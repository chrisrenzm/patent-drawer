"""Build a PowerPoint deck from a folder of ChemDraw cards (.cdx or .cdxml).
Every card becomes a real ChemDraw OLE object (double-click to edit in ChemDraw on Windows).

usage: python build_deck.py CARD_DIR OUT.pptx ["Title line 1" "Title line 2" ...]
                            [--template my.pptx] [--cols 5] [--rows 3]

Slide 1 is a title slide; then cols x rows cards per slide, in natural file-name order.
--template uses your own deck's look and slide size (its existing slides are dropped);
it needs a title layout and a blank layout (falls back to the first/last layout).
"""
import argparse, html, io, os, posixpath, re, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cdxload, oleobj, preview  # noqa: E402

DEFAULT_TEMPLATE = os.path.join(HERE, '..', '..', 'templates', 'default_deck.pptx')
EMU_PER_PX = 914400 / preview.DPI
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL_OLE, REL_IMG, REL_SLIDE, REL_LAYOUT = R + '/oleObject', R + '/image', R + '/slide', R + '/slideLayout'
CT_SLIDE = 'application/vnd.openxmlformats-officedocument.presentationml.slide+xml'
NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="' + R + '" '
      'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')
XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
GROUP = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm>'
         '<a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')
# parts that only belong to the template's own slides
SLIDE_RELS = (REL_SLIDE, R + '/notesSlide', R + '/comments', R + '/changesInfo', R + '/revisionInfo')


def natural(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s)]


def rels_path(part):
    d, f = posixpath.split(part)
    return posixpath.join(d, '_rels', f + '.rels')


def read_rels(parts, part):
    """[(id, type, absolute target)] of one part."""
    x = parts.get(rels_path(part))
    if x is None:
        return []
    out = []
    for m in re.finditer(rb'<Relationship\b[^>]*>', x):
        a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(0).decode()))
        if a.get('TargetMode') == 'External':
            continue
        out.append((a['Id'], a['Type'], posixpath.normpath(posixpath.join(posixpath.dirname(part), a['Target']))))
    return out


def rels_xml(items):
    return (XML_HEAD + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + ''.join(f'<Relationship Id="{i}" Type="{t}" Target="{g}"/>' for i, t, g in items) + '</Relationships>').encode()


def load_template(path):
    """Template parts minus its slides (and whatever only the slides used)."""
    z = zipfile.ZipFile(path)
    parts = {n: z.read(n) for n in z.namelist()}
    keep, todo = set(), [(t, g) for _, t, g in _root_rels(parts)]
    while todo:  # walk relationships from the package root, never into slides
        typ, tgt = todo.pop()
        if typ in SLIDE_RELS or tgt in keep or tgt not in parts:
            continue
        keep.add(tgt)
        todo += [(t, g) for _, t, g in read_rels(parts, tgt)]
    keep |= {'[Content_Types].xml', '_rels/.rels'}
    keep |= {rels_path(p) for p in list(keep) if rels_path(p) in parts}
    return {n: b for n, b in parts.items() if n in keep}


def _root_rels(parts):
    out = []
    for m in re.finditer(rb'<Relationship\b[^>]*>', parts['_rels/.rels']):
        a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(0).decode()))
        out.append((a['Id'], a['Type'], a['Target'].lstrip('/')))
    return out


def find_layouts(parts):
    layouts = sorted([n for n in parts if re.match(r'ppt/slideLayouts/slideLayout\d+\.xml$', n)], key=natural)
    if not layouts:
        raise SystemExit('template has no slide layouts')
    def typ(n):
        m = re.search(rb'<p:sldLayout\b[^>]*\btype="(\w+)"', parts[n])
        return m.group(1).decode() if m else ''
    title = next((n for n in layouts if typ(n) == 'title'), layouts[0])
    blank = next((n for n in layouts if typ(n) == 'blank'), layouts[-1])
    return title, blank


