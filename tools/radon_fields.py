"""Name the fields a libRadon unpack() writes, from the class's own accessors.

Reads docs/firmware_decomp/libRadon_3.4.1_serializers.c and, for one class:
  1. collects every simple accessor  radon::CLASS::getX / isX / hasX  whose body returns a member
     (this + OFF, *(T *)(this + OFF), this[OFF], or a bit test on one) -> {OFF: [names]}
  2. walks CLASS::unpack and lists, in stream order, the reads (getUInt8/getInt16/.../read/X::unpack)
     and the member offset each one is stored to
and prints the stream fields with the accessor names found for their offsets.

usage: python tools/radon_fields.py CLASS [CLASS ...]      e.g.  BPConfig VoxBase PriorityNode
"""
import pathlib
import re
import sys

import os
SRC = pathlib.Path(os.environ.get('RADON_SRC') or pathlib.Path(__file__).resolve().parent.parent / 'docs' / 'firmware_decomp'
                   / ('libRadon_%s_serializers.c' % os.environ.get('RADON_FW', '3.4.1')))
FUNC = re.compile(r'^// ==== (radon::[\w:<>,\s]+?)  @ ([0-9a-f]+) ====$', re.M)


def functions(text):
    """{qualified name: [bodies]} (the thunk copies at 0x2f....-0x31.... are skipped)."""
    out = {}
    heads = list(FUNC.finditer(text))
    for i, m in enumerate(heads):
        body = text[m.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        if 'PTR_' in body and body.count('\n') < 15:          # import thunk, no body
            continue
        out.setdefault(m.group(1), []).append(body)
    return out


OFF = r'this\s*\+\s*(0x[0-9a-f]+|\d+)'
RET = [re.compile(r'return\s+\*\([^)]*\*\)\(' + OFF + r'\)'),     # return *(T *)(this + 0x10)
       re.compile(r'return\s+this\[(0x[0-9a-f]+|\d+)\]'),       # return this[0x14]
       re.compile(r'return\s+' + OFF + r'\s*;'),                  # return this + 0x6c
       re.compile(r'return\s+\(?\*\(\w+ \*\)\(' + OFF + r'\)\s*&'),  # return (*(uint *)(this + 0xb0) & 3)
       re.compile(r'\(\*\(\w+ \*\)\(' + OFF + r'\)\s*[&>]')]    # bit tests


def accessors(funcs, cls):
    names = {}
    for q, bodies in funcs.items():
        m = re.match(r'radon::' + re.escape(cls) + r'::((?:get|is|has)\w*)$', q)
        if not m:
            continue
        for body in bodies:
            if body.count(';') > 6:                               # only trivial accessors
                continue
            for rx in RET:
                hit = rx.search(body)
                if hit:
                    names.setdefault(int(hit.group(1), 0), set()).add(m.group(1))
                    break
    return names


READ = re.compile(r'(InputStream::(?:get\w+|read)|(\w+(?:::\w+)*)::unpack(?:\w*))\s*\(')
STORE = re.compile(r'\*?\(?\w*\s*\*?\)?\(?(?:this|param_1)\s*\+\s*(0x[0-9a-f]+|\d+)\)?\s*=|this\[(0x[0-9a-f]+|\d+)\]\s*=')
UNPACK_ARG = re.compile(r'::unpack\w*\s*\(\s*\(\w+\s*\*\)\s*\(this\s*\+\s*(0x[0-9a-f]+|\d+)\)')


def unpack_fields(funcs, cls):
    bodies = funcs.get(f'radon::{cls}::unpack') or []
    if not bodies:
        return []
    body = max(bodies, key=len)
    lines = body.splitlines()
    out = []
    for i, line in enumerate(lines):
        m = READ.search(line)
        if not m or 'OutputStream' in line:
            continue
        kind = m.group(1).replace('InputStream::', '')
        off = None
        a = UNPACK_ARG.search(line)
        if a:
            off = int(a.group(1), 0)
        else:
            for j in range(i, min(i + 4, len(lines))):           # value stored on this or the next lines
                s = STORE.search(lines[j])
                if s:
                    off = int(s.group(1) or s.group(2), 0)
                    break
        out.append((kind, off))
    return out


def main(classes):
    funcs = functions(SRC.read_text(encoding='utf-8', errors='replace'))
    for cls in classes:
        acc = accessors(funcs, cls)
        print(f'== {cls}  (accessors for {len(acc)} offsets)')
        for n, (kind, off) in enumerate(unpack_fields(funcs, cls)):
            name = ', '.join(sorted(acc.get(off, ()))) if off is not None else ''
            print(f'  {n:3d}  {kind:34s} +{off:#06x}  {name}' if off is not None else f'  {n:3d}  {kind:34s}  ?')
        extra = {o: v for o, v in acc.items()}
        print('  accessors:', ', '.join(f'+{o:#x}={"/".join(sorted(v))}' for o, v in sorted(extra.items())))


if __name__ == '__main__':
    main(sys.argv[1:] or ['BPConfig'])
