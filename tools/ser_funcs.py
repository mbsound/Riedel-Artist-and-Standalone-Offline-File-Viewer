"""Show which Serialize implementation (and reached functions) each class uses.
Usage: python tools/ser_funcs.py <uniq_dir> CLASS [CLASS ...]"""
import sys, re, json, pathlib

tools = pathlib.Path(__file__).parent
inherit = {}
for l in (tools / 'ghidra' / 'serialize_list.txt').read_text().splitlines():
    m = re.match(r'# (\w+) inherits Serialize from (\w+)', l)
    if m:
        inherit[m.group(1)] = m.group(2)
idx = json.loads((pathlib.Path(sys.argv[1]) / 'index.json').read_text())
for c in sys.argv[2:]:
    src = inherit.get(c, c)
    print('%-26s -> %-26s %s' % (c, src, ' '.join(idx.get(src, ['?']))))
