"""
Split reduced decompiler output into one file per unique function plus an index of which
class Serialize reaches which functions.
Usage: python tools/dedupe_decomp.py <reduced_dir> <out_dir>
"""
import re, sys, pathlib, json

src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
(dst / 'funcs').mkdir(parents=True, exist_ok=True)
funcs, index = {}, {}
for f in sorted(src.glob('*.c')):
    t = f.read_text(encoding='utf-8')
    parts = re.split(r'(?m)^// ===== (\S+) @ ([0-9a-f]+).*$', t)
    order = []
    for name, addr, body in zip(parts[1::3], parts[2::3], parts[3::3]):
        key = addr.lstrip('0')
        funcs.setdefault(key, (name, body.strip()))
        order.append(key)
    index[f.stem] = order
tot = 0
for key, (name, body) in funcs.items():
    (dst / 'funcs' / ('%s.c' % key)).write_text('// %s @ %s\n%s\n' % (name, key, body), encoding='utf-8')
    tot += len(body)
(dst / 'index.json').write_text(json.dumps(index, indent=1))
print(len(funcs), 'unique functions,', tot, 'bytes')
