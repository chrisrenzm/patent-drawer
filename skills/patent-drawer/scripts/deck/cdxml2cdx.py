"""Convert a ChemDraw .cdxml file to binary .cdx (no outside libraries).

Covers what our ChemDraw cards use: document style settings, color and font
tables, page, fragment, nodes (incl. nested nickname fragments and external
connection points), bonds (order, stereo display), text with styled runs, groups
and chemical-property links. Unknown elements and attributes are skipped.

usage: python cdxml2cdx.py in.cdxml [out.cdx]
"""
import struct, sys
import xml.etree.ElementTree as ET

HEADER = b'VjCD0100' + b'\x04\x03\x02\x01' + b'\0' * 10

OBJ = {'CDXML': 0x8000, 'page': 0x8001, 'group': 0x8002, 'fragment': 0x8003,
       'n': 0x8004, 'b': 0x8005, 't': 0x8006, 'chemicalproperty': 0x8020}

JUST = {'Right': -1, 'Left': 0, 'Center': 1, 'Full': 2, 'Above': 3, 'Below': 4, 'Auto': 5, 'BestInitial': 6}
NODETYPE = {'Unspecified': 0, 'Element': 1, 'ElementList': 2, 'ElementListNickname': 3, 'Nickname': 4,
            'Fragment': 5, 'Formula': 6, 'GenericNickname': 7, 'AnonymousAlternativeGroup': 8,
            'NamedAlternativeGroup': 9, 'MultiAttachment': 10, 'VariableAttachment': 11,
            'ExternalConnectionPoint': 12, 'LinkNode': 13}
GEOMETRY = {g: i for i, g in enumerate(
    'Unknown 1Ligand Linear Bent TrigonalPlanar TrigonalPyramidal SquarePlanar Tetrahedral '
    'TrigonalBipyramidal SquarePyramidal 5Ligand Octahedral 6Ligand 7Ligand 8Ligand 9Ligand 10Ligand'.split())}
ATOM_CIP = {'U': 0, 'N': 1, 'R': 2, 'S': 3, 'r': 4, 's': 5, 'u': 6}
BOND_CIP = {'U': 0, 'N': 1, 'E': 2, 'Z': 3}
DISPLAY = {d: i for i, d in enumerate(
    'Solid Dash Hash WedgedHashBegin WedgedHashEnd Bold WedgeBegin WedgeEnd Wavy HollowWedgeBegin '
    'HollowWedgeEnd WavyWedgeBegin WavyWedgeEnd Dot DashDot'.split())}
ORDER = {'1': 1, '2': 2, '3': 4, '4': 8, '5': 16, '6': 32, '0.5': 64, '1.5': 128, '2.5': 256,
         '3.5': 512, '4.5': 1024, '5.5': 2048, 'dative': 4096, 'ionic': 8192, 'hydrogen': 16384,
         'threecenter': 32768}
DOUBLEPOS = {'Center': 0, 'Right': 1, 'Left': 2}
POSITIONING = {'auto': 0, 'angle': 1, 'offset': 2, 'absolute': 3}
# characters that cp1252 cannot hold
TEXTFIX = {'μ': 'µ', 'Μ': 'M', '≤': '<=', '≥': '>=', ' ': ' ', ' ': ' ',
           '−': '-', '–': '-', '—': '-'}


def _fix(v):
    return int(round(float(v) * 65536))


def _point(v):
    x, y = v.split()[:2]
    return struct.pack('<ii', _fix(y), _fix(x))


def _rect(v):
    l, t, r, b = v.split()[:4]
    return struct.pack('<iiii', _fix(t), _fix(l), _fix(b), _fix(r))


def _str(v):
    return b'\0\0' + _enc(v)


def _enc(s):
    for a, b in TEXTFIX.items():
        s = s.replace(a, b)
    return s.replace('\r\n', '\r').replace('\n', '\r').encode('cp1252', 'replace')


def _ids(v):
    return b''.join(struct.pack('<i', int(x)) for x in v.split())


def _bool(v):
    return bytes([v == 'yes'])


def _enum(table, fmt):
    return lambda v: struct.pack(fmt, table[v])


i8 = lambda v: struct.pack('<b', int(float(v)))
u8 = lambda v: struct.pack('<B', int(float(v)))
i16 = lambda v: struct.pack('<h', int(float(v)))
u16 = lambda v: struct.pack('<H', int(float(v)))
i32 = lambda v: struct.pack('<i', int(float(v)))
coord = lambda v: struct.pack('<i', _fix(v))
FLAG = 'flag'  # zero-length property, present only when "yes"

