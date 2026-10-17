"""End-to-end smoke test on a tiny synthetic patent (no lab files needed).

Needs network for OPSIN (www.ebi.ac.uk). Run: pytest tests/test_pipeline.py
"""
import csv, io, json, os, subprocess, sys
import pymupdf, pytest
from rdkit import Chem
from rdkit.Chem import Draw

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "skills", "patent-drawer", "scripts")
sys.path.insert(0, SCRIPTS)
import patent as P

COMPOUNDS = {  # label: (name in the "patent", true structure in the drawing)
    "A1": ("4-benzylpiperidine-4-carbonitrile", "N#CC1(Cc2ccccc2)CCNCC1"),
    # name copied wrong on purpose: the drawing is 3-chloro, the title says 2-chloro
    "A2": ("4-(2-chlorobenzyl)piperidine-4-carbonitrile", "N#CC1(Cc2cccc(Cl)c2)CCNCC1"),
}

def make_pdf(path):
    d = pymupdf.open()
    p = d.new_page()
    y = 72
    for lab, (name, _) in COMPOUNDS.items():
        p.insert_text((72, y), f"Example {lab[1:]}. Synthesis of {name.replace('1-', 'l-')} ({lab})", fontsize=9)
        y += 40
    p = d.new_page()
    p.insert_text((72, 60), "Table 1. Exemplary compounds.", fontsize=10)
    x0, xm, x1, top, h = 70, 170, 520, 80, 200
    for i, (lab, (_, smi)) in enumerate(COMPOUNDS.items()):
        ya = top + i * h
        img = Draw.MolToImage(Chem.MolFromSmiles(smi), size=(300, 180))
        buf = io.BytesIO(); img.save(buf, "PNG")
        p.insert_image(pymupdf.Rect(xm + 20, ya + 10, xm + 320, ya + 190), stream=buf.getvalue())
        p.insert_text((x0 + 30, ya + 30), lab, fontsize=12)
    for i in range(len(COMPOUNDS) + 1):
        p.draw_line((x0, top + i * h), (x1, top + i * h), width=1)
    for x in (x0, xm, x1):
        p.draw_line((x, top), (x, top + len(COMPOUNDS) * h), width=1)
    d.save(path)

def pd(*args):
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "pd.py"), *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    return r.stdout

def test_offline_pieces():
    assert P.fix_typos("4-(4-fluorohenzyl)-l-(2-x)piperidine-4-carhonitrile") == "4-(4-fluorobenzyl)-1-(2-x)piperidine-4-carbonitrile"
    assert P._label_pattern("AlO", "A") == "A10"
    assert P.mol_info("CCO")["formula"] == "C2H6O"

def test_pipeline(tmp_path):
    pdf, run = str(tmp_path / "p.pdf"), str(tmp_path / "run")
    make_pdf(pdf)
    pd("init", run, "--pdf", pdf, "--patent-id", "WO-0000000000-A1", "--prefix", "A", "--target", "TEST")
    out = pd("crops", run, "--pages", "2")
    assert "A1" in out and "A2" in out
    with open(os.path.join(run, "tracker.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["order", "patent_no", "source_tables", "pages", "activity_raw", "activity_display", "selected", "reason"])
        w.writerow([1, "A1", "Table 1", 2, "A", "<0.1 µM", "yes", "test"])
        w.writerow([2, "A2", "Table 1", 2, "A", "<0.1 µM", "yes", "test"])
    json.dump({"label_pattern": "TEST_WO0000_{patent_no}",
               "caption_lines": ["{label}", "Molecular weight: {mw:.2f}", "TEST IC<sub>50</sub> {activity_display}"],
               "title_lines": ["TEST"], "deck_name": "TEST"}, open(os.path.join(run, "spec.json"), "w"))
    pd("resolve", run)
    recs = {n: json.load(open(os.path.join(run, "records", n + ".json"))) for n in COMPOUNDS}
    assert recs["A1"]["inchikey"] == Chem.MolToInchiKey(Chem.MolFromSmiles(COMPOUNDS["A1"][1]))
    assert os.path.exists(os.path.join(run, "review", "A2.png"))
    # stand-in for the checker subagent: A1 matches, A2 needs the corrected name
    json.dump([{"no": "A1", "verdict": "match", "reason": "same"},
               {"no": "A2", "verdict": "fixed", "corrected_name": "4-(3-chlorobenzyl)piperidine-4-carbonitrile",
                "reason": "drawing shows 3-chloro"}],
              open(os.path.join(run, "batches", "batch_1.result.json"), "w"))
    pd("apply", run)
    a2 = json.load(open(os.path.join(run, "records", "A2.json")))
    assert a2["inchikey"] == Chem.MolToInchiKey(Chem.MolFromSmiles(COMPOUNDS["A2"][1]))
    assert a2["status"] == "flagged"
    pd("draw", run)
    out = pd("doublecheck", run, "--sample", "1.0")
    assert "cross-check group: 2" in out
    # stand-in for the cross-check agents
    json.dump([{"no": "A1", "verdict": "ok", "reason": "all agree"},
               {"no": "A2", "verdict": "problem", "reason": "test"}],
              open(os.path.join(run, "batches", "xc_1.result.json"), "w"))
    pd("dcapply", run)
    assert "cross-check: test" in json.load(open(os.path.join(run, "records", "A2.json")))["flags"]
    rep = pd("validate", run)
    assert "2 compounds" in rep and "A2" in rep  # A2 must be listed for the user
