"""Draw one patent compound as a ChemDraw card (.cdxml), in the style of the
reference card CYP46A1_WO3027_A6 (ACS Document 1996 settings).

    from draw_card import draw_card
    draw_card(smiles, ["Name", "CYP46A1 IC<sub>50</sub> <0.1 \u00b5M"], "out.cdxml")

    python draw_card.py "<smiles>" out.cdxml "line1" "line2" ...

The first caption line is bold; "<sub>..</sub>" marks a subscript, "<sup>..</sup>" a superscript.
"""
import math
import os
import re
import sys
from xml.sax.saxutils import escape

from rdkit import Chem
from rdkit.Chem import rdDepictor

BL = 14.4          # bond length (ACS Document 1996)
LEFT, TOP = 118.0, 118.0   # where the structure starts, as in the reference
WARN = "Chemical Interpretation is not possible for this label"

# Copied from the reference card: document header, color table, font table.
HEADER = '''<?xml version="1.0" encoding="UTF-8" ?>
<!DOCTYPE CDXML SYSTEM "https://static.chemistry.revvitycloud.com/cdxml/CDXML.dtd" >
<CDXML
 CreationProgram="ChemDraw 26.0.0.6599"
 Name="@NAME@"
 BoundingBox="@BBOX@"
 WindowPosition="0 0"
 WindowSize="0 0"
 FractionalWidths="yes"
 InterpretChemically="yes"
 ShowAtomQuery="yes"
 ShowAtomStereo="no"
 ShowAtomEnhancedStereo="yes"
 ShowAtomNumber="no"
 ShowResidueID="no"
 ShowBondQuery="yes"
 ShowBondRxn="yes"
 ShowBondStereo="no"
 ShowTerminalCarbonLabels="no"
 ShowNonTerminalCarbonLabels="no"
 HideImplicitHydrogens="no"
 LabelFont="60"
 LabelSize="10"
 LabelFace="96"
 CaptionFont="60"
 CaptionSize="10"
 HashSpacing="2.49"
 MarginWidth="1.59"
 LineWidth="0.60"
 BoldWidth="2.01"
 BondLength="14.40"
 BondSpacing="18"
 ChainAngle="120"
 LabelJustification="Auto"
 CaptionJustification="Left"
 AminoAcidTermini="HOH"
 ShowSequenceTermini="yes"
 ShowSequenceBonds="yes"
 ShowSequenceUnlinkedBranches="no"
 ShowPrimeLabels="no"
 ResidueWrapCount="40"
 PrintMargins="36 36 36 36"
 MacPrintInfo="00030000004800480000000002E70252FFF7FFF7030F025B0367052803FB00020000004800480000000002E70252000100000064000000010001010100000001270F000100010000000000000000000000000002001901900000000000400000000000000000000100000000000000000000000000000000"
 ChemPropName=""
 ChemPropFormula="Chemical formula: "
 ChemPropExactMass="Exact mass: "
 ChemPropMolWt="Molecular weight: "
 ChemPropMOverZ="m/z: "
 ChemPropAnalysis="Elemental analysis: "
 ChemPropBoilingPt="Boiling point: "
 ChemPropMeltingPt="Melting point: "
 ChemPropCritTemp="Critical temp: "
 ChemPropCritPres="Critical pres: "
 ChemPropCritVol="Critical vol: "
 ChemPropGibbs="Gibbs energy: "
 ChemPropLogP="Log P: "
 ChemPropMR="MR: "
 ChemPropHenry="Henry&apos;s law: "
 ChemPropEForm="Heat of form: "
 ChemProptPSA="tPSA: "
 ChemPropID=""
 ChemPropFragmentLabel=""
 color="0"
 bgcolor="1"
 RxnAutonumberStart="1"
 RxnAutonumberConditions="no"
 RxnAutonumberStyle="Roman"
 RxnAutonumberFormat="(#)"
 MonomerRenderingStyle="graphic"
><colortable>
<color r="1" g="1" b="1"/>
<color r="0" g="0" b="0"/>
<color r="1" g="0" b="0"/>
<color r="1" g="1" b="0"/>
<color r="0" g="1" b="0"/>
<color r="0" g="1" b="1"/>
<color r="0" g="0" b="1"/>
<color r="1" g="0" b="1"/>
</colortable><fonttable>
<font id="60" charset="x-mac-roman" name="Arial"/>
<font id="62" charset="x-mac-roman" name="Arial Bold"/>
</fonttable>'''

