"""
Director's automation property names per record class, with the member each property reads.

Every CPhysObj subclass has a property-name function (vtable +0x28: switch id -> name) and a getter
(vtable +0x24: switch id -> member). Both are decompiled by Ghidra (DecompileList.java) into
<ghidra_projects>/props2 as N_<vtable>.c and G_<vtable>.c; the vtable list is written by the snippet in
docs/HANDOFF.md. The name cases usually call a tiny helper that builds a CString from an ASCII literal,
so the literal is read from that helper's disassembly.

Usage: python tools/prop_names.py <props2 dir> <vtables.json> > docs/director_props.txt
"""
import os, re, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dre import dis, astr

IDENT = re.compile(r'[A-Za-z][A-Za-z0-9_]{2,60}$')


def helper_name(va):
    """First identifier-like ASCII literal pushed / loaded in the helper at va."""
    for i in dis(va, 60):
        for m in re.finditer(r'0x([0-9a-f]{6,7})\b', i.op_str):
            s = astr(int(m.group(1), 16))
            if s and IDENT.match(s):
                return s
        if i.mnemonic == 'ret':
            break
    return None


def split_cases(text):
    """{case id: body text} from a decompiled switch."""
    parts = re.split(r'\n\s*case (?:\(\w+ \*\))?(0x[0-9a-f]+|\d+):', text)
    out = {}
    for k in range(1, len(parts) - 1, 2):
        out[int(parts[k], 0)] = parts[k + 1].split('\n  case')[0][:1500]
    return out


def names(path):
    text = open(path, encoding='utf-8', errors='replace').read()
    res = {}
    for cid, body in split_cases(text).items():
        lit = re.search(r'"([A-Za-z][A-Za-z0-9_]+)"', body)
        if lit:
            res[cid] = lit.group(1)
            continue
        for f in re.findall(r'FUN_00([0-9a-f]{6})', body):
            n = helper_name(int(f, 16))
            if n:
                res[cid] = n
                break
    return res


def getters(path):
    text = open(path, encoding='utf-8', errors='replace').read()
    res = {}
    for cid, body in split_cases(text).items():
        offs = re.findall(r'in_ECX \+ (0x[0-9a-f]+)\)( >> \w+)?', body)
        offs += [('0x%x' % (int(i, 16) * 4), '') for i in re.findall(r'in_ECX\[(0x[0-9a-f]+)\]', body)]
        res[cid] = ', '.join('+%s%s' % (o, s) for o, s in offs[:3]) if offs else ''
    return res


def main():
    d, vtj = sys.argv[1], sys.argv[2]
    vts = json.load(open(vtj))
    for vt, (cls, fn, n, g) in sorted(vts.items(), key=lambda kv: kv[1][0]):
        vt_hex = vt[2:]
        npath, gpath = os.path.join(d, 'N_%s.c' % vt_hex), os.path.join(d, 'G_%s.c' % vt_hex)
        if not os.path.exists(npath):
            continue
        nm = names(npath)
        gt = getters(gpath) if os.path.exists(gpath) else {}
        if not nm:
            continue
        print('class 0x%x %s  vtable %s  names FUN_%08x  getter FUN_%08x' % (cls, fn, vt, n, g))
        for cid in sorted(nm):
            print('   %3d  %-34s %s' % (cid, nm[cid], gt.get(cid, '')))


if __name__ == '__main__':
    main()