# attribute -> (tag, encoder). Shared by every object; sizes follow ChemDraw's own writer.
ATTR = {
    'CreationProgram': (0x0003, _str), 'Name': (0x0008, _str), 'Z': (0x000A, i16),
    'IgnoreWarnings': (0x000F, FLAG), 'Warning': (0x0010, _str),
    'p': (0x0200, _point), 'BoundingBox': (0x0204, _rect),
    'color': (0x0301, u16), 'bgcolor': (0x0302, u16),
    'NodeType': (0x0400, _enum(NODETYPE, '<h')), 'Element': (0x0402, i16), 'Isotope': (0x0420, i16),
    'Charge': (0x0421, i8), 'NumHydrogens': (0x042B, u16), 'Geometry': (0x0430, _enum(GEOMETRY, '<b')),
    'BondOrdering': (0x0431, _ids), 'AS': (0x0437, _enum(ATOM_CIP, '<b')), 'NeedsClean': (0x0448, FLAG),
    'ExternalConnectionNum': (0x044B, i8), 'AtomID': (0x044D, i32),
    'ShowAtomQuery': (0x043A, _bool), 'ShowAtomStereo': (0x043B, _bool), 'ShowAtomNumber': (0x043C, _bool),
    'ShowTerminalCarbonLabels': (0x0442, _bool), 'ShowNonTerminalCarbonLabels': (0x0443, _bool),
    'HideImplicitHydrogens': (0x0444, _bool), 'ShowAtomEnhancedStereo': (0x0445, _bool),
    'ShowResidueID': (0x044A, _bool),
    'Order': (0x0600, lambda v: struct.pack('<H', sum(ORDER[o] for o in v.split()))),
    'Display': (0x0601, _enum(DISPLAY, '<h')), 'DoublePosition': (0x0603, _enum(DOUBLEPOS, '<h')),
    'B': (0x0604, i32), 'E': (0x0605, i32), 'BS': (0x060A, _enum(BOND_CIP, '<b')),
    'BondCircularOrdering': (0x060B, _ids), 'ShowBondQuery': (0x060C, _bool),
    'ShowBondStereo': (0x060D, _bool), 'CrossingBonds': (0x060E, _ids), 'ShowBondRxn': (0x060F, _bool),
    'Justification': (0x0701, _enum(JUST, '<b')),
    'LineHeight': (0x0702, lambda v: struct.pack('<H', {'variable': 0, 'auto': 1}.get(v) or int(float(v) * 20))),
    'WordWrapWidth': (0x0703, lambda v: struct.pack('<H', int(float(v)))),
    'LineStarts': (0x0704, lambda v: struct.pack('<H', len(v.split())) + b''.join(struct.pack('<H', int(x)) for x in v.split())),
    'LabelAlignment': (0x0705, _enum(JUST, '<b')), 'InterpretChemically': (0x0708, _bool),
    'MacPrintInfo': (0x0800, bytes.fromhex), 'PrintMargins': (0x0802, _rect),
    'ChainAngle': (0x0803, coord), 'BondSpacing': (0x0804, lambda v: struct.pack('<h', int(round(float(v) * 10)))),
    'BondLength': (0x0805, coord), 'BoldWidth': (0x0806, coord), 'LineWidth': (0x0807, coord),
    'MarginWidth': (0x0808, coord), 'HashSpacing': (0x0809, coord),
    'CaptionJustification': (0x080C, _enum(JUST, '<b')), 'FractionalWidths': (0x080D, _bool),
    'Magnification': (0x080E, i16), 'WidthPages': (0x080F, i16), 'HeightPages': (0x0810, i16),
    'HeaderPosition': (0x0816, coord), 'FooterPosition': (0x0818, coord), 'PrintTrimMarks': (0x0819, FLAG),
    'LabelJustification': (0x0823, _enum(JUST, '<b')),
    'ShowSequenceTermini': (0x0829, _bool), 'ShowSequenceBonds': (0x082A, _bool),
    'ResidueWrapCount': (0x082B, u8), 'ShowSequenceUnlinkedBranches': (0x0832, _bool),
    'WindowPosition': (0x0901, _point), 'WindowSize': (0x0902, _point),
    'BasisObjects': (0x0B82, _ids), 'ChemicalPropertyType': (0x0BB0, _ids),
    'ChemicalPropertyDisplayID': (0x0BB1, i32), 'ChemicalPropertyIsActive': (0x0BB2, FLAG),
    'RxnAutonumberStart': (0x0C0B, i16), 'RxnAutonumberConditions': (0x0C0A, _bool),
    'RxnAutonumberFormat': (0x0C0C, _str),
    'PositioningType': (0x0D06, _enum(POSITIONING, '<b')), 'PositioningOffset': (0x0D08, _point),
}
for _i, _n in enumerate('Name Formula ExactMass MolWt MOverZ Analysis BoilingPt MeltingPt CritTemp CritPres '
                        'CritVol Gibbs LogP MR Henry EForm tPSA CLogP CMR LogS PKa ID FragmentLabel'.split()):
    ATTR['ChemProp' + _n] = (0x0BB4 + _i, _str)


