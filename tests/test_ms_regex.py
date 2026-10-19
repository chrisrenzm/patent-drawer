"""Patent mass reading (no network). Run: pytest tests/test_ms_regex.py"""
import os, sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "patent-drawer", "scripts"))
import patent as P

@pytest.mark.parametrize("text, want", [
    ("LCMS (ESI) m/z 494 [M+1]+", ["494"]),
    ("MS (ESI) m/z: 520.2 [M+H]+.", ["520.2"]),
    ("HRMS [M+H]+ calcd 481.1, found 481.0", ["481.0"]),
    ("Calcd for C25H30N5O [M+H]+: 416.2, found 416.3", ["416.3"]),
    ("[M+H]+ 481.1", ["481.1"]),
    ("ESI-MS m/z 302.1 (M+H)+", ["302.1"]),
    ("MS: MH+ 455", ["455"]),
    ("MS m/z 503.2 [M+Na]+; 479.1 [M-H]-", []),
])
def test_ms_values(text, want):
    assert P.ms_values(text) == want
