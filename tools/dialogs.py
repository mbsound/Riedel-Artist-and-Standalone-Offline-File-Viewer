"""
Dump Director's dialog templates (RT_DIALOG resources): dialog id, caption and every control
(id, class, text). Used to put Director's own labels on checkbox / radio / combo fields.
Usage: python tools/dialogs.py [exe] [--grep TEXT] [--id DIALOG_ID] > docs/director_dialogs.txt
"""
import os, sys, struct
import pefile

EXE = os.environ.get("DIRECTOR_EXE", r"C:\Program Files (x86)\Riedel\Director8.9.D2\Director 8.9.D2.exe")
CLASSES = {0x80: 'Button', 0x81: 'Edit', 0x82: 'Static', 0x83: 'ListBox', 0x84: 'ScrollBar', 0x85: 'ComboBox'}


def _sz_or_ord(b, o):
    """Read a DLGTEMPLATE sz_Or_Ord field; returns (value, new offset)."""
    w = struct.unpack_from('<H', b, o)[0]
    if w == 0:
        return '', o + 2
    if w == 0xffff:
        return struct.unpack_from('<H', b, o + 2)[0], o + 4
    e = o
    while struct.unpack_from('<H', b, e)[0]:
        e += 2
    return b[o:e].decode('utf-16le', 'replace'), e + 2


def _align4(o):
    return (o + 3) & ~3


def parse_dialog(b):
    """DLGTEMPLATEEX (MFC dialogs) or classic DLGTEMPLATE -> (caption, [controls])."""
    ex = struct.unpack_from('<HH', b, 0) == (1, 0xffff)
    if ex:
        _, _, _, _, style, n = struct.unpack_from('<HHIII H', b, 0)[:6] if False else (0, 0, 0, 0, 0, 0)
        help_id, exstyle, style = struct.unpack_from('<III', b, 4)
        n, x, y, cx, cy = struct.unpack_from('<Hhhhh', b, 16)
        o = 26
    else:
        style, exstyle, n, x, y, cx, cy = struct.unpack_from('<IIHhhhh', b, 0)
        o = 18
    menu, o = _sz_or_ord(b, o)
    wclass, o = _sz_or_ord(b, o)
    caption, o = _sz_or_ord(b, o)
    if style & 0x40:                                      # DS_SETFONT
        o += 6 if ex else 2
        _, o = _sz_or_ord(b, o)
    ctrls = []
    for _ in range(n):
        o = _align4(o)
        if ex:
            _, _, cstyle = struct.unpack_from('<III', b, o)
            rect = struct.unpack_from('<hhhh', b, o + 12)
            cid = struct.unpack_from('<I', b, o + 20)[0]
            o += 24
        else:
            cstyle, _ = struct.unpack_from('<II', b, o)
            rect = struct.unpack_from('<hhhh', b, o + 8)
            cid = struct.unpack_from('<H', b, o + 16)[0]
            o += 18
        cls, o = _sz_or_ord(b, o)
        text, o = _sz_or_ord(b, o)
        extra = struct.unpack_from('<H', b, o)[0]
        o += 2 + extra
        cls = CLASSES.get(cls, cls) if isinstance(cls, int) else cls
        kind = cls
        if cls == 'Button':
            bs = cstyle & 0xf
            kind = {2: 'CheckBox', 3: 'CheckBox', 5: 'CheckBox', 6: 'CheckBox', 4: 'Radio', 9: 'Radio',
                    7: 'GroupBox'}.get(bs, 'Button')
        ctrls.append((cid & 0xffff, kind, text if isinstance(text, str) else '#%d' % text, rect))
    return caption, ctrls


def dialogs(exe=EXE):
    pe = pefile.PE(exe, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_RESOURCE']])
    out = {}
    for t in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if t.id != 5:                                     # RT_DIALOG
            continue
        for e in t.directory.entries:
            for lang in e.directory.entries:
                ds = lang.data.struct
                b = pe.get_data(ds.OffsetToData, ds.Size)
                try:
                    out[e.id if e.id is not None else str(e.name)] = parse_dialog(b)
                except Exception as ex:                   # malformed template: keep going
                    out[e.id] = ('<parse error %s>' % ex, [])
    return out


def main(argv):
    exe = EXE
    grep = did = None
    args = list(argv)
    if args and not args[0].startswith('--'):
        exe = args.pop(0)
    while args:
        a = args.pop(0)
        if a == '--grep':
            grep = args.pop(0).lower()
        elif a == '--id':
            did = int(args.pop(0), 0)
    for i, (cap, ctrls) in sorted(dialogs(exe).items(), key=lambda t: (str(type(t[0])), t[0])):
        if did is not None and i != did:
            continue
        if grep and grep not in (cap + ' ' + ' '.join(c[2] for c in ctrls)).lower():
            continue
        print('DIALOG %s  "%s"' % (i, cap))
        for cid, kind, text, _ in ctrls:
            if kind in ('Static',) and not text.strip():
                continue
            print('   %5d  %-10s %s' % (cid, kind, text.replace('\n', ' ')))


if __name__ == '__main__':
    main(sys.argv[1:])
