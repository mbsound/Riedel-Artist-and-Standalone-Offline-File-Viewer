"""
Check artist_reader's port decoding against Director's own Ports grid (copied as CSV).
Usage: python tools/check_ports_csv.py file.Art ports.csv
Prints every mismatching cell, then the class -> 'Port Type' table seen in the export.
"""
import csv, sys, pathlib, re
from collections import defaultdict
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import artist_reader as A

names = {}
for line in open(pathlib.Path(A.__file__).parent / 'docs' / 'director_class_codes.txt'):
    m = re.match(r'0x([0-9a-f]+)\s+(\S+)', line)
    if m:
        names[int(m.group(1), 16)] = m.group(2)


def ip_columns(port):
    """Which 'IP Address (Input/Output Media n)' columns Director fills: port_214 picks the interface."""
    n = port.get('port_214', 0) + 1
    cols = {}
    if 'stream_rx' in port:
        cols['IP Address (Input Media %d)' % n] = '0.0.0.0'     # stream addresses are 0 in this file
    if 'stream_tx' in port or 'audio_settings' in port:
        cols['IP Address (Output Media %d)' % n] = '0.0.0.0'
    om2 = port.get('output_media_2')
    if om2:
        cols['IP Address (Output Media %d)' % n] = om2['ip']
    return cols


def decoded(port, byid):
    d = {
        'Long Name': port['port_str'],
        'Local 8-char Label': port['name'],
        'Alias': port['alias'],
        'Subtitle': port['port_str2'],
        'Port': port['port_strings'][1],
        'Node-Bay': A.port_node_bay(port, byid),
        'Port Type': A.port_type(port, byid),
        'Trunking object address': str(port['trunk_address']),
        'Input Gain': '%+.1f' % port['input_gain_db'],
        'Output Gain': '%+.1f' % port['output_gain_db'],
        'Room Code': ('Room ' if port['room_code'] else '') + A.room_code_label(port['room_code']),
    }
    for col in IP_COLS:
        d[col] = ''
    d.update(ip_columns(port))
    return d


IP_COLS = ['IP Address (%s Media %d)' % (io, n) for io in ('Input', 'Output') for n in (1, 2)]


def norm(s):
    return ' '.join(s.split())


def main(art, csv_path):
    _, recs = A.parse_art(open(art, 'rb').read())
    byid = {r['id']: r for r in recs}
    ports = {r['port_str']: r for r in recs if 'port_number' in r}
    rows = list(csv.DictReader(open(csv_path, newline='', encoding='utf-8-sig')))
    print('%d ports in file, %d rows in export' % (len(ports), len(rows)))
    bad = 0
    types = defaultdict(set)
    for row in rows:
        p = ports.pop(row['Long Name'], None)
        if p is None:
            print('MISSING in file:', row['Long Name'])
            bad += 1
            continue
        types[names.get(p['class'], hex(p['class']))].add(row['Port Type'].strip())
        for col, val in decoded(p, byid).items():
            if val is None or (col.endswith('Gain') and row[col] == ''):   # gain column hidden for this type
                continue
            if norm(val) != norm(row[col]):
                print('%-32s %-28s file=%r director=%r' % (row['Long Name'], col, val, row[col]))
                bad += 1
    for name in ports:
        print('EXTRA in file:', name)
        bad += 1
    print('\n%d mismatches' % bad)
    print('\nclass -> Port Type')
    for cls, t in sorted(types.items()):
        print('  %-28s %s' % (cls, ' | '.join(sorted(t))))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
