"""Which compounds go to the cross-check group (offline). Run: pytest tests/test_doublecheck.py"""
import argparse, glob, json, os, sys
import pytest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "skills", "patent-drawer", "scripts")
sys.path.insert(0, SCRIPTS)
import pd

def run_dc(tmp_path, monkeypatch, n, n_flagged, sample=None):
    """n selected compounds, the first n_flagged not trusted; returns the cross-check list."""
    run = str(tmp_path)
    os.makedirs(os.path.join(run, "batches"), exist_ok=True)
    nos = [f"A{i}" for i in range(1, n + 1)]
    recs = {no: dict(label=no, status="fixed" if i < n_flagged else "trusted") for i, no in enumerate(nos)}
    monkeypatch.setattr(pd, "cfg", lambda r: {"prefix": "A"})
    monkeypatch.setattr(pd, "read_tracker", lambda r: [dict(patent_no=no, selected="yes") for no in nos])
    monkeypatch.setattr(pd, "load_rec", lambda r, no: recs[no])
    monkeypatch.setattr(pd, "save_rec", lambda r, rec: None)
    monkeypatch.setattr(pd, "card_info", lambda r, no: {})
    monkeypatch.setattr(pd.P, "example_name", lambda *x: None)
    pd.doublecheck(argparse.Namespace(run=run, sample=sample, seed=0, batch=1000))
    return [x for f in glob.glob(os.path.join(run, "batches", "xc_*.json")) for x in json.load(open(f))]

def test_under_100_checks_all(tmp_path, monkeypatch, capsys):
    xc = run_dc(tmp_path, monkeypatch, 99, 5)
    assert len(xc) == 99
    assert "<100" in capsys.readouterr().out

def test_100_or_more_samples_20pct(tmp_path, monkeypatch):
    xc = run_dc(tmp_path, monkeypatch, 150, 10)
    assert len(xc) == 10 + 28  # all flagged + ceil(0.2 * 140) trusted

def test_explicit_zero_only_flagged(tmp_path, monkeypatch):
    xc = run_dc(tmp_path, monkeypatch, 50, 3, sample=0.0)
    assert sorted(x["no"] for x in xc) == ["A1", "A2", "A3"]
    assert all(x["why"] == "flagged" for x in xc)
