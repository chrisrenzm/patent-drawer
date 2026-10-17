"""Read a patent PDF: text, Example-title names, mass-spec values, table drawings.

Everything is tied to a run folder (see pd.py). Nothing here calls a model.
"""
import json, os, re, time, urllib.parse
from functools import lru_cache
import numpy as np, pymupdf, requests
from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors, rdMolDescriptors

RDLogger.DisableLog("rdApp.*")
DPI = 150

# ---------- structures ----------

def mol_info(smiles):
    m = Chem.MolFromSmiles(smiles or "")
    if not m:
        return None
    return dict(smiles=Chem.MolToSmiles(m), inchikey=Chem.MolToInchiKey(m),
                formula=rdMolDescriptors.CalcMolFormula(m),
                mw=round(Descriptors.MolWt(m), 2),
                mh=round(Descriptors.ExactMolWt(m) + 1.00728, 1))

# ---------- patent text ----------

@lru_cache(None)
def patent_text(pdf):
    d = pymupdf.open(pdf)
    return "".join(f"\n<<PAGE {i+1}>>\n" + p.get_text() for i, p in enumerate(d))

# Common scanning typos in OCR'd patents.
TYPOS = [(r"-\s?(?:5|10|15|20|25|30)\s+(?=[a-z]{3})", "-"),          # margin line numbers
         (r"(?<![\w])[lI]-", "1-"), (r"(?<=[\s(\[,-])l,", "1,"), (r"(?<=[\s(\[,-])l(?=[,H])", "1"),
         (r"(?<=[a-z]) 1(?=[)\-\]])", "l"), (r"Ij(?=[a-z])", "l)"), (r"(?<=[a-z])I(?=[a-z)\-])", "l"),
         (r"f[il1]{2,3}oro", "fluoro"), (r"henzy", "benzy"), (r"carhon", "carbon"), (r"hipyridin", "bipyridin"),
         (r"\bO-", "0-"), (r"\s+'", "'"), (r"(\d)' ([a-z])", r"\1'-\2")]

def fix_typos(name):
    for a, b in TYPOS:
        name = re.sub(a, b, name)
    return name

def _label_pattern(raw, prefix):
    """Scanned label -> regex: 'AlO' -> A10, 'A 3 7' -> A37, 'ASl' -> A[35]1."""
    s = raw.replace(" ", "")[len(prefix):]
    s = s.translate(str.maketrans("lIiOo", "11100"))
    return prefix + s.replace("S", "[35]")

@lru_cache(None)
def example_titles(pdf, prefix):
    """Every compound named in an 'Example N. [Synthesis of] <name> (<label>)' title."""
    t, out = patent_text(pdf), []
    heads = list(re.finditer(r"\n(?:\d{1,2}\s+)?Example (\d+)\.", t))
    for k, h in enumerate(heads):
        block = t[h.end(): heads[k + 1].start() if k + 1 < len(heads) else len(t)]
        head = block[:700]
        labs = list(re.finditer(r"\(\s*(" + re.escape(prefix) + r"[\sA-Za-z0-9]{1,5}?)\s*\)", head))
        page = t[:h.start()].count("<<PAGE ")
        ms = re.findall(r"\[M\s*\+\s*H\]\s*\+?\s*:?\s*\d{3}(?:\.\d)?\s*,?\s*found\s*:?\s*(\d{3}(?:\.\d)?)", block)
        formulas = re.findall(r"calcd\.?\s*(?:for|For)?\s*:?\s*([A-Z][A-Za-z0-9]{4,30})", block)
        start = 0
        for lab in labs:
            raw = re.sub(r"^\s*(?:Synthes[ie]s of|Preparation of|and)\s*", "", head[start:lab.start()].strip())
            name = re.sub(r"\s*\n\s*", "", re.sub(r"-\s*\n\s*", "-", raw)).strip()
            out.append(dict(example=int(h.group(1)), label_pattern=_label_pattern(lab.group(1), prefix),
                            raw=raw, name=fix_typos(name), page=page,
                            ms=sorted({float(f) for f in ms}), formulas=formulas))
            start = lab.end()
    return out

def example_name(pdf, prefix, no):
    """Name of compound `no` from its Example title (typos fixed), page, [M+H]+ found values."""
    ts = example_titles(pdf, prefix)
    hits = [e for e in ts if e["label_pattern"] == no] or \
           [e for e in ts if re.fullmatch(e["label_pattern"], no)]
    return hits[0] if hits else None

def parse_formula(s):
    """Scanned formula -> {element: count}. Fixes 'Hi8'->H18, 'CI'->Cl, 'N50'->N5O, 'H2OCl'->H20Cl."""
    s = re.sub(r"CI(?![a-z])", "Cl", s)
    s = re.sub(r"(?<=\d)[iIl]|[iIl](?=\d)", "1", s)
    s = re.sub(r"(?<=H\d)O(?=[A-Z])", "0", s)
    s = re.sub(r"(?<=[NOFSPl])(\d)0(\d?)", r"\1O\2", s)
    out = {}
    for el, n in re.findall(r"([A-Z][a-z]?)(\d*)", s):
        out[el] = out.get(el, 0) + int(n or 1)
    return out

