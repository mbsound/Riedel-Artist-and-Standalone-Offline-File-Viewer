"""
MSVC RTTI helpers for Director (32-bit): class name -> vtable(s).

TypeDescriptor = {vftable ptr, spare, ".?AV<name>@@"}; a CompleteObjectLocator (COL) holds the TypeDescriptor
address at +0x0c; the vtable follows a pointer to its COL (vtable[-1] == COL).

Usage: python tools/rtti.py CCmdDialPP [more names...]   -> prints vtables and their slots in .text
"""
import os, re, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dre import d, off2va, u32, TEXT


def type_descriptor(name):
    m = re.search(re.escape(('.?AV%s@@' % name).encode()) + b'\0', d)
    return off2va(m.start()) - 8 if m else None


def vtables(name):
    td = type_descriptor(name)
    if td is None:
        return []
    out = []
    for m in re.finditer(re.escape(struct.pack('<I', td)), d):
        col = off2va(m.start()) - 0x0c
        if u32(col) != 0:          # signature 0 for x86 COL
            continue
        for p in re.finditer(re.escape(struct.pack('<I', col)), d):
            out.append(off2va(p.start()) + 4)
    return out


def slots(vt, n=0x80):
    lo, hi = TEXT[1], TEXT[1] + TEXT[2]
    res = []
    for k in range(n):
        a = u32(vt + 4 * k)
        if a is None or not (lo <= a < hi):
            break
        res.append((4 * k, a))
    return res


if __name__ == '__main__':
    for nm in sys.argv[1:]:
        for vt in vtables(nm):
            print(nm, hex(vt), ' '.join('%x:%x' % s for s in slots(vt) if not (0x80d000 < s[1] < 0x830000)))