def title_slide(layout_xml, lines):
    has_sub = b'type="subTitle"' in layout_xml
    kind = 'ctrTitle' if b'type="ctrTitle"' in layout_xml else 'title'
    def ph(i, t, idx, texts):
        paras = ''.join(f'<a:p><a:r><a:rPr lang="en-US" dirty="0"/><a:t>{html.escape(s)}</a:t></a:r></a:p>' for s in texts)
        return (f'<p:sp><p:nvSpPr><p:cNvPr id="{i}" name="{t} {i}"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
                f'<p:nvPr><p:ph type="{t}"{idx}/></p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>{paras}</p:txBody></p:sp>')
    body = ph(2, kind, '', lines[:1] if has_sub else lines)
    if has_sub and lines[1:]:
        body += ph(3, 'subTitle', ' idx="1"', lines[1:])
    return f'{XML_HEAD}<p:sld {NS}><p:cSld><p:spTree>{GROUP}{body}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'


def ole_frame(shape_id, name, rid_ole, rid_img, x, y, cx, cy):
    ole = f'<p:oleObj name="CS ChemDraw Drawing" r:id="{rid_ole}" imgW="{cx}" imgH="{cy}" progId="ChemDraw.Document.6.0"><p:embed/>'
    return (
        f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{shape_id}" name="{html.escape(name)}"/>'
        f'<p:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></p:cNvGraphicFramePr><p:nvPr/></p:nvGraphicFramePr>'
        f'<p:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></p:xfrm>'
        f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/presentationml/2006/ole">'
        f'<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
        f'<mc:Choice xmlns:v="urn:schemas-microsoft-com:vml" Requires="v">{ole}</p:oleObj></mc:Choice><mc:Fallback>{ole}'
        f'<p:pic><p:nvPicPr><p:cNvPr id="0" name=""/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>'
        f'<p:blipFill><a:blip r:embed="{rid_img}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic></p:oleObj>'
        f'</mc:Fallback></mc:AlternateContent></a:graphicData></a:graphic></p:graphicFrame>')


