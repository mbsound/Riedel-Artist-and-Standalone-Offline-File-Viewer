"""Count the object classes in each .Art file's directory, named from Director's class table.
Usage: python tools/census.py file1.Art [file2.Art ...]"""
import sys, collections, pathlib, re
CODE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CODE))
import artist_reader as A

names = {}
for line in open(CODE / 'docs' / 'director_class_codes.txt', encoding='utf-8-sig'):
    m = re.match(r'0x([0-9a-f]+)\s+(\S+)', line)
    if m:
        names[int(m.group(1), 16)] = m.group(2)

files = sys.argv[1:]
counts = {}
for f in files:
    data = open(f, 'rb').read()
    _, objs, _ = A.read_art(data)                   # object directory: (class, id, group)
    t = {oid: cls for cls, oid, _ in objs}
    counts[pathlib.Path(f).stem[:18]] = collections.Counter(t.values())

allc = sorted(set().union(*[c.keys() for c in counts.values()]))
hdr = '%-6s %-28s' % ('code', 'class') + ''.join('%19s' % k for k in counts)
print(hdr)
for c in allc:
    print('0x%03x  %-28s' % (c, names.get(c, '?')) + ''.join('%19d' % counts[k].get(c, 0) for k in counts))
