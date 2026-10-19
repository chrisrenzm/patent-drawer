"""Shared-core alignment: two series and one odd compound."""
import math
import sys
from pathlib import Path

from rdkit import Chem

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "skills" / "patent-drawer" / "scripts"))
import align  # noqa: E402
from draw_card import _layout, draw_card  # noqa: E402

QUINAZOLINES = {"Q1": "COc1cc2ncnc(Nc3ccc(F)cc3)c2cc1OC",
                "Q2": "COc1cc2ncnc(Nc3cccc(Cl)c3)c2cc1OCCN1CCOCC1",
                "Q3": "COc1cc2ncnc(N3CCN(C)CC3)c2cc1OC"}
INDOLES = {"I1": "O=C(NCc1ccccc1)c1cc2ccccc2n1C",
           "I2": "O=C(N1CCCC1)c1cc2cc(Cl)ccc2n1C"}
ODD = {"X1": "CCCCCCO"}


def test_series_found():
    cores = align.find_cores({**QUINAZOLINES, **INDOLES, **ODD})
    groups = sorted(sorted(c["members"]) for c in cores)
    assert groups == [sorted(INDOLES), sorted(QUINAZOLINES)]
    assert align.core_for(ODD["X1"], cores) is None


def test_core_same_orientation_and_structure_kept(tmp_path):
    cores = align.find_cores(QUINAZOLINES)
    for no, smi in QUINAZOLINES.items():
        core = align.core_for(smi, cores)
        mol = Chem.MolFromSmiles(smi)
        pts = _layout(mol, core)
        got = [pts[i] for i in mol.GetSubstructMatch(core[0])]
        dx, dy = got[0][0] - core[1][0][0], got[0][1] - core[1][0][1]
        assert max(math.dist((x - dx, y - dy), r) for (x, y), r in zip(got, core[1])) < 2.0
        out = tmp_path / f"{no}.cdxml"
        draw_card(smi, [no], str(out), core)
        back = max(Chem.MolsFromCDXMLFile(str(out)), key=lambda m: m.GetNumAtoms())
        assert Chem.MolToInchiKey(back) == Chem.MolToInchiKey(mol)
