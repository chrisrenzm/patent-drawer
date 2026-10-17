import os
"""Deck builder: hand-drawn .cdxml cards -> .pptx with ChemDraw OLE objects."""
import io
import re
import shutil
import sys
import zipfile
from pathlib import Path

import olefile
import pytest
from rdkit import Chem

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "skills" / "patent-drawer" / "scripts" / "deck"))
import build_deck, cdxml2cdx, cdxtext  # noqa: E402

# Optional folder of hand-drawn .cdxml reference cards; tests skip without it.
CDX = Path(os.environ.get("PATENT_DRAWER_REF_CARDS", Path(__file__).parent / "local" / "ref_cards"))
CARDS = ["A6", "A10", "A44"]  # plain, OCF3 nickname, stereo wedge
CHEMDRAW_CLSID = "41BA6D21-A02E-11CE-8FD9-0020AFD1F20C"


@pytest.fixture
def cards(tmp_path):
    src = [CDX / f"CYP46A1_WO3027_{n}.cdxml" for n in CARDS]
    if not all(p.exists() for p in src):
        pytest.skip("reference cards not found")
    d = tmp_path / "cards"
    d.mkdir()
    for p in src:
        shutil.copy(p, d)
    return d


def _keys(path, fmt):
    p = Chem.CDXMLParserParams()
    p.format = fmt
    return [Chem.MolToInchiKey(m) for m in Chem.MolsFromCDXMLFile(str(path), p) if m is not None]


def test_cdxml_to_cdx(cards, tmp_path):
    for src in sorted(cards.iterdir()):
        out = tmp_path / (src.stem + ".cdx")
        data = cdxml2cdx.convert_file(str(src), str(out))
        assert _keys(out, Chem.CDXMLFormat.CDX) == _keys(src, Chem.CDXMLFormat.CDXML)
        lines = [t for t, _ in cdxtext.lines(data)]
        assert lines[0] == src.stem and any(t.startswith("Molecular weight") for t in lines)


def test_build_deck(cards, tmp_path):
    out = tmp_path / "deck.pptx"
    report = build_deck.build(str(cards), str(out), ["Test deck"])
    assert len(report) == 3
    z = zipfile.ZipFile(out)
    assert z.testzip() is None
    slides = [n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
    assert len(slides) == 2  # title + one card slide
    pres = z.read("ppt/presentation.xml").decode()
    assert pres.count("<p:sldId ") == 2
    card_slide = z.read("ppt/slides/slide2.xml").decode()
    assert card_slide.count('progId="ChemDraw.Document.6.0"') == 2 * 3  # Choice + Fallback per card
    bins = [n for n in z.namelist() if n.startswith("ppt/embeddings/")]
    assert len(bins) == 3
    for n in bins:
        ole = olefile.OleFileIO(io.BytesIO(z.read(n)))
        assert ole.root.clsid == CHEMDRAW_CLSID
        assert b"ChemDraw.Document.6.0" in ole.openstream("\x01CompObj").read()
        assert ole.openstream("CONTENTS").read()[:8] == b"VjCD0100"
    assert "Test deck" in z.read("ppt/slides/slide1.xml").decode()


def test_grid_and_template(cards, tmp_path):
    out = tmp_path / "deck.pptx"
    build_deck.build(str(cards), str(out), cols=2, rows=1, template=build_deck.DEFAULT_TEMPLATE)
    z = zipfile.ZipFile(out)
    assert len([n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]) == 3  # title + 2 + 1
    # the generated deck can itself serve as a template: its old slides are dropped
    out2 = tmp_path / "deck2.pptx"
    build_deck.build(str(cards), str(out2), template=str(out))
    z2 = zipfile.ZipFile(out2)
    assert len([n for n in z2.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]) == 2
    assert len([n for n in z2.namelist() if n.startswith("ppt/embeddings/")]) == 3
