"""Pull free text objects (captions) out of a binary ChemDraw CDX file."""
import struct

TEXT_OBJ = 0x8006
NODE_OBJ = 0x8004
PROP_TEXT = 0x0700
PROP_POS = 0x0200


def texts(data: bytes):
    """Return list of (y, x, [(string, bold)]) for caption text objects
    (not atom labels, which live inside node objects)."""
    assert data[:8] == b"VjCD0100"
    p = 28
    stack = []  # object tags
    out = []
    cur = None
    while p < len(data) - 1:
        tag = struct.unpack_from("<H", data, p)[0]
        p += 2
        if tag == 0:
            if not stack:
                break
            t, rec = stack.pop()
            if rec is not None and rec.get("runs"):
                out.append((rec.get("y", 0), rec.get("x", 0), rec["runs"]))
            continue
        if tag & 0x8000:
            p += 4  # object id
            in_node = any(t == NODE_OBJ for t, _ in stack)
            rec = {} if (tag == TEXT_OBJ and not in_node) else None
            stack.append((tag, rec))
            continue
        ln = struct.unpack_from("<H", data, p)[0]
        p += 2
        if ln == 0xFFFF:
            ln = struct.unpack_from("<I", data, p)[0]
            p += 4
        val = data[p:p + ln]
        p += ln
        rec = stack[-1][1] if stack else None
        if rec is None:
            continue
        if tag == PROP_POS and len(val) >= 8:
            y, x = struct.unpack_from("<ii", val)
            rec["y"], rec["x"] = y / 65536, x / 65536
        elif tag == PROP_TEXT:
            n = struct.unpack_from("<H", val)[0]
            runs = [struct.unpack_from("<HHHHH", val, 2 + 10 * i) for i in range(n)]
            s = val[2 + 10 * n:].decode("cp1252", "replace")
            pieces = []
            for i, (start, font, face, size, color) in enumerate(runs):
                end = runs[i + 1][0] if i + 1 < n else len(s)
                pieces.append((s[start:end], bool(face & 1)))
            rec["runs"] = pieces
    return out


def lines(data: bytes):
    """Caption lines top-to-bottom as (text, bold)."""
    res = []
    for y, x, pieces in sorted(texts(data)):
        buf, bold = "", None
        for s, b in pieces:
            for ch in s:
                if ch in "\r\n":
                    res.append((buf, bold))
                    buf, bold = "", None
                else:
                    buf += ch
                    if bold is None and ch.strip():
                        bold = b
        res.append((buf, bold))
    return [(t, bool(b)) for t, b in res if t.strip()]
