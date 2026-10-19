"""pd.py conventions: rare mass formats are flagged with their example numbers (offline)."""
import json, os, subprocess, sys

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "skills", "patent-drawer", "scripts")

def test_conventions(tmp_path):
    run = tmp_path / "run"; run.mkdir()
    (run / "config.json").write_text(json.dumps({"prefix": ""}))
    parts = [f"Example {n}: rac-compound {n}. LCMS m/z 400 [M+H]+." for n in range(1, 40)]
    parts.insert(20, "Example 155: (S)-compound or1. LCMS (ESI) m/z 494 [M+1]+.")
    txt = tmp_path / "t.txt"; txt.write_text("\n".join(parts * 2))
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "pd.py"), "conventions", str(run), "--text", str(txt)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    md = (run / "conventions.md").read_text()
    assert "`[M+H]+` 78" in md
    rare = md.split("Rare")[1].split("##")[0]
    assert "`[M+1]+` 2: Example 155" in rare and "[M+H]" not in rare
    assert "or1/or2: 2" in md and "rac-: 78" in md