PAGE = '''<page
 id="%d"
 BoundingBox="0 0 540 720"
 HeaderPosition="36"
 FooterPosition="36"
 PrintTrimMarks="yes"
 HeightPages="1"
 WidthPages="1"
>'''

# --- text width (Arial, from the Mac system font if present) -----------------
_FONTS = {}


def _width(text, size, bold=False):
    key = (size, bold)
    if key not in _FONTS:
        _FONTS[key] = None
        name = "Arial Bold.ttf" if bold else "Arial.ttf"
        for d in ("/System/Library/Fonts/Supplemental", "/Library/Fonts",
                  "C:/Windows/Fonts", "/usr/share/fonts/truetype/msttcorefonts"):
            p = os.path.join(d, name)
            if os.path.exists(p):
                try:
                    from PIL import ImageFont
                    _FONTS[key] = ImageFont.truetype(p, size * 20)
                except Exception:
                    pass
                break
    f = _FONTS[key]
    if f is None:
        return 0.56 * size * len(text)
    return f.getlength(text) / 20.0


# --- 2D layout ---------------------------------------------------------------
def _min_dist(pts):
    return min((math.dist(a, b) for i, a in enumerate(pts) for b in pts[i + 1:]),
               default=99.0)


def _layout(mol, core=None):
    """2D coordinates, scaled to bond length BL, y pointing down. CoordGen first;
    if any two atoms end up too close, try RDKit's depictor with sampling.
    core = (pattern, coords): the matching atoms are held at those coordinates
    (same units as the result), so a series shares one orientation."""
    fixed = {}
    if core:
        from rdkit.Geometry import Point2D
        match = mol.GetSubstructMatch(core[0])
        fixed = {i: Point2D(x / BL * 1.5, -y / BL * 1.5)
                 for i, (x, y) in zip(match, core[1])}
    tries = [dict(coordgen=True)] + [dict(coordgen=False, seed=s) for s in (1, 2, 3, 4)]
    best = None
    for t in tries:
        m = Chem.Mol(mol)
        rdDepictor.SetPreferCoordGen(t["coordgen"])
        if t["coordgen"]:
            rdDepictor.Compute2DCoords(m, coordMap=fixed)
        else:
            rdDepictor.Compute2DCoords(m, coordMap=fixed, forceRDKit=True, nFlipsPerSample=3,
                                       nSample=50, sampleSeed=t["seed"])
        c = m.GetConformer()
        pts = [(c.GetAtomPosition(i).x, -c.GetAtomPosition(i).y)
               for i in range(m.GetNumAtoms())]
        if m.GetNumBonds():
            mean = sum(math.dist(pts[b.GetBeginAtomIdx()], pts[b.GetEndAtomIdx()])
                       for b in m.GetBonds()) / m.GetNumBonds()
            s = BL / mean
        else:
            s = BL
        pts = [(x * s, y * s) for x, y in pts]
        score = _min_dist(pts) / BL
        if best is None or score > best[0]:
            best = (score, pts)
        if score >= 0.9:
            break
    rdDepictor.SetPreferCoordGen(False)
    return best[1]


# --- caption -----------------------------------------------------------------
def _runs(line):
    """'IC<sub>50</sub> x' -> [('IC', False), ('50', 'sub'), (' x', False)]; <sup> gives 'sup'."""
    out = []
    for part in re.split(r"(<su[bp]>.*?</su[bp]>)", line):
        if part.startswith("<sub>") or part.startswith("<sup>"):
            out.append((part[5:-6], part[3:4] == "b" and "sub" or "sup"))
        elif part:
            out.append((part, False))
    return out


def _clean(line):
    # micro sign must be U+00B5 (Mac Roman safe); fix Greek mu / capital Mu
    return line.replace("\u03bc\u039c", "\u00b5M").replace("\u03bc", "\u00b5")


