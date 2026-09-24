"""
Object-level diff of two .Art files read with artist_reader (for one-change test saves in Director).
Usage: python tools/art_diff.py old.Art new.Art
Ignores the per-save trailer flag (base_5c) and record offsets/lengths.
"""
import sys, pathlib, re
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import artist_reader as A

IGNORE = {'offset', 'length', 'base_5c'}
names = {}
for line in open(pathlib.Path(A.__file__).parent / 'docs' / 'director_class_codes.txt'):
    m = re.match(r'0x([0-9a-f]+)\s+(\S+)', line)
    if m:
        names[int(m.group(1), 16)] = m.group(2)


def label(r):
    n = r.get('name') or r.get('label') or r.get('long_name') or ''
    return '%s id %d %r' % (names.get(r['class'], hex(r['class'])), r['id'], n)


def show(v, limit=160):
    s = repr(v)
    return s if len(s) <= limit else s[:limit] + '...'


def main(a, b):
    _, ra = A.parse_art(open(a, 'rb').read())
    _, rb = A.parse_art(open(b, 'rb').read())
    da, db = {r['id']: r for r in ra}, {r['id']: r for r in rb}
    for oid in db.keys() - da.keys():
        r = db[oid]
        print('+ NEW', label(r))
        for k, v in r.items():
            if k not in IGNORE and k not in ('class', 'id', 'group'):
                print('      %s = %s' % (k, show(v)))
    for oid in da.keys() - db.keys():
        print('- REMOVED', label(da[oid]))
    for oid in da.keys() & db.keys():
        x, y = da[oid], db[oid]
        ch = [k for k in sorted(set(x) | set(y)) if k not in IGNORE and x.get(k) != y.get(k)]
        if ch:
            print('~ CHANGED', label(y))
            for k in ch:
                print('      %s: %s -> %s' % (k, show(x.get(k)), show(y.get(k))))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
