import os
"""Round trip: hand-drawn card -> SMILES -> draw_card -> same InChIKey."""
import sys
from pathlib import Path

import pytest
from rdkit import Chem

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "skills" / "patent-drawer" / "scripts"))
from draw_card import draw_card  # noqa: E402

# Optional folder of hand-drawn .cdxml reference cards; tests skip without it.
CDX = Path(os.environ.get("PATENT_DRAWER_REF_CARDS", Path(__file__).parent / "local" / "ref_cards"))
CARDS = ["A6", "A44", "A208"]  # plain, stereo (hash wedge), ethyl side chain


def _mol(path):
    return max(Chem.MolsFromCDXMLFile(str(path)), key=lambda m: m.GetNumHeavyAtoms())


@pytest.mark.parametrize("name", CARDS)
def test_round_trip(name, tmp_path):
    src = CDX / f"CYP46A1_WO3027_{name}.cdxml"
    if not src.exists():
        pytest.skip("reference card not found")
    mol = _mol(src)
    out = tmp_path / f"{name}.cdxml"
    draw_card(Chem.MolToSmiles(mol),
              [f"CYP46A1_WO3027_{name}", "CYP46A1 IC<sub>50</sub> <0.1 µM"], str(out))
    assert Chem.MolToInchiKey(_mol(out)) == Chem.MolToInchiKey(mol)
    text = out.read_text(encoding="utf-8")
    assert 'face="32">50</s>' in text and "µM" in text


def test_stereo_written_as_wedges(tmp_path):
    out = tmp_path / "s.cdxml"
    draw_card("C[C@H](N)C(=O)O", ["x"], str(out))
    text = out.read_text(encoding="utf-8")
    assert "WedgeBegin" in text or "WedgedHashBegin" in text
