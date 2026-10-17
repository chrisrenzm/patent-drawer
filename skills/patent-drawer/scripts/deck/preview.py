import io, cairosvg
from rdkit import Chem, RDLogger
from rdkit.Chem.Draw import rdMolDraw2D
from PIL import Image, ImageDraw, ImageFont
import cdxtext
RDLogger.DisableLog('rdApp.*')
DPI = 300
S = DPI / 72.0
# caption fonts: Arial (macOS / Windows) or Liberation Sans (Linux), else Pillow's built-in font
FONTS = ['/System/Library/Fonts/Supplemental/Arial.ttf', 'C:/Windows/Fonts/arial.ttf',
         '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', 'Arial.ttf', 'LiberationSans-Regular.ttf']
FONTS_B = ['/System/Library/Fonts/Supplemental/Arial Bold.ttf', 'C:/Windows/Fonts/arialbd.ttf',
           '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf', 'Arial Bold.ttf', 'LiberationSans-Bold.ttf']


def _font(names, size):
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            pass
    return ImageFont.load_default(size)
PT = 10  # caption font size, points

def mols(data: bytes):
    p = Chem.CDXMLParserParams(); p.format = Chem.CDXMLFormat.CDX; p.sanitize = False; p.removeHs = False
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix='.cdx', delete=False) as f:
        f.write(data); fn = f.name
    try:
        return [m for m in Chem.MolsFromCDXMLFile(fn, p) if m is not None]
    finally:
        os.unlink(fn)

def mol_png(m, data=None):
    try:
        Chem.SanitizeMol(m); Chem.Kekulize(m, clearAromaticFlags=True)
    except Exception:
        m.UpdatePropertyCache(False)
    if data is not None:
        m = apply_wedges(m, data)
    from rdkit.Chem import rdAbbreviations
    ab = [a for a in rdAbbreviations.GetDefaultAbbreviations() if a.label in ('CF3',)]
    try:
        m = rdAbbreviations.CondenseMolAbbreviations(m, ab, maxCoverage=0.6)
    except Exception:
        pass
    d = rdMolDraw2D.MolDraw2DSVG(-1, -1)
    rdMolDraw2D.SetACS1996Mode(d.drawOptions(), rdMolDraw2D.MeanBondLength(m) or 1.5)
    d.drawOptions().prepareMolsBeforeDrawing = False
    d.drawOptions().clearBackground = True
    d.DrawMolecule(m)
    d.FinishDrawing()
    png = cairosvg.svg2png(bytestring=d.GetDrawingText().encode(), scale=S)
    return Image.open(io.BytesIO(png)).convert('RGBA')

def render(data: bytes) -> Image.Image:
    ms = mols(data)
    if not ms:
        raise ValueError('no structure found in CDX')
    m = ms[0]
    for extra in ms[1:]:
        m = Chem.CombineMols(m, extra)
    mi = mol_png(m, data if len(ms) == 1 else None)
    caps = cdxtext.lines(data)
    f = _font(FONTS, int(PT * S)); fb = _font(FONTS_B, int(PT * S))
    lh = int(PT * 1.18 * S)
    widths = [(fb if b else f).getlength(t) for t, b in caps]
    W = int(max([mi.width] + widths) + 8 * S)
    H = mi.height + int(4 * S) + lh * len(caps) + int(4 * S)
    img = Image.new('RGBA', (W, H), (255, 255, 255, 255))
    img.alpha_composite(mi, ((W - mi.width) // 2, 0))
    dr = ImageDraw.Draw(img)
    y = mi.height + int(4 * S)
    for (t, b), w in zip(caps, widths):
        dr.text(((W - w) / 2, y), t, font=fb if b else f, fill='black'); y += lh
    return img.convert('RGB')


import numpy as np, cdxbonds
from rdkit.Chem import rdmolops

def apply_wedges(m, data):
    """Copy ChemDraw wedge/hash bonds onto the RDKit mol (RDKit's CDX reader drops them)."""
    nodes, bonds = cdxbonds.parse(data)
    wed = [(b, e, d) for b, e, d in bonds if d in (3, 4, 6, 7) and b in nodes and e in nodes]
    if not wed:
        return m
    P = m.GetConformer().GetPositions()[:, :2] * np.array([1, -1])
    lc = [np.hypot(*np.subtract(nodes[b], nodes[e])) for b, e, _ in bonds if b in nodes and e in nodes]
    lr = [np.linalg.norm(P[x.GetBeginAtomIdx()] - P[x.GetEndAtomIdx()]) for x in m.GetBonds()]
    k = np.median(lc) / np.median(lr)
    Q = P * k
    ids = list(nodes); N = np.array([nodes[i] for i in ids])
    off = np.median(N, 0) - np.median(Q, 0)
    for _ in range(3):  # refine offset from nearest matches
        near = [np.argmin(np.linalg.norm(Q + off - n, axis=1)) for n in N]
        off = np.median(N - Q[near], 0)
    amap = {}
    for i, n in zip(ids, N):
        dist = np.linalg.norm(Q + off - n, axis=1); j = int(np.argmin(dist))
        if dist[j] < 0.3 * np.median(lc):
            amap[i] = j
    rw = Chem.RWMol(m)
    for b, e, d in wed:
        if b not in amap or e not in amap: continue
        a1, a2 = amap[b], amap[e]
        if d in (4, 7): a1, a2 = a2, a1          # "End" variants: narrow end at the end atom
        bd = rw.GetBondBetweenAtoms(a1, a2)
        if bd is None: continue
        if bd.GetBeginAtomIdx() != a1:
            bt = bd.GetBondType(); rw.RemoveBond(a1, a2); rw.AddBond(a1, a2, bt); bd = rw.GetBondBetweenAtoms(a1, a2)
        bd.SetBondDir(Chem.BondDir.BEGINWEDGE if d in (6, 7) else Chem.BondDir.BEGINDASH)
    return rw.GetMol()

if __name__ == '__main__':
    import sys
    for fn in sys.argv[1:]:
        im = render(open(fn, 'rb').read()); im.save(fn.rsplit('.', 1)[0] + '_preview.png', dpi=(DPI, DPI)); print(fn, im.size)
