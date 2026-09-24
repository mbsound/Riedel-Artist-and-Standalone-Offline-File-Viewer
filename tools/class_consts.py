"""
Print constant-returning virtual methods for Director classes (e.g. key rows / columns),
read straight from each class's vtable.
Usage: python tools/class_consts.py 0xc0 0xc8 [...]   (vtable byte offsets)
"""
import pathlib, sys, re
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from dre import vtables, fn, dis, is_code
from class_codes import const_return

offsets = [int(a, 16) for a in sys.argv[1:]]
codes = {}
for line in open(pathlib.Path(__file__).resolve().parent.parent / 'docs' / 'director_class_codes.txt'):
    m = re.match(r'0x([0-9a-f]+)\s+(\S+)', line)
    if m:
        codes[m.group(2)] = int(m.group(1), 16)
vt = vtables()
for name, code in sorted(codes.items(), key=lambda x: x[1]):
    if name not in vt:
        continue
    vals = []
    for off in offsets:
        f = fn(vt[name][0], off // 4)
        vals.append(const_return(f) if f and is_code(f) else None)
    print('0x%03x %-26s %s' % (code, name, '  '.join('%s' % v for v in vals)))