def formula_matches(patent_formula, smiles):
    """True if a patent formula is this structure as M, [M+H] or [M+Na]."""
    from rdkit.Chem import rdMolDescriptors
    m = Chem.MolFromSmiles(smiles)
    f = parse_formula(rdMolDescriptors.CalcMolFormula(m))
    p = parse_formula(patent_formula)
    plus_h = {**f, "H": f.get("H", 0) + 1}
    plus_na = {**f, "Na": 1}
    return p in (f, plus_h, plus_na)

def mentions(pdf, no, n=6, width=400):
    t = patent_text(pdf)
    return [t[max(0, m.start() - width): m.end() + width] for m in re.finditer(r"\b" + re.escape(no) + r"\b", t)][:n]

# ---------- name -> structure ----------

def opsin(name):
    """IUPAC name -> SMILES with the free OPSIN web service (EBI)."""
    url = "https://www.ebi.ac.uk/opsin/ws/" + urllib.parse.quote(name, safe="") + ".smi"
    for _ in range(3):
        try:
            r = requests.get(url, timeout=30)
            return r.text.strip() if r.status_code == 200 else None
        except requests.RequestException:
            time.sleep(1)
    return None

# ---------- database ----------

PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

def fetch_patent_db(patent_id, out_csv):
    """InChIKeys of every compound PubChem links to the patent (2 calls). patent_id like WO-2020243027-A1."""
    cids = requests.get(f"{PUG}/compound/xref/PatentID/{patent_id}/cids/TXT", timeout=60).text.split()
    cids = [c for c in cids if c.isdigit()]
    rows = ["CID,InChIKey"]
    for i in range(0, len(cids), 500):
        r = requests.post(f"{PUG}/compound/cid/property/InChIKey/CSV",
                          data={"cid": ",".join(cids[i:i + 500])}, timeout=120)
        rows += [l.replace('"', "") for l in r.text.splitlines()[1:]]
    open(out_csv, "w").write("\n".join(rows) + "\n")
    return len(rows) - 1

@lru_cache(None)
def db_keys(csv_path):
    if not os.path.exists(csv_path):
        return {}
    keys = {}
    for line in open(csv_path).read().splitlines()[1:]:
        cid, key = line.split(",")
        keys[key] = int(cid)
    return keys

# ---------- table drawings ----------

@lru_cache(None)
def _ocr_engine():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()

def _ocr(png_path):
    res, _ = _ocr_engine()(png_path)
    return " ".join(r[1] for r in (res or []))

def index_table(pdf, pages, prefix, crops_dir):
    """Cut every row of a gridded 'label | drawing' table into crops/<label>.png.

    Labels come from the PDF text layer when present, otherwise from local OCR.
    Returns {label: {page, crop}} and saves it as crops/index.json.
    """
    os.makedirs(crops_dir, exist_ok=True)
    d, idx = pymupdf.open(pdf), {}
    lab_re = re.compile(re.escape(prefix) + r"\s?(\d{1,4})")
    for pn in pages:
        page = d[pn - 1]
        pix = page.get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
        a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w)
        dark = a < 128
        vl = np.where(dark.sum(0) > 0.15 * pix.h)[0]
        vl = [x for i, x in enumerate(vl) if i == 0 or x - vl[i - 1] > 3]
        if len(vl) < 3:
            continue
        x0, xm, x1 = vl[0], vl[1], vl[-1]
        hl = np.where(dark[:, x0:x1].sum(1) > 0.8 * (x1 - x0))[0]
        lines = [y for i, y in enumerate(hl) if i == 0 or y - hl[i - 1] > 3]
        for ya, yb in zip(lines, lines[1:]):
            if yb - ya < 60:
                continue
            lab_rect = pymupdf.Rect(x0, ya, xm, yb) * (72 / DPI)
            txt = page.get_textbox(lab_rect)
            if not lab_re.search(txt or ""):
                tmp = os.path.join(crops_dir, "_lab.png")
                page.get_pixmap(dpi=300, clip=lab_rect).save(tmp)
                txt = _ocr(tmp).replace("O", "0")
                os.remove(tmp)
            m = lab_re.search(txt or "")
            if not m:
                continue
            no = prefix + m.group(1)
            crop = os.path.join(crops_dir, f"{no}.png")
            page.get_pixmap(dpi=200, clip=pymupdf.Rect(xm, ya, x1, yb) * (72 / DPI)).save(crop)
            idx[no] = dict(page=pn, crop=crop)
    json.dump(idx, open(os.path.join(crops_dir, "index.json"), "w"), indent=1)
    return idx

def render_page(pdf, pn, out_png, dpi=110):
    pymupdf.open(pdf)[pn - 1].get_pixmap(dpi=dpi).save(out_png)
    return out_png
