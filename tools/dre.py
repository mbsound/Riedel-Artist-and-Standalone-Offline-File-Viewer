"""
Static reverse-engineering helpers for Riedel Director (no execution).
Usage (x64 Python with `pip install capstone`):
    python -i tools/dre.py            # defaults to Director 8.9.D2 in Program Files
    >>> vt = vtables()                # {class name: [vtable VA, ...]}
    >>> fn(vt['CPhysCmdConf'][0], 5)  # 5th virtual function VA
    >>> show(0x9dffe0)                # disassemble one function
Addresses are for Director 8.9.D2 (image base 0x400000). See docs/FORMAT_NOTES.md.
"""
import os, struct, re, functools
import capstone

EXE = os.environ.get("DIRECTOR_EXE", r"C:\Program Files (x86)\Riedel\Director8.9.D2\Director 8.9.D2.exe")
d = open(EXE, 'rb').read()
_pe = struct.unpack_from('<I', d, 0x3c)[0]
_nsec = struct.unpack_from('<H', d, _pe + 6)[0]
_opt = struct.unpack_from('<H', d, _pe + 20)[0]
base = struct.unpack_from('<I', d, _pe + 24 + 28)[0]
secs = []
for i in range(_nsec):
    s = _pe + 24 + _opt + 40 * i
    name = d[s:s + 8].rstrip(b'\0').decode()
    vsz, va, rsz, raw = struct.unpack_from('<IIII', d, s + 8)
    secs.append((name, base + va, vsz, raw, rsz))
TEXT = next(s for s in secs if s[0] == '.text')


def off2va(o):
    for _, va, vsz, raw, rsz in secs:
        if raw <= o < raw + rsz:
            return va + (o - raw)


def va2off(v):
    for _, va, vsz, raw, rsz in secs:
        if va <= v < va + min(vsz, rsz):
            return raw + (v - va)


def u32(v):
    o = va2off(v)
    return None if o is None else struct.unpack_from('<I', d, o)[0]


def is_code(v):
    return TEXT[1] <= v < TEXT[1] + TEXT[2]


def wstr(v, maxlen=400):
    o = va2off(v)
    if o is None:
        return None
    e = o
    while e + 1 < len(d) and d[e:e + 2] != b'\0\0' and e - o < maxlen:
        e += 2
    try:
        s = d[o:e].decode('utf-16le')
    except UnicodeDecodeError:
        return None
    return s if s and all(32 <= ord(c) < 127 or c in '\r\n\t' for c in s) else None


def astr(v, maxlen=400):
    o = va2off(v)
    if o is None:
        return None
    e = d.find(b'\0', o, o + maxlen)
    s = d[o:e].decode('latin-1') if e > o else ''
    return s if s and all(32 <= ord(c) < 127 for c in s) else None


md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.detail = False


def dis(va, n=80):
    o = va2off(va)
    return list(md.disasm(d[o:o + n * 16], va))[:n]


def func(va, limit=4000):
    """Linear-sweep a function from va to its last ret (follows forward jumps within it)."""
    o = va2off(va)
    out, far = [], va
    for ins in md.disasm(d[o:o + limit * 16], va):
        out.append(ins)
        if ins.mnemonic.startswith('j') and ins.op_str.startswith('0x'):
            t = int(ins.op_str, 16)
            if va <= t < va + 0x8000:
                far = max(far, t)
        if ins.mnemonic in ('ret', 'retn') and ins.address >= far:
            break
        if ins.mnemonic == 'int3' and ins.address >= far:
            break
        if len(out) >= limit:
            break
    return out


def annotate(ins):
    """Append string / known-function hints to an instruction."""
    s = '%08x  %-6s %s' % (ins.address, ins.mnemonic, ins.op_str)
    for m in re.finditer(r'0x([0-9a-f]{6,8})', ins.op_str):
        v = int(m.group(1), 16)
        hint = NAMES.get(v) or wstr(v, 120) or astr(v, 120)
        if hint:
            s += '    ; ' + repr(hint)[:100]
    return s


NAMES = {}  # VA -> label, filled in as functions are identified


def show(va, limit=400):
    for ins in func(va, limit):
        print(annotate(ins))


# ---------- RTTI ----------
@functools.lru_cache(None)
def type_descriptors():
    """{VA of TypeDescriptor: mangled name} for every '.?AV...@@' class."""
    out = {}
    for m in re.finditer(rb'\.\?A[VU][A-Za-z0-9_@?$]+?@@\0', d):
        td = off2va(m.start()) - 8
        out[td] = m.group()[:-1].decode()
    return out


@functools.lru_cache(None)
def vtables():
    """{demangled-ish class name: [vtable VAs]} via CompleteObjectLocator -> vtable[-1]."""
    tds = type_descriptors()
    cols = {}
    rd = [s for s in secs if s[0] == '.rdata'][0]
    lo, hi = rd[3], rd[3] + rd[4]
    for off in range(lo, hi - 20, 4):
        sig, offs, cdo, ptd, pch = struct.unpack_from('<IIIII', d, off)
        if sig == 0 and ptd in tds and offs < 0x1000:
            cols[off2va(off)] = (ptd, offs)
    pat = {}
    for col in cols:
        pat.setdefault(struct.pack('<I', col), col)
    out = {}
    for off in range(lo, hi - 8, 4):
        v = struct.unpack_from('<I', d, off)[0]
        if v in cols:
            first = struct.unpack_from('<I', d, off + 4)[0]
            if is_code(first):
                ptd, offs = cols[v]
                if offs == 0:
                    name = tds[ptd][4:-2]
                    out.setdefault(name, []).append(off2va(off) + 4)
    return out


def vfuncs(vt, n=120):
    out = []
    for i in range(n):
        f = u32(vt + 4 * i)
        if f is None or not is_code(f):
            break
        out.append(f)
    return out


def fn(vt, idx):
    return u32(vt + 4 * idx)


# ---------- xrefs ----------
def xrefs_imm(value):
    """File offsets in .text where the 32-bit value appears (push/mov imm, call targets not included)."""
    pat = struct.pack('<I', value)
    lo, hi = TEXT[3], TEXT[3] + TEXT[4]
    return [off2va(m.start()) for m in re.finditer(re.escape(pat), d[lo:hi])] and \
        [off2va(lo + m.start()) for m in re.finditer(re.escape(pat), d[lo:hi])]


@functools.lru_cache(None)
def _calls():
    """{target VA: [caller instruction VAs]} for E8 rel32 calls (byte scan, may include noise)."""
    lo, hi = TEXT[3], TEXT[3] + TEXT[4]
    out = {}
    tlo, thi = TEXT[1], TEXT[1] + TEXT[2]
    for m in re.finditer(rb'\xe8', d[lo:hi]):
        o = lo + m.start()
        rel = struct.unpack_from('<i', d, o + 1)[0]
        src = off2va(o)
        t = (src + 5 + rel) & 0xffffffff
        if tlo <= t < thi:
            out.setdefault(t, []).append(src)
    return out


def callers(va):
    return _calls().get(va, [])


def func_start(va, back=0x4000):
    """Guess the start of the function containing va (after int3/ret padding)."""
    o = va2off(va)
    lo = max(TEXT[3], o - back)
    p = o
    while p > lo:
        if d[p - 1] == 0xcc and d[p] != 0xcc:
            return off2va(p)
        p -= 1
    return None


if __name__ == '__main__':
    import code
    code.interact(local=globals())
