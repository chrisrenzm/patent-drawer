"""Read node positions and bond wedge/hash display from a binary CDX."""
import struct
NODE, BOND, FRAG = 0x8004, 0x8005, 0x8003
def parse(data):
    p = 28; stack = []; nodes = {}; bonds = []
    while p < len(data) - 1:
        tag = struct.unpack_from('<H', data, p)[0]; p += 2
        if tag == 0:
            if not stack: break
            t, oid, rec = stack.pop()
            if t == NODE and 'pos' in rec and len([s for s in stack if s[0] == NODE]) == 0:
                nodes[oid] = rec['pos']
            if t == BOND and 'b' in rec and 'e' in rec and len([s for s in stack if s[0] == NODE]) == 0:
                bonds.append((rec['b'], rec['e'], rec.get('disp', 0)))
            continue
        if tag & 0x8000:
            oid = struct.unpack_from('<I', data, p)[0]; p += 4
            stack.append((tag, oid, {})); continue
        ln = struct.unpack_from('<H', data, p)[0]; p += 2
        if ln == 0xFFFF:
            ln = struct.unpack_from('<I', data, p)[0]; p += 4
        v = data[p:p + ln]; p += ln
        if not stack: continue
        t, oid, rec = stack[-1]
        if t == NODE and tag == 0x0200 and ln >= 8:
            y, x = struct.unpack_from('<ii', v); rec['pos'] = (x / 65536, y / 65536)
        elif t == BOND:
            if tag == 0x0604: rec['b'] = struct.unpack_from('<I', v)[0]
            elif tag == 0x0605: rec['e'] = struct.unpack_from('<I', v)[0]
            elif tag == 0x0601: rec['disp'] = struct.unpack_from('<H', v)[0]
    return nodes, bonds
