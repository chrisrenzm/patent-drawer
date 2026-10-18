"""Patent Drawer pipeline. All state lives in one run folder; every step can be re-run.

  pd.py init     RUN --pdf P --patent-id WO-2020243027-A1 --prefix A --target CYP46A1
  pd.py tables   RUN                     pages that mention "Table N" (to find the data tables)
  pd.py crops    RUN --pages 14-39       cut the structure table into crops/<no>.png
  (agent writes RUN/tracker.csv and RUN/spec.json, user confirms)  -> GATE 1, GATE 2
  pd.py resolve  RUN [--mode thorough|lean] [--batch 20]
                                         name -> structure -> database + MS check; review images; checker batches
  (checker subagents write RUN/batches/batch_K.result.json)
  pd.py apply    RUN                     read checker results (corrected names go through OPSIN again)
  pd.py draw     RUN [--only A6]         write cdx/<label>.cdxml for every resolved compound
  pd.py doublecheck RUN [--sample 0.2]  card formula/MW vs patent (all); batches for the MW and cross-check agent groups
  (MW agents write batches/mw_K.result.json; cross-check agents write batches/xc_K.result.json)
  pd.py dcapply  RUN                     read double-check verdicts
  pd.py validate RUN                     code checks -> validation/report.md
  pd.py outputs  RUN                     deck + Excel + contact sheet
  pd.py status   RUN                     counts per status
"""
import argparse, csv, glob, json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import patent as P

TRACKER_COLS = ["order", "patent_no", "source_tables", "pages", "activity_raw", "activity_display",
                "selected", "reason"]
STATUS_COLS = ["label", "name", "name_page", "drawing_page", "smiles", "mw", "formula", "structure_source",
               "in_db", "ms_match", "status", "flags", "validation"]

# ---------- run folder helpers ----------

def cfg(run):
    return json.load(open(os.path.join(run, "config.json")))

def pdf_path(run):
    return os.path.join(run, "patent.pdf")