def _caption(lines, cx, y_top, ids, z):
    """One centered text object. Returns (xml, bbox)."""
    lines = [_clean(l) for l in lines]
    sizes = [12 if i == 0 else 10 for i in range(len(lines))]
    widths = []
    for i, l in enumerate(lines):
        w = 0.0
        for txt, sub in _runs(l):
            w += _width(txt, sizes[i] * (0.75 if sub else 1), i == 0)
        widths.append(w)
    base = y_top + 0.905 * sizes[0]
    p_y = base
    last_base = base + sum(1.15 * s for s in sizes[1:])
    wmax = max(widths)
    bbox = (cx - wmax / 2, p_y - 0.73 * sizes[0], cx + wmax / 2,
            last_base + 0.21 * sizes[-1])
    runs, starts, pos = [], [], 0
    for i, l in enumerate(lines):
        nl = "\n" if i < len(lines) - 1 else ""
        parts = _runs(l)
        for j, (txt, sub) in enumerate(parts):
            t = txt + (nl if j == len(parts) - 1 else "")
            if i == 0:
                attr = 'font="62" size="12" color="0" face="1"'
            elif sub == "sup":
                attr = 'font="60" size="10" color="0" face="64"'
            elif sub:
                attr = 'font="60" size="10" color="0" face="32"'
            else:
                attr = 'font="60" size="10" color="0"'
            runs.append("<s %s>%s</s>" % (attr, escape(t)))
        pos += sum(len(t) for t, _ in parts) + len(nl)
        starts.append(pos)
    xml = ('<t\n id="%d"\n p="%.2f %.2f"\n BoundingBox="%.2f %.2f %.2f %.2f"\n'
           ' Z="%d"\n InterpretChemically="no"\n CaptionJustification="Center"\n'
           ' Justification="Center"\n LineHeight="auto"\n LineStarts="%s"\n>%s</t>'
           % (ids, cx, p_y, *bbox, z, " ".join(map(str, starts)), "".join(runs)))
    return xml, bbox


# --- main --------------------------------------------------------------------
def _num(v):
    return ("%.2f" % v).rstrip("0").rstrip(".")