def _prop(tag, data):
    if len(data) >= 0xFFFF:
        return struct.pack('<HHI', tag, 0xFFFF, len(data)) + data
    return struct.pack('<HH', tag, len(data)) + data


def _attrs(el, skip=()):
    out = b''
    for k, v in el.attrib.items():
        if k in skip or k not in ATTR:
            continue
        tag, enc = ATTR[k]
        if enc is FLAG:
            if v == 'yes':
                out += _prop(tag, b'')
            continue
        try:
            out += _prop(tag, enc(v))
        except (KeyError, ValueError):
            pass  # value we do not know how to encode: leave it out
    return out


def _styled_text(t):
    """<s> runs of a text object -> CDX styled string (property 0x0700)."""
    runs, text = [], b''
    for s in t.findall('s'):
        size = int(round(float(s.get('size', '10')) * 20))
        runs.append(struct.pack('<HHHHH', len(text), int(s.get('font', '0')), int(s.get('face', '0')),
                                size, int(s.get('color', '0')) & 0xFFFF))
        text += _enc(s.text or '')
    if not runs:
        return b''
    return _prop(0x0700, struct.pack('<H', len(runs)) + b''.join(runs) + text)


def _colortable(el):
    cols = el.findall('color')
    body = struct.pack('<H', len(cols))
    for c in cols:
        body += struct.pack('<HHH', *(int(round(float(c.get(k, '0')) * 65535)) for k in 'rgb'))
    return _prop(0x0300, body)


def _fonttable(el):
    fonts = el.findall('font')
    body = struct.pack('<HH', 0, len(fonts))
    for f in fonts:
        name = f.get('name', 'Arial').encode('cp1252', 'replace')
        # text is written as Windows-1252, so every font says so (as ChemDraw for Windows does)
        body += struct.pack('<HHH', int(f.get('id')), 1252, len(name)) + name
    return _prop(0x0100, body)


def _style(el, prefix, tag):
    """Document LabelFont/LabelSize/LabelFace -> one CDX font-style property."""
    if el.get(prefix + 'Font') is None:
        return b''
    return _prop(tag, struct.pack('<HHHH', int(el.get(prefix + 'Font')), int(el.get(prefix + 'Face', '0')),
                                  int(round(float(el.get(prefix + 'Size', '10')) * 20)), 0))


def _obj(el):
    tag = OBJ.get(el.tag)
    if tag is None:
        return b''
    out = struct.pack('<HI', tag, int(el.get('id', '0')))
    out += _attrs(el)
    if el.tag == 'CDXML':
        out += _style(el, 'Label', 0x080A) + _style(el, 'Caption', 0x080B)
    if el.tag == 't':
        out += _styled_text(el)
    for ch in el:
        if ch.tag == 'colortable':
            out += _colortable(ch)
        elif ch.tag == 'fonttable':
            out += _fonttable(ch)
        else:
            out += _obj(ch)
    return out + b'\0\0'


def convert(cdxml_text):
    """CDXML (str or bytes) -> CDX bytes."""
    if isinstance(cdxml_text, str):
        cdxml_text = cdxml_text.encode('utf-8')
    root = ET.fromstring(cdxml_text)
    if root.tag != 'CDXML':
        raise ValueError('not a CDXML document')
    return HEADER + _obj(root) + b'\0\0'


def convert_file(src, dst=None):
    data = convert(open(src, 'rb').read())
    if dst:
        open(dst, 'wb').write(data)
    return data


if __name__ == '__main__':
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else src.rsplit('.', 1)[0] + '.cdx'
    print(dst, len(convert_file(src, dst)), 'bytes')