def read_tracker(run):
    with open(os.path.join(run, "tracker.csv"), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def write_tracker(run, rows):
    cols = list(rows[0].keys())
    for c in STATUS_COLS:
        if c not in cols:
            cols.append(c)
    with open(os.path.join(run, "tracker.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})

def selected(rows):
    return [r for r in rows if str(r.get("selected", "")).lower() in ("yes", "y", "true", "1")]

def rec_path(run, no):
    return os.path.join(run, "records", f"{no}.json")

def load_rec(run, no):
    p = rec_path(run, no)
    return json.load(open(p)) if os.path.exists(p) else None

def save_rec(run, rec):
    os.makedirs(os.path.join(run, "records"), exist_ok=True)
    json.dump(rec, open(rec_path(run, rec["patent_no"]), "w"), indent=1, ensure_ascii=False)

def label(run, no):
    s = json.load(open(os.path.join(run, "spec.json")))
    return s["label_pattern"].format(patent_no=no)

def parse_pages(s):
    out = []
    for part in s.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out

# ---------- steps ----------

def init(a):
    os.makedirs(a.run, exist_ok=True)
    shutil.copy(a.pdf, pdf_path(a.run))
    c = dict(patent_id=a.patent_id, prefix=a.prefix, target=a.target, source_pdf=os.path.abspath(a.pdf))
    json.dump(c, open(os.path.join(a.run, "config.json"), "w"), indent=1)
    try:
        n = P.fetch_patent_db(a.patent_id, os.path.join(a.run, "patent_db.csv"))
        print(f"database: PubChem links {n} compounds to {a.patent_id}")
    except Exception as e:
        print("database: PubChem not reachable, continuing without it:", e)
    print("pages:", len(P.patent_text(pdf_path(a.run)).split("<<PAGE ")) - 1)
    print("example titles with compound labels:", len(P.example_titles(pdf_path(a.run), a.prefix)))

def tables(a):
    t = P.patent_text(pdf_path(a.run))
    pages = t.split("<<PAGE ")[1:]
    empty = []
    for p in pages:
        num, _, body = p.partition(">>")
        for m in re.finditer(r"Table \d+[^\n]{0,80}", body):
            print(f"p{num}: {m.group(0).strip()}")
        if len(body.strip()) < 80:
            empty.append(int(num))
    if empty:
        print("pages with (almost) no text layer, probably drawings:", empty)

def ocr(a):
    """Text of picture-only pages (local OCR), row by row, saved to RUN/ocr/p<N>.txt."""
    import pymupdf
    d = pymupdf.open(pdf_path(a.run))
    os.makedirs(os.path.join(a.run, "ocr"), exist_ok=True)
    for pn in parse_pages(a.pages):
        png = os.path.join(a.run, "ocr", f"p{pn}.png")
        d[pn - 1].get_pixmap(dpi=200).save(png)
        res, _ = P._ocr_engine()(png)
        os.remove(png)
        rows = []
        for box, txt, _ in sorted(res or [], key=lambda r: (round(r[0][0][1] / 25), r[0][0][0])):
            y = round(box[0][1] / 25)
            if rows and rows[-1][0] == y:
                rows[-1][1].append(txt)
            else:
                rows.append((y, [txt]))
        text = "\n".join(" | ".join(t) for _, t in rows)
        open(os.path.join(a.run, "ocr", f"p{pn}.txt"), "w").write(text)
        print(f"--- page {pn}\n{text}")

def crops(a):
    c = cfg(a.run)
    idx = P.index_table(pdf_path(a.run), parse_pages(a.pages), c["prefix"], os.path.join(a.run, "crops"))
    print(f"{len(idx)} drawings cut out:", " ".join(sorted(idx, key=lambda k: int(re.sub(r'\D', '', k) or 0))))

def _review_image(run, no, smiles, out_name=None):
    """Patent drawing (left) next to our structure (right), for the checker."""
    from PIL import Image, ImageDraw
    from rdkit import Chem
    from rdkit.Chem import Draw
    os.makedirs(os.path.join(run, "review"), exist_ok=True)
    crop = os.path.join(run, "crops", f"{no}.png")
    left = Image.open(crop).convert("RGB") if os.path.exists(crop) else Image.new("RGB", (500, 350), "white")
    right = Draw.MolToImage(Chem.MolFromSmiles(smiles), size=(500, 350)) if smiles else Image.new("RGB", (500, 350), "white")
    h = max(left.height, right.height) + 30
    img = Image.new("RGB", (left.width + right.width + 20, h), "white")
    img.paste(left, (0, 30)); img.paste(right, (left.width + 20, 30))
    d = ImageDraw.Draw(img)
    d.text((5, 5), f"{no}  patent drawing", fill="black")
    d.text((left.width + 25, 5), "our structure" if smiles else "our structure: NONE", fill="black")
    out = os.path.join(run, "review", f"{out_name or no}.png")
    img.save(out)
    return out

def resolve(a):
    c, pdf = cfg(a.run), pdf_path(a.run)
    rows = read_tracker(a.run)
    db = os.path.join(a.run, "patent_db.csv")
    idx_file = os.path.join(a.run, "crops", "index.json")
    idx = json.load(open(idx_file)) if os.path.exists(idx_file) else {}
    todo = []
    # A new or poorly indexed patent has almost nothing in PubChem; then the flag is noise.
    use_db = len(P.db_keys(db)) >= 0.25 * len(selected(rows))
    if not use_db:
        note = (f"PubChem: only {len(P.db_keys(db))} compounds linked to this patent, "
                "so the 'not in database list' check was skipped for every compound.")
        print(note)
        with open(os.path.join(a.run, "decisions.md"), "a") as f:
            f.write("- " + note + "\n")
    for r in selected(rows):
        no = r["patent_no"]
        e = P.example_name(pdf, c["prefix"], no)
        s = P.opsin(e["name"]) if e else None
        info = P.mol_info(s) if s else None
        rec = dict(patent_no=no, label=label(a.run, no), name=e and e["name"], name_page=e and e["page"],
                   drawing_page=idx.get(no, {}).get("page"), ms_found=e["ms"] if e else [],
                   smiles=None, flags=[])
        if info:
            rec.update(info, structure_source=f"name (Example {e['example']}, p.{e['page']}) -> OPSIN")
            rec["in_db"] = info["inchikey"] in P.db_keys(db)
            rec["ms_match"] = any(abs(v - info["mh"]) < 0.6 for v in rec["ms_found"]) if rec["ms_found"] else None
            if use_db and not rec["in_db"]:
                rec["flags"].append("not in database list")
            if rec["ms_match"] is False:
                rec["flags"].append("MS does not match")
        else:
            rec["structure_source"] = None
            rec["flags"].append("no name found" if not e else "name did not convert")
        if no not in idx:
            rec["flags"].append("no drawing found")
        # Thorough: every compound is checked against its drawing. Lean: only flagged ones.
        need = a.mode == "thorough" or rec["flags"]
        rec["status"] = "to_check" if need else "trusted"
        save_rec(a.run, rec)
        if need:
            rec["review_png"] = _review_image(a.run, no, rec.get("smiles"))
            todo.append(rec)
        print(no, rec["status"], "; ".join(rec["flags"]))
    bdir = os.path.join(a.run, "batches")
    os.makedirs(bdir, exist_ok=True)
    for f in glob.glob(os.path.join(bdir, "batch_*.json")):
        os.remove(f)
    for k in range(0, len(todo), a.batch):
        items = [dict(no=r["patent_no"], name=r["name"], smiles=r.get("smiles"), review_png=r["review_png"],
                      drawing_png=os.path.join(a.run, "crops", r["patent_no"] + ".png"),
                      code_flags=r["flags"]) for r in todo[k:k + a.batch]]
        json.dump(items, open(os.path.join(bdir, f"batch_{k // a.batch + 1}.json"), "w"), indent=1)
    sync(a.run)
    print(f"{len(todo)} compounds to check in {-(-len(todo) // a.batch)} batch(es) in {bdir}")

def apply(a):
    """Checker verdicts: match -> trusted; fixed (corrected name) -> OPSIN again, flagged for user; flag -> flagged."""
    db = os.path.join(a.run, "patent_db.csv")
    n = 0
    for f in sorted(glob.glob(os.path.join(a.run, "batches", "batch_*.result.json"))):
        for v in json.load(open(f)):
            rec = load_rec(a.run, v["no"])
            if not rec:
                print("unknown compound in", f, v.get("no")); continue
            rec["checker"] = v
            verdict = v.get("verdict")
            if verdict == "match":
                rec["status"] = "trusted"
            elif verdict == "fixed" and v.get("corrected_name"):
                s = P.opsin(v["corrected_name"])
                info = P.mol_info(s) if s else None
                if info:
                    rec.update(info, name=v["corrected_name"],
                               structure_source=f"corrected name from drawing -> OPSIN ({v.get('reason', '')})")
                    rec["in_db"] = info["inchikey"] in P.db_keys(db)
                    rec["ms_match"] = any(abs(x - info["mh"]) < 0.6 for x in rec["ms_found"]) if rec["ms_found"] else None
                    rec["flags"].append("corrected from drawing: " + v.get("reason", ""))
                else:
                    rec["flags"].append("corrected name did not convert: " + v["corrected_name"])
                rec["status"] = "flagged"
            else:
                rec["flags"].append("checker: " + v.get("reason", "no reason given"))
                rec["status"] = "flagged"
            save_rec(a.run, rec); n += 1
    sync(a.run)
    print(f"applied {n} checker verdicts")
    status(a)

def fixbatch(a):
    """Every flagged compound -> batches/fix_K.json for the fixer group."""
    bdir = os.path.join(a.run, "batches")
    for f in glob.glob(os.path.join(bdir, "fix_*.json")):
        os.remove(f)
    todo = []
    for r in selected(read_tracker(a.run)):
        rec = load_rec(a.run, r["patent_no"])
        if rec and (rec["status"] == "flagged" or (rec.get("ms_match") is False and not rec.get("ms_explained"))):
            todo.append(dict(no=rec["patent_no"], name=rec.get("name"), smiles=rec.get("smiles"), flags=rec["flags"],
                             review_png=_review_image(a.run, rec["patent_no"], rec.get("smiles")),
                             drawing_png=os.path.join(a.run, "crops", rec["patent_no"] + ".png")))
    for i in range(0, len(todo), a.batch):
        json.dump(todo[i:i + a.batch], open(os.path.join(bdir, f"fix_{i // a.batch + 1}.json"), "w"), indent=1)
    print(f"{len(todo)} flagged compounds to fix in {-(-len(todo) // a.batch)} batch(es):", " ".join(x["no"] for x in todo))

def fixapply(a):
    """Fixer verdicts: false_alarm -> trusted; fixed -> new name through OPSIN, status 'fixed' until the
    cross-check confirms it; cannot_fix -> stays flagged for the user. Every case goes into mistakes.md."""
    log = os.path.join(a.run, "mistakes.md")
    if not os.path.exists(log):
        open(log, "w").write("# Mistake log\n\n| Compound | Flag | Verdict | Where it went wrong | What was done |\n|---|---|---|---|---|\n")
    for f in sorted(glob.glob(os.path.join(a.run, "batches", "fix_*.result.json"))):
        for v in json.load(open(f)):
            rec = load_rec(a.run, v["no"])
            if not rec:
                print("unknown compound in", f, v.get("no")); continue
            verdict, done = v.get("verdict"), v.get("reason", "")
            if verdict == "false_alarm":
                rec["status"] = "trusted"
                if rec.get("ms_match") is False:
                    rec["ms_explained"] = done
            elif verdict == "fixed" and v.get("corrected_name"):
                s = P.opsin(v["corrected_name"])
                info = P.mol_info(s) if s else None
                if info:
                    rec.update(info, name=v["corrected_name"],
                               structure_source=f"fixed from drawing -> OPSIN ({done})")
                    rec["ms_match"] = any(abs(x - info["mh"]) < 0.6 for x in rec["ms_found"]) if rec["ms_found"] else None
                    rec["status"] = "fixed" if rec["ms_match"] is not False else "flagged"
                    done = f"new name: {v['corrected_name']}" + ("" if rec["ms_match"] is not False else " (mass still off)")
                else:
                    rec["status"], done = "flagged", "corrected name did not convert: " + v["corrected_name"]
            else:
                rec["status"] = "flagged"
            if rec["status"] != "flagged":
                rec.setdefault("resolved_flags", []).extend(rec["flags"]); rec["flags"] = []
            row = [rec["patent_no"], "; ".join(rec.get("resolved_flags", []) + rec["flags"])[-200:], verdict,
                   v.get("where", ""), done]
            open(log, "a").write("| " + " | ".join(str(x).replace("|", "/") for x in row) + " |\n")
            save_rec(a.run, rec)
    sync(a.run)
    status(a)

# ChemDraw stores a pasted CLogP as a live <chemicalproperty> (type 18) linked to the molecule's atoms and
# bonds, and recalculates it when the structure changes. So we write that link into each file ourselves,
# ChemDraw opens it, "Clean Up" nudges the structure, and the saved file holds ChemDraw's own value.
CLOGP_SCRIPT = """
on run argv
  repeat with p in argv
    set f to POSIX file (p as text)
    tell application "ChemDraw"
      open f
      clean front document
      save front document
      close front document saving no
    end tell
  end repeat
end run
"""

def _add_clogp_link(path):
    s = open(path).read()
    frag = re.search(r"<fragment.*?</fragment>", s, re.S).group(0)
    basis = re.findall(r'<[nb]\s+id="(\d+)"', frag)
    nid = max(int(x) for x in re.findall(r'\bid="(\d+)"', s)) + 1
    add = (f'<t id="{nid}" p="0 0" InterpretChemically="no"><s font="3" size="10" color="0">CLogP: PENDING</s></t>'
           f'<chemicalproperty id="{nid + 1}" ChemicalPropertyDisplayID="{nid}" ChemicalPropertyIsActive="yes" '
           f'ChemicalPropertyType="18" BasisObjects="{" ".join(basis)}"/>')
    open(path, "w").write(s.replace("</page>", add + "</page>", 1))

def chemdraw_check(a):
    """Start-of-run check: is ChemDraw installed, and can it calculate CLogP (Professional or Signals ChemDraw)?"""
    sys.path.insert(0, HERE)
    from draw_card import draw_card
    if sys.platform != "darwin":
        print("CHEMDRAW: not checked (CLogP from ChemDraw is only set up for macOS)"); return
    if not os.path.exists("/Applications/ChemDraw.app"):
        print("CHEMDRAW: not installed"); return
    import tempfile
    f = os.path.join(tempfile.mkdtemp(), "check.cdxml")
    draw_card("CN1C=NC2=C1C(=O)N(C(=O)N2C)C", [], f)  # caffeine; ChemDraw gives CLogP -0.04
    _add_clogp_link(f)
    subprocess.run(["osascript", "-", f], input=CLOGP_SCRIPT, capture_output=True, text=True)
    m = re.search(r"CLogP:\s*(-?[\d.]+)", open(f).read())
    print(f"CHEMDRAW: ok, CLogP works (caffeine {m.group(1)})" if m else
          "CHEMDRAW: installed, but no CLogP came back (needs ChemDraw Professional or Signals ChemDraw)")

def clogp(a):
    """ChemDraw's own CLogP for each structure, with no clicks: needs ChemDraw on a Mac (run outside the sandbox)."""
    if sys.platform != "darwin":
        print("CLogP from ChemDraw is only set up for macOS so far; leaving CLogP blank.")
        return
    sys.path.insert(0, HERE)
    from draw_card import draw_card
    rows = read_tracker(a.run)
    d = os.path.join(a.run, "clogp")
    os.makedirs(d, exist_ok=True)
    nos = a.only.split(",") if a.only else [r["patent_no"] for r in selected(rows)]
    files = {}
    for no in nos:
        rec = load_rec(a.run, no)
        if not rec or not rec.get("smiles"):
            print(no, "skipped: no structure"); continue
        files[no] = os.path.join(d, no + ".cdxml")
        draw_card(rec["smiles"], [], files[no])
        _add_clogp_link(files[no])
    r = subprocess.run(["osascript", "-"] + list(files.values()), input=CLOGP_SCRIPT, capture_output=True, text=True)
    if r.returncode:
        print("ChemDraw step failed:", r.stderr.strip()[-300:])
    got = {}
    for no, f in files.items():
        m = re.search(r"CLogP:\s*(-?[\d.]+)", open(f).read())
        if m:
            got[no] = f"{float(m.group(1)):.2f}"
        else:
            print(no, "no CLogP from ChemDraw")
    for row in rows:
        row["clogp"] = got.get(row["patent_no"], row.get("clogp", ""))
    write_tracker(a.run, rows)
    print(f"CLogP from ChemDraw for {len(got)} of {len(nos)} compounds")

def caption_lines(spec, row, rec):
    vals = {**row, **rec, "label": rec["label"], "clogp": row.get("clogp", "")}
    out = []
    for t in spec["caption_lines"]:
        out.append(t.format(**vals))
    for t in spec.get("extra_lines", []):
        fields = re.findall(r"{(\w+)", t)
        if all(str(vals.get(f, "")).strip() for f in fields):
            out.append(t.format(**vals))
    return out

def draw(a):
    sys.path.insert(0, HERE)
    from draw_card import draw_card
    spec = json.load(open(os.path.join(a.run, "spec.json")))
    rows = {r["patent_no"]: r for r in read_tracker(a.run)}
    os.makedirs(os.path.join(a.run, "cdx"), exist_ok=True)
    nos = a.only.split(",") if a.only else [r["patent_no"] for r in selected(rows.values())]
    for no in nos:
        rec = load_rec(a.run, no)
        if not rec or not rec.get("smiles"):
            print(no, "skipped: no structure"); continue
        out = os.path.join(a.run, "cdx", rec["label"] + ".cdxml")
        draw_card(rec["smiles"], caption_lines(spec, rows[no], rec), out)
        rec["file"] = out
        save_rec(a.run, rec)
        print(no, "->", os.path.basename(out))

def card_info(run, no):
    """Structure read back from the finished card file (not from the record)."""
    from rdkit import Chem
    rec = load_rec(run, no)
    f = os.path.join(run, "cdx", rec["label"] + ".cdxml")
    mols = [m for m in Chem.MolsFromCDXMLFile(f) if m and m.GetNumAtoms() > 1] if os.path.exists(f) else []
    m = max(mols, key=lambda m: m.GetNumAtoms()) if mols else None
    info = P.mol_info(Chem.MolToSmiles(m)) if m else {}
    return dict(info or {}, file=f, caption=_card_text(f) if os.path.exists(f) else "")

def doublecheck(a):
    """Stage A (code, all): card formula/MW vs the patent's own formula and MS.
    Mismatches -> batches/mw_K.json for the MW agent group.
    Stage B: all flagged + a random sample of trusted -> batches/xc_K.json for the cross-check group."""
    import math, random
    c, pdf = cfg(a.run), pdf_path(a.run)
    bdir = os.path.join(a.run, "batches")
    for f in glob.glob(os.path.join(bdir, "mw_*.json")) + glob.glob(os.path.join(bdir, "xc_*.json")):
        os.remove(f)
    mw_todo, trusted, flagged = [], [], []
    n = dict(formula_ok=0, formula_mismatch=0, no_formula=0)
    for r in selected(read_tracker(a.run)):
        no = r["patent_no"]
        rec, card = load_rec(a.run, no), card_info(a.run, no)
        e = P.example_name(pdf, c["prefix"], no)
        forms, ms = (e["formulas"], e["ms"]) if e else ([], [])
        chk = dict(card_formula=card.get("formula"), card_mw=card.get("mw"), patent_formulas=forms, patent_ms=ms)
        if not card.get("smiles"):
            chk["formula"] = "no card structure"
        elif not forms:
            chk["formula"] = "no formula in patent"; n["no_formula"] += 1
        elif any(P.formula_matches(f, card["smiles"]) for f in forms):
            chk["formula"] = "ok"; n["formula_ok"] += 1
        else:
            chk["formula"] = "mismatch"; n["formula_mismatch"] += 1
        chk["ms"] = ("ok" if any(abs(v - card["mh"]) < 0.6 for v in ms) else "mismatch") if ms and card.get("mh") else "no data"
        rec["doublecheck"] = dict(code=chk)
        save_rec(a.run, rec)
        if chk["formula"] not in ("ok", "no formula in patent") or chk["ms"] == "mismatch":
            mw_todo.append(dict(no=no, label=rec["label"], name=rec.get("name"), **chk))
        (trusted if rec["status"] == "trusted" else flagged).append(no)
    k = math.ceil(a.sample * len(trusted))
    sample = sorted(random.Random(a.seed).sample(trusted, k), key=trusted.index)
    xc = [dict(no=no, label=load_rec(a.run, no)["label"], drawing_png=os.path.join(a.run, "crops", no + ".png"),
               why="flagged" if no in flagged else "random sample") for no in flagged + sample]
    for name, items in (("mw", mw_todo), ("xc", xc)):
        for i in range(0, len(items), a.batch):
            json.dump(items[i:i + a.batch], open(os.path.join(bdir, f"{name}_{i // a.batch + 1}.json"), "w"), indent=1)
    print(f"code check of {sum(n.values())} cards: {n}; MS mismatches: {sum(1 for x in mw_todo if x['ms'] == 'mismatch')}")
    print(f"MW group: {len(mw_todo)} to review ({-(-len(mw_todo) // a.batch)} batch(es)): {' '.join(x['no'] for x in mw_todo)}")
    print(f"cross-check group: {len(xc)} ({len(flagged)} flagged + {k} random of {len(trusted)} trusted) in {-(-len(xc) // a.batch)} batch(es)")

def dcapply(a):
    """Read double-check verdicts. 'problem' -> flagged for the user."""
    from collections import Counter
    cnt = Counter()
    for f in sorted(glob.glob(os.path.join(a.run, "batches", "mw_*.result.json")) +
                    glob.glob(os.path.join(a.run, "batches", "xc_*.result.json"))):
        group = "MW check" if os.path.basename(f).startswith("mw_") else "cross-check"
        for v in json.load(open(f)):
            rec = load_rec(a.run, v["no"])
            if not rec:
                print("unknown compound in", f, v.get("no")); continue
            rec.setdefault("doublecheck", {})[group] = v
            cnt[(group, v.get("verdict"))] += 1
            if v.get("verdict") != "ok":
                rec["status"] = "flagged"
                rec["flags"].append(f"{group}: {v.get('reason', 'no reason given')}")
            elif rec["status"] == "fixed" and group == "cross-check":
                rec["status"] = "trusted"  # an independent check confirmed the fix
            save_rec(a.run, rec)
    sync(a.run)
    for (g, v), x in sorted(cnt.items()):
        print(f"{g}: {v} {x}")

def _card_text(path):
    """Caption text on a card: styled runs joined, one text block per line."""
    import xml.etree.ElementTree as ET
    root = ET.parse(path).getroot()
    return "\n".join("".join(s.text or "" for s in t.iter("s")) for t in root.iter("t"))

def validate(a):
    from rdkit import Chem
    spec = json.load(open(os.path.join(a.run, "spec.json")))
    rows = read_tracker(a.run)
    sel = selected(rows)
    lines, counts = [], dict(pass_=0, flag=0)
    seen = set()
    for r in sel:
        no, probs = r["patent_no"], []
        rec = load_rec(a.run, no)
        if not rec or not rec.get("smiles"):
            probs.append("no structure")
        else:
            f = os.path.join(a.run, "cdx", rec["label"] + ".cdxml")
            if not os.path.exists(f):
                probs.append("card file missing")
            else:
                mols = [m for m in Chem.MolsFromCDXMLFile(f) if m and m.GetNumAtoms() > 1]
                m = max(mols, key=lambda m: m.GetNumAtoms()) if mols else None
                info = P.mol_info(Chem.MolToSmiles(m)) if m else None
                if not info:
                    probs.append("card does not read back as a structure")
                else:
                    if info["inchikey"] != rec["inchikey"]:
                        probs.append("card structure differs from record")
                    x = _card_text(f)
                    if f"{info['mw']:.2f}" not in x:
                        probs.append(f"MW {info['mw']:.2f} not on card")
                    if rec["label"] not in x:
                        probs.append("label not on card")
                    if "μ" in x or "Μ" in x:
                        probs.append("Greek mu/Mu in text (use µ and M)")
                    for t in caption_lines(spec, r, rec)[1:]:
                        plain = re.sub(r"<[^>]+>", "", t).strip()
                        if plain and plain not in x:
                            probs.append(f"caption line missing: {plain}")
            if rec["inchikey"] in seen:
                probs.append("duplicate structure of another compound")
            seen.add(rec["inchikey"])
            if rec.get("ms_match") is False and not rec.get("ms_explained"):
                probs.append("MS in patent does not match MW")
            if rec["status"] != "trusted":
                probs.append("needs your review: " + "; ".join(rec["flags"]))
        r["validation"] = "pass" if not probs else "flag"
        counts["pass_" if not probs else "flag"] += 1
        if probs:
            lines.append(f"- **{no}** (p.{(rec or {}).get('drawing_page') or (rec or {}).get('name_page')}): " + "; ".join(probs))
    write_tracker(a.run, rows)
    os.makedirs(os.path.join(a.run, "validation"), exist_ok=True)
    rep = [f"# Validation report", "", f"{len(sel)} compounds: {counts['pass_']} pass, {counts['flag']} need a look.", "",
           "## Needs a look", ""] + (lines or ["None."])
    open(os.path.join(a.run, "validation", "report.md"), "w").write("\n".join(rep) + "\n")
    print("\n".join(rep))

def outputs(a):
    py = sys.executable
    spec = json.load(open(os.path.join(a.run, "spec.json")))
    os.makedirs(os.path.join(a.run, "out"), exist_ok=True)
    name = spec.get("deck_name", "deck")
    cmds = [[py, os.path.join(HERE, "deck", "build_deck.py"), os.path.join(a.run, "cdx"),
             os.path.join(a.run, "out", name + ".pptx")] + spec.get("title_lines", []),
            [py, os.path.join(HERE, "build_excel.py"), os.path.join(a.run, "tracker.csv"),
             os.path.join(a.run, "out", name + ".xlsx")],
            [py, os.path.join(HERE, "contact_sheet.py"), os.path.join(a.run, "tracker.csv"),
             os.path.join(a.run, "cdx"), os.path.join(a.run, "crops"), os.path.join(a.run, "out", "contact_sheet.pdf")]]
    if spec.get("template"):
        cmds[0] += ["--template", spec["template"]]
    for cmd in cmds:
        r = subprocess.run(cmd, capture_output=True, text=True)
        print(os.path.basename(cmd[1]), "ok" if r.returncode == 0 else "FAILED\n" + r.stderr[-1500:])
    if a.export:
        # One clean folder with everything the user needs; working files stay in RUN.
        dest = os.path.expanduser(a.export)
        os.makedirs(dest, exist_ok=True)
        for f in glob.glob(os.path.join(a.run, "out", "*")):
            shutil.copy2(f, dest)
        shutil.copytree(os.path.join(a.run, "cdx"), os.path.join(dest, "ChemDraw files"), dirs_exist_ok=True)
        for f in ["validation/report.md", "tracker.csv", "decisions.md", "mistakes.md"]:
            if os.path.exists(os.path.join(a.run, f)):
                shutil.copy2(os.path.join(a.run, f), dest)
        print("exported to", dest)

def sync(run):
    """Copy record fields into tracker.csv so it is the one readable state file."""
    rows = read_tracker(run)
    for r in rows:
        rec = load_rec(run, r["patent_no"])
        if rec:
            for c in STATUS_COLS:
                if c in rec:
                    v = rec[c]
                    r[c] = "; ".join(v) if isinstance(v, list) else ("" if v is None else v)
    write_tracker(run, rows)

def status(a):
    from collections import Counter
    recs = [load_rec(a.run, r["patent_no"]) for r in selected(read_tracker(a.run))]
    print(dict(Counter((r or {}).get("status", "not resolved") for r in recs)))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init"); s.add_argument("run"); s.add_argument("--pdf", required=True)
    s.add_argument("--patent-id", required=True); s.add_argument("--prefix", default="")
    s.add_argument("--target", default="")
    for name in ["tables", "apply", "validate", "status", "dcapply"]:
        sub.add_parser(name).add_argument("run")
    s = sub.add_parser("outputs"); s.add_argument("run"); s.add_argument("--export")
    s = sub.add_parser("fixbatch"); s.add_argument("run"); s.add_argument("--batch", type=int, default=20)
    sub.add_parser("fixapply").add_argument("run")
    s = sub.add_parser("clogp"); s.add_argument("run"); s.add_argument("--only")
    sub.add_parser("chemdraw_check")
    for name in ["crops", "ocr"]:
        s = sub.add_parser(name); s.add_argument("run"); s.add_argument("--pages", required=True)
    s = sub.add_parser("resolve"); s.add_argument("run")
    s.add_argument("--mode", default="thorough", choices=["thorough", "lean"]); s.add_argument("--batch", type=int, default=20)
    s = sub.add_parser("draw"); s.add_argument("run"); s.add_argument("--only")
    s = sub.add_parser("doublecheck"); s.add_argument("run"); s.add_argument("--sample", type=float, default=0.2)
    s.add_argument("--seed", type=int, default=0); s.add_argument("--batch", type=int, default=20)
    a = ap.parse_args()
    globals()[a.cmd](a)