def draw_card(smiles, lines, out_path, core=None):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError("bad SMILES: %s" % smiles)
    Chem.AssignStereochemistry(mol, cleanIt=True, force=True)
    cip = {a.GetIdx(): a.GetProp("_CIPCode") for a in mol.GetAtoms()
           if a.HasProp("_CIPCode")}
    pts = _layout(mol, core)
    # wedge/hash bonds from the stereo centres, using these coordinates
    m = Chem.Mol(mol)
    conf = Chem.Conformer(m.GetNumAtoms())
    for i, (x, y) in enumerate(pts):
        conf.SetAtomPosition(i, (x, -y, 0.0))
    m.RemoveAllConformers()
    m.AddConformer(conf)
    Chem.WedgeMolBonds(m, m.GetConformer())
    Chem.Kekulize(m, clearAromaticFlags=True)

    lines = list(lines or [])
    minx = min(p[0] for p in pts)
    maxx = max(p[0] for p in pts)
    miny = min(p[1] for p in pts)
    maxy = max(p[1] for p in pts)
    # caption width decides how much room we need left/right
    cap_w = 0.0
    for i, l in enumerate(lines):
        w = sum(_width(t, (12 if i == 0 else 10) * (0.75 if s else 1), i == 0)
                for t, s in _runs(_clean(l)))
        cap_w = max(cap_w, w)
    total = max(maxx - minx, cap_w)
    ox = LEFT + (total - (maxx - minx)) / 2 - minx
    oy = TOP - miny
    pts = [(x + ox, y + oy) for x, y in pts]
    cx = LEFT + total / 2

    nid = [0]

    def new_id():
        nid[0] += 1
        return nid[0]

    page_id = new_id()
    frag_id = new_id()
    z = [0]

    def new_z():
        z[0] += 1
        return z[0]

    frag_z = new_z()
    atom_ids = [new_id() for _ in range(m.GetNumAtoms())]
    nodes, boxes = [], []
    for a in m.GetAtoms():
        i = a.GetIdx()
        x, y = pts[i]
        boxes.append((x, y, x, y))
        sym = a.GetSymbol()
        plain = (sym == "C" and a.GetFormalCharge() == 0 and a.GetIsotope() == 0
                 and a.GetNumRadicalElectrons() == 0)
        at = ['id="%d"' % atom_ids[i], 'p="%s %s"' % (_num(x), _num(y)),
              'Z="%d"' % new_z()]
        if not plain:
            at.append('Element="%d"' % a.GetAtomicNum())
            if a.GetIsotope():
                at.append('Isotope="%d"' % a.GetIsotope())
            if a.GetFormalCharge():
                at.append('Charge="%d"' % a.GetFormalCharge())
            at.append('NumHydrogens="%d"' % a.GetTotalNumHs())
        if i in cip:
            at.append('Geometry="Tetrahedral"')
        at.append('AS="%s"' % cip.get(i, "N"))
        at.append('AtomID="%d"' % (i + 1))
        inner = ""
        if not plain:
            nb = [pts[n.GetIdx()][0] - x for n in a.GetNeighbors()]
            dx = sum(nb)
            hn = a.GetTotalNumHs()
            h = "" if hn == 0 else ("H" if hn == 1 else "H%d" % hn)
            ch = a.GetFormalCharge()
            tail = "" if ch == 0 else (("+" if ch > 0 else "-") +
                                       ("" if abs(ch) == 1 else str(abs(ch))))
            right = dx > 0.5
            label = (h + sym + tail) if right else (sym + h + tail)
            if a.GetIsotope():
                label = str(a.GetIsotope()) + label
            wt = _width(label, 10)
            if right:   # atom symbol is at the end of the label
                px = x - (wt - _width(sym[-1], 10) / 2)
            else:
                px = x - _width(sym[0], 10) / 2
            py = y + 3.58
            tx = ['p="%.2f %.2f"' % (px, py),
                  'BoundingBox="%.2f %.2f %.2f %.2f"' % (px + 0.76, py - 7.16,
                                                         px + wt - 0.76, py),
                  'LabelJustification="Left"']
            if abs(dx) > 0.5:
                tx.append('LabelAlignment="%s"' % ("Right" if right else "Left"))
            inner = ('<t\n %s\n><s font="60" size="10" color="0" face="96">%s</s></t>'
                     % ("\n ".join(tx), escape(label)))
            boxes[-1] = (px + 0.76, py - 7.16, px + wt - 0.76, py)
        nodes.append("<n\n %s\n>%s</n>" % ("\n ".join(at), inner)
                     if inner else "<n\n %s\n/>" % "\n ".join(at))
    bonds = []
    for b in m.GetBonds():
        at = ['id="%d"' % new_id(), 'Z="%d"' % new_z(), 'IgnoreWarnings="yes"',
              'B="%d"' % atom_ids[b.GetBeginAtomIdx()],
              'E="%d"' % atom_ids[b.GetEndAtomIdx()]]
        order = {Chem.BondType.DOUBLE: 2, Chem.BondType.TRIPLE: 3}.get(b.GetBondType(), 1)
        if order > 1:
            at.append('Order="%d"' % order)
        d = b.GetBondDir()
        if d == Chem.BondDir.BEGINWEDGE:
            at.append('Display="WedgeBegin"')
        elif d == Chem.BondDir.BEGINDASH:
            at.append('Display="WedgedHashBegin"')
        at.append('BS="N"')
        bonds.append("<b\n %s\n/>" % "\n ".join(at))

    fb = (min(b[0] for b in boxes), min(b[1] for b in boxes),
          max(b[2] for b in boxes), max(b[3] for b in boxes))
    frag = ('<fragment\n id="%d"\n BoundingBox="%.2f %.2f %.2f %.2f"\n Z="%d"\n>%s</fragment>'
            % (frag_id, *fb, frag_z, "".join(nodes + bonds)))
    body, allb = frag, list(fb)
    if lines:
        txml, tb = _caption(lines, cx, fb[3] + 14, new_id(), new_z())
        body += txml
        allb = [min(allb[0], tb[0]), min(allb[1], tb[1]),
                max(allb[2], tb[2]), max(allb[3], tb[3])]
    head = (HEADER.replace("@NAME@", escape(os.path.basename(out_path)))
            .replace("@BBOX@", "%.2f %.2f %.2f %.2f" % tuple(allb)))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(head + PAGE % page_id + body + "</page></CDXML>")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit('usage: draw_card.py "<smiles>" out.cdxml "line1" "line2" ...')
    draw_card(sys.argv[1], sys.argv[3:], sys.argv[2])
