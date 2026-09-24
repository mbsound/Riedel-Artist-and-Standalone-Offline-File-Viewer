"""
Condense Ghidra output from DecompileSerializers.java into a readable read/write listing.
Drops MFC buffer management, exception plumbing and declarations; turns inlined CArchive
accesses into READ_/WRITE_ calls.
Usage: python tools/reduce_decomp.py <in_dir> <out_dir>
"""
import re, sys, pathlib

TYPES = {'byte': 'u8', 'char': 'i8', 'undefined1': 'u8', 'bool': 'u8',
         'short': 'i16', 'ushort': 'u16', 'undefined2': 'u16', 'wchar_t': 'u16',
         'int': 'i32', 'uint': 'u32', 'undefined4': 'u32', 'float': 'f32', 'long': 'i32', 'ulong': 'u32',
         'double': 'f64', 'undefined8': 'u64', 'longlong': 'i64', 'ulonglong': 'u64'}

CUR = r'(?:\w+->m_lpBufCur)'
NOISE = [
    re.compile(r'^\s*if \(\(\(?\w+->m_nMode & 1\)? == 0\)\) goto \w+;\s*$'),
    re.compile(r'^\s*if \(\(\~?\(?\w+->m_nMode & 1\)? [!=]= 0\)\) goto \w+;\s*$'),
    re.compile(r'^\s*\w+Stack_\w+ = .*;\s*$'),
    re.compile(r'ExceptionList|DAT_0128a000|puStack_c = |local_8 = |local_8\._\d_\d_ = '),
    re.compile(r'^\s*/\* WARNING: Subroutine does not return \*/\s*$'),
    re.compile(r'^\s*\w+ = \(?\w+ \*?\)?\w+;\s*$'),   # plain register aliases like pCVar5 = ar;
]
FILL_OPEN = re.compile(r'^\s*if \(.*m_lpBufMax < .*\) \{\s*$')
MODE_OPEN = re.compile(r'^\s*if \(.*m_nMode & 1.*\) \{\s*$')
READ = re.compile(r'^(\s*)(.*?)\*\((\w+) \*\)' + CUR + r';\s*$')
READ_DEREF = re.compile(r'^(\s*)(.*?)\*' + CUR + r';\s*$')
ADV = re.compile(r'^\s*(\w+->m_lpBufCur) = .*?\1 \+ (\d+);\s*$|^\s*(\w+->m_lpBufCur) = \(byte \*\)\(\(int\)\3 \+ (\d+)\);\s*$')
ADV_TMP = re.compile(r'^\s*(\w+) = \(?\w*\s?\*?\)?\(?\(?\w*\)?\w+->m_lpBufCur \+ (\d+)\)?;\s*$')
WRITE = re.compile(r'^(\s*)\*\((\w+) \*\)' + CUR + r' = (.*);\s*$')
WRITE_DEREF = re.compile(r'^(\s*)\*' + CUR + r' = (.*);\s*$')


def reduce_func(lines):
    out, i = [], 0
    # skip declarations: from '{' after signature to first blank line
    body_start = next((k for k, l in enumerate(lines) if l.strip() == '{'), 0)
    k = body_start + 1
    while k < len(lines) and lines[k].strip() and re.match(r'^\s+[\w\s\*\[\]]+;$', lines[k]):
        k += 1
    lines = lines[:body_start + 1] + lines[k:]
    pending_read = None
    while i < len(lines):
        l = lines[i]
        # buffer refill / flush blocks and mode-check throw blocks
        if FILL_OPEN.match(l) or MODE_OPEN.match(l):
            depth, j = 0, i
            while j < len(lines):
                depth += lines[j].count('{') - lines[j].count('}')
                j += 1
                if depth <= 0:
                    break
            block = '\n'.join(lines[i:j])
            if 'CArchive_' in block or 'Afx' in block or 'GetBuffer' in block:
                i = j
                continue
        m = READ.match(l)
        if m:
            t = TYPES.get(m.group(3), m.group(3))
            out.append('%s%sREAD_%s();' % (m.group(1), m.group(2), t))
            pending_read = True
            i += 1
            continue
        m = READ_DEREF.match(l)
        if m:
            out.append('%s%sREAD_u8();' % (m.group(1), m.group(2)))
            pending_read = True
            i += 1
            continue
        m = WRITE.match(l)
        if m:
            out.append('%sWRITE_%s(%s);' % (m.group(1), TYPES.get(m.group(2), m.group(2)), m.group(3)))
            pending_read = True
            i += 1
            continue
        m = WRITE_DEREF.match(l)
        if m:
            out.append('%sWRITE_u8(%s);' % (m.group(1), m.group(2)))
            pending_read = True
            i += 1
            continue
        m = ADV_TMP.match(l)
        if m and i + 1 < len(lines) and re.match(r'^\s*\w+->m_lpBufCur = %s;\s*$' % m.group(1), lines[i + 1]):
            if pending_read:
                pending_read = None
            else:
                out.append(re.match(r'^\s*', l).group() + 'SKIP(%s);' % m.group(2))
            i += 2
            continue
        m = ADV.match(l)
        if m:
            n = m.group(2) or m.group(4)
            if pending_read:
                pending_read = None
            else:
                out.append(re.match(r'^\s*', l).group() + 'SKIP(%s);' % n)
            i += 1
            continue
        if any(p.search(l) for p in NOISE):
            i += 1
            continue
        out.append(l)
        i += 1
    # drop empty lines runs
    text = re.sub(r'\n\s*\n+', '\n', '\n'.join(out))
    return text


def reduce_file(src):
    t = src.read_text(encoding='utf-8', errors='replace')
    parts = re.split(r'(?m)^(// ===== .*)$', t)
    res = [parts[0]]
    for h, body in zip(parts[1::2], parts[2::2]):
        res.append(h)
        res.append(reduce_func(body.split('\n')))
    return '\n'.join(res)


if __name__ == '__main__':
    src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    dst.mkdir(parents=True, exist_ok=True)
    tot_in = tot_out = 0
    for f in sorted(src.glob('*.c')):
        r = reduce_file(f)
        (dst / f.name).write_text(r, encoding='utf-8')
        tot_in += f.stat().st_size
        tot_out += len(r)
    print('reduced %d -> %d bytes' % (tot_in, tot_out))
