"""Minimal Compound File Binary (OLE2) writer, v3 (512-byte sectors).
Enough to build an embedded ChemDraw OLE object: a root storage with a CLSID
and a few flat streams."""
import struct

SECT = 512
MINI = 64
CUTOFF = 4096
FREE, ENDCHAIN, FATSECT = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD
NOSTREAM = 0xFFFFFFFF


def _pad(b, n):
    r = len(b) % n
    return b + b"\0" * ((n - r) % n)


def _cmp_key(name):
    return (len(name), name.upper())


def _dirent(name, typ, color, left, right, child, clsid, start, size):
    n = (name + "\0").encode("utf-16-le")
    assert len(n) <= 64
    if not name:
        n = b""
    e = (n.ljust(64, b"\0") + struct.pack("<HBBIII", len(n), typ, color, left, right, child)
         + clsid + struct.pack("<I", 0) + b"\0" * 16 + struct.pack("<IQ", start, size))
    assert len(e) == 128
    return e


def build(root_clsid: bytes, streams: dict) -> bytes:
    """streams: {name: bytes}. Returns the compound file bytes."""
    names = sorted(streams, key=_cmp_key)
    # --- mini stream + mini FAT
    minifat, ministream, starts = [], b"", {}
    big = []
    for nm in names:
        d = streams[nm]
        if len(d) < CUTOFF:
            if len(d) == 0:
                starts[nm] = ENDCHAIN
                continue
            first = len(minifat)
            k = (len(d) + MINI - 1) // MINI
            for i in range(k):
                minifat.append(first + i + 1 if i < k - 1 else ENDCHAIN)
            starts[nm] = first
            ministream += _pad(d, MINI)
        else:
            big.append(nm)
    # --- lay out regular sectors
    sectors = []  # list of 512-byte blobs
    fat = []

    def add_chain(data):
        data = _pad(data, SECT)
        k = len(data) // SECT
        first = len(sectors)
        for i in range(k):
            sectors.append(data[i * SECT:(i + 1) * SECT])
            fat.append(first + i + 1 if i < k - 1 else ENDCHAIN)
        return first if k else ENDCHAIN

    root_start = add_chain(ministream) if ministream else ENDCHAIN
    for nm in big:
        starts[nm] = add_chain(streams[nm])
    minifat_bytes = b"".join(struct.pack("<I", x) for x in minifat)
    minifat_start = add_chain(minifat_bytes) if minifat else ENDCHAIN
    n_minifat_sect = (len(minifat_bytes) + SECT - 1) // SECT

    # --- directory: balanced BST (all black is valid when balanced as a perfect-ish tree;
    # we keep it simple: build balanced tree, color all black -> valid for <= 3 nodes per level
    # sizes we use). Use generic balanced build.
    entries = [None] * (1 + len(names))
    idx = {nm: i + 1 for i, nm in enumerate(names)}
    left, right = {}, {}

    def bal(lst):
        if not lst:
            return NOSTREAM
        m = len(lst) // 2
        node = lst[m]
        left[node] = bal(lst[:m])
        right[node] = bal(lst[m + 1:])
        return idx[node]

    root_child = bal(names)
    d = _dirent("Root Entry", 5, 1, NOSTREAM, NOSTREAM, root_child, root_clsid,
                root_start, len(ministream))
    entries[0] = d
    for nm in names:
        entries[idx[nm]] = _dirent(nm, 2, 1, left[nm], right[nm], NOSTREAM, b"\0" * 16,
                                   starts[nm], len(streams[nm]))
    dirdata = b"".join(entries)
    while len(dirdata) % SECT:
        dirdata += _dirent("", 0, 0, NOSTREAM, NOSTREAM, NOSTREAM, b"\0" * 16, 0, 0)
    dir_start = add_chain(dirdata)

    # --- FAT sectors (they also need FAT entries)
    nfat = 1
    while True:
        total = len(sectors) + nfat
        if (total + SECT // 4 - 1) // (SECT // 4) <= nfat:
            break
        nfat += 1
    assert nfat <= 109
    fat_start = len(sectors)
    fat += [FATSECT] * nfat
    fat += [FREE] * (nfat * (SECT // 4) - len(fat))
    fatbytes = b"".join(struct.pack("<I", x) for x in fat)
    for i in range(nfat):
        sectors.append(fatbytes[i * SECT:(i + 1) * SECT])

    difat = [fat_start + i for i in range(nfat)] + [FREE] * (109 - nfat)
    hdr = (b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1" + b"\0" * 16
           + struct.pack("<HHHHH", 0x3E, 3, 0xFFFE, 9, 6) + b"\0" * 6
           + struct.pack("<IIIIIIIII", 0, nfat, dir_start, 0, CUTOFF,
                         minifat_start, n_minifat_sect, ENDCHAIN, 0)
           + b"".join(struct.pack("<I", x) for x in difat))
    assert len(hdr) == 512
    return hdr + b"".join(sectors)