def build(card_dir, out, title_lines=None, template=None, cols=5, rows=3):
    files = sorted([f for f in os.listdir(card_dir) if f.lower().endswith(('.cdx', '.cdxml'))], key=natural)
    if not files:
        raise SystemExit('no .cdx/.cdxml files in ' + card_dir)
    title_lines = title_lines or ['ChemDraw structures']
    parts = load_template(template or DEFAULT_TEMPLATE)
    pres = parts['ppt/presentation.xml'].decode()
    W, H = (int(v) for v in re.search(r'<p:sldSz cx="(\d+)" cy="(\d+)"', pres).groups())
    title_layout, blank_layout = find_layouts(parts)
    per_slide = cols * rows
    margin = int(min(W, H) * 0.02)
    cell_w, cell_h = (W - 2 * margin) / cols, (H - 2 * margin) / rows

    slides = [(title_slide(parts[title_layout], title_lines).encode(), [('rId1', REL_LAYOUT, '../slideLayouts/' + posixpath.basename(title_layout))])]
    report, k = [], 0
    for si in range(0, len(files), per_slide):
        frames, rels = [], [('rId1', REL_LAYOUT, '../slideLayouts/' + posixpath.basename(blank_layout))]
        for j, fn in enumerate(files[si:si + per_slide]):
            k += 1
            data = cdxload.load(os.path.join(card_dir, fn))
            img = preview.render(data)
            buf = io.BytesIO()
            img.save(buf, 'PNG', dpi=(preview.DPI, preview.DPI))
            parts[f'ppt/embeddings/oleObject{k}.bin'] = oleobj.make(data)
            parts[f'ppt/media/chemdraw{k}.png'] = buf.getvalue()
            cx, cy = img.width * EMU_PER_PX, img.height * EMU_PER_PX
            sc = min(1.0, 0.97 * cell_w / cx, 0.97 * cell_h / cy)
            cx, cy = int(cx * sc), int(cy * sc)
            col, row = j % cols, j // cols
            x = int(margin + cell_w * (col + 0.5) - cx / 2)
            y = int(margin + cell_h * (row + 0.5) - cy / 2)
            ro, ri = f'rId{2 * j + 2}', f'rId{2 * j + 3}'
            rels += [(ro, REL_OLE, f'../embeddings/oleObject{k}.bin'), (ri, REL_IMG, f'../media/chemdraw{k}.png')]
            frames.append(ole_frame(j + 2, os.path.splitext(fn)[0], ro, ri, x, y, cx, cy))
            report.append((fn, len(slides) + 1, len(data)))
        xml = f'{XML_HEAD}<p:sld {NS}><p:cSld><p:spTree>{GROUP}{"".join(frames)}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'
        slides.append((xml.encode(), rels))

    # presentation.xml + its rels
    prels = read_rels(parts, 'ppt/presentation.xml')
    prels = [(i, t, posixpath.relpath(g, 'ppt')) for i, t, g in prels if t not in SLIDE_RELS]
    nid = max([int(i[3:]) for i, _, _ in prels if i[3:].isdigit()] + [0]) + 1
    ids = []
    for n, (xml, rels) in enumerate(slides, 1):
        parts[f'ppt/slides/slide{n}.xml'] = xml
        parts[f'ppt/slides/_rels/slide{n}.xml.rels'] = rels_xml(rels)
        rid = f'rId{nid + n - 1}'
        prels.append((rid, REL_SLIDE, f'slides/slide{n}.xml'))
        ids.append(f'<p:sldId id="{255 + n}" r:id="{rid}"/>')
    pres = re.sub(r'<p:sldIdLst>.*?</p:sldIdLst>|<p:sldIdLst/>|<p:custShowLst>.*?</p:custShowLst>', '', pres, flags=re.S)
    pres = re.sub(r'<p:ext uri="\{521415D9-36F7-43E2-AB2F-B90AF26B5E84\}">.*?</p:ext>', '', pres, flags=re.S)  # sections
    pres = pres.replace('<p:sldSz', '<p:sldIdLst>' + ''.join(ids) + '</p:sldIdLst><p:sldSz', 1)
    parts['ppt/presentation.xml'] = pres.encode()
    parts['ppt/_rels/presentation.xml.rels'] = rels_xml(prels)

    # content types: drop overrides for parts we removed, add ours
    ct = parts['[Content_Types].xml'].decode()
    ct = re.sub(r'<Override PartName="/([^"]+)"[^>]*/>', lambda m: m.group(0) if m.group(1) in parts and
                not m.group(1).startswith('ppt/slides/') else '', ct)
    for ext, typ in (('png', 'image/png'), ('bin', 'application/vnd.openxmlformats-officedocument.oleObject')):
        if f'Extension="{ext}"' not in ct:
            ct = ct.replace('<Default ', f'<Default Extension="{ext}" ContentType="{typ}"/><Default ', 1)
    ct = ct.replace('</Types>', ''.join(f'<Override PartName="/ppt/slides/slide{n}.xml" ContentType="{CT_SLIDE}"/>'
                                        for n in range(1, len(slides) + 1)) + '</Types>')
    parts['[Content_Types].xml'] = ct.encode()

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zo:
        zo.writestr('[Content_Types].xml', parts.pop('[Content_Types].xml'))
        for n, b in parts.items():
            zo.writestr(n, b)
    return report


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('card_dir')
    ap.add_argument('out')
    ap.add_argument('title', nargs='*')
    ap.add_argument('--template', help='your own .pptx to take layouts, theme and slide size from')
    ap.add_argument('--cols', type=int, default=5)
    ap.add_argument('--rows', type=int, default=3)
    a = ap.parse_args()
    r = build(a.card_dir, a.out, a.title, a.template, a.cols, a.rows)
    print(f'{len(r)} structures on {r[-1][1] - 1} slide(s) -> {a.out}')
