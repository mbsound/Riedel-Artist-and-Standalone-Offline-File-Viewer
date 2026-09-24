"""Count the object classes in each .Art file's directory, named from Director's class table.
Usage: python tools/census.py file1.Art [file2.Art ...]"""
import sys, collections, pathlib, re
CODE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CODE))
from riedel_formats import artist_object_types

names = {}
for line in open(CODE / 'docs' / 'director_class_codes.txt', encoding='utf-8-sig'):
    m = re.match(r'0x([0-9a-f]+)\s+(\S+)', line)
    if m:
        names[int(m.group(1), 16)] = m.group(2)

files = sys.argv[1:]
counts = {}
for f in files:
    data = open(f, 'rb').read()
    t = artist_object_types(data)
    counts[pathlib.Path(f).stem[:18]] = collections.Counter(t.values())

allc = sorted(set().union(*[c.keys() for c in counts.values()]))
hdr = '%-6s %-28s' % ('code', 'class') + ''.join('%19s' % k for k in counts)
print(hdr)
for c in allc:
    print('0x%03x  %-28s' % (c, names.get(c, '?')) + ''.join('%19d' % counts[k].get(c, 0) for k in counts))
