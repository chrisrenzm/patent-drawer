"""Review sheet: patent drawing next to our card, one PDF, flagged compounds first.

usage: python contact_sheet.py tracker.csv cdx_dir crops_dir out.pdf

tracker.csv needs patent_no; status (or validation_status) and flags are shown when present.
Crops are crops_dir/<patent_no>.png. Our card is the .cdx/.cdxml in cdx_dir whose name
ends with _<patent_no> (or equals the tracker's label / file column).
"""
import csv, os, re, sys
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'deck'))
import cdxload, preview  # noqa: E402

DPI = 100
PAGE_W, PAGE_H = int(11 * DPI), int(8.5 * DPI)   # US letter, landscape
ROWS = 3
MARGIN = int(0.35 * DPI)
OK = {'', 'ok', 'pass', 'passed', 'valid', 'done', 'trusted'}
YES = {'yes', 'y', 'true', '1', 'x'}


def find_card(cdx_dir, row):
    names = [f for f in os.listdir(cdx_dir) if f.lower().endswith(('.cdx', '.cdxml'))]
    for key in ('file', 'label'):
        want = os.path.splitext(os.path.basename(row.get(key, '').strip()))[0]
        hit = [f for f in names if want and os.path.splitext(f)[0] == want]
        if hit:
            return os.path.join(cdx_dir, hit[0])
    pn = row['patent_no'].strip()
    hit = sorted(f for f in names if re.search(r'(^|_)' + re.escape(pn) + r'$', os.path.splitext(f)[0]))
    hit.sort(key=lambda f: not f.lower().endswith('.cdxml'))
    return os.path.join(cdx_dir, hit[0]) if hit else None


def fit(img, w, h):
    s = min(w / img.width, h / img.height)
    return img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)


def flagged(row):
    status = (row.get('status') or row.get('validation_status') or '').strip().lower()
    return bool((row.get('flags') or '').strip()) or status not in OK


def panel(path, render, w, h, missing):
    try:
        if path and os.path.exists(path):
            return fit(render(path), w, h)
    except Exception as e:  # show the problem on the sheet instead of stopping
        missing = f'{missing}: {type(e).__name__}: {e}'[:90]
    im = Image.new('RGB', (w, h // 3), 'white')
    ImageDraw.Draw(im).text((10, 10), missing, fill=(180, 0, 0), font=preview._font(preview.FONTS, 16))
    return im


def build(tracker, cdx_dir, crops_dir, out):
    with open(tracker, newline='', encoding='utf-8-sig') as f:
        rows = [{(k or '').strip().lower(): (v or '') for k, v in r.items()} for r in csv.DictReader(f)]
    if rows and 'selected' in rows[0]:
        rows = [r for r in rows if r['selected'].strip().lower() in YES]
    rows = sorted(rows, key=lambda r: not flagged(r))  # stable: flagged first, tracker order kept
    font = preview._font(preview.FONTS_B, 18)
    small = preview._font(preview.FONTS, 14)
    row_h = (PAGE_H - 2 * MARGIN) // ROWS
    col_w = (PAGE_W - 2 * MARGIN) // 2
    pic_h = row_h - 40
    pages = []
    for i, r in enumerate(rows):
        if i % ROWS == 0:
            pages.append(Image.new('RGB', (PAGE_W, PAGE_H), 'white'))
        pg, y = pages[-1], MARGIN + (i % ROWS) * row_h
        d = ImageDraw.Draw(pg)
        pn = r['patent_no'].strip()
        status = (r.get('status') or r.get('validation_status') or '').strip()
        bad = flagged(r)
        head = f'{pn}   status: {status or "-"}'
        d.text((MARGIN, y), head, fill=(190, 0, 0) if bad else (0, 0, 0), font=font)
        if (r.get('flags') or '').strip():
            d.text((MARGIN + font.getlength(head) + 20, y + 3), 'flags: ' + r['flags'].strip()[:110], fill=(190, 0, 0), font=small)
        crop = panel(os.path.join(crops_dir, pn + '.png'), Image.open, col_w - 20, pic_h, 'no patent crop')
        card = panel(find_card(cdx_dir, r), lambda p: preview.render(cdxload.load(p)), col_w - 20, pic_h, 'no card')
        for k, im in enumerate((crop, card)):
            x0 = MARGIN + k * col_w
            pg.paste(im.convert('RGB'), (x0 + (col_w - im.width) // 2, y + 30))
        d.text((MARGIN, y + 26), 'patent', fill=(120, 120, 120), font=small)
        d.text((MARGIN + col_w, y + 26), 'ours', fill=(120, 120, 120), font=small)
        d.line([(MARGIN, y + row_h - 4), (PAGE_W - MARGIN, y + row_h - 4)], fill=(200, 200, 200))
        d.line([(MARGIN + col_w, y + 30), (MARGIN + col_w, y + row_h - 10)], fill=(225, 225, 225))
    if not pages:
        raise SystemExit('no compounds in ' + tracker)
    pages[0].save(out, 'PDF', resolution=DPI, save_all=True, append_images=pages[1:])
    return len(rows), sum(map(flagged, rows))


if __name__ == '__main__':
    if len(sys.argv) != 5:
        raise SystemExit(__doc__)
    n, nf = build(*sys.argv[1:])
    print(f'{n} compounds ({nf} flagged) -> {sys.argv[4]}')
