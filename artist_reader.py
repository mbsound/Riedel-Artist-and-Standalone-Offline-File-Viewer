"""
Sequential reader for Riedel Director `.Art` configuration files, transcribed from Director 8.9.D2's
own load code (see docs/FORMAT_NOTES.md §5). Unlike the pattern-matching parser in riedel_formats.py,
this reads the file exactly the way Director does: header, object directory, then every object's
Serialize() record in directory order.

Function addresses in comments are Director 8.9.D2 virtual addresses.
"""
import struct


class ArtFormatError(Exception):
    pass


class Archive:
    """MFC CArchive reader over a bytes object."""

    def __init__(self, data, pos=0):
        self.d = data
        self.p = pos
        self.version = 0     # g_FileVersion (DAT_012a8968), the file's schema revision

    def _take(self, n):
        if self.p + n > len(self.d):
            raise ArtFormatError('read past end at 0x%x (+%d)' % (self.p, n))
        b = self.d[self.p:self.p + n]
        self.p += n
        return b

    def u8(self):
        return self._take(1)[0]

    def i8(self):
        return struct.unpack('<b', self._take(1))[0]

    def u16(self):
        return struct.unpack('<H', self._take(2))[0]

    def i16(self):
        return struct.unpack('<h', self._take(2))[0]

    def u32(self):
        return struct.unpack('<I', self._take(4))[0]

    def i32(self):
        return struct.unpack('<i', self._take(4))[0]

    def f32(self):
        return struct.unpack('<f', self._take(4))[0]

    def f64(self):
        return struct.unpack('<d', self._take(8))[0]

    def skip(self, n):
        self._take(n)

    def str_len(self):
        """FUN_00dda1c0: u8, 0xff -> u16, 0xffff -> u32."""
        n = self.u8()
        if n != 0xff:
            return n
        n = self.u16()
        if n != 0xffff:
            return n
        n = self.u32()
        if n >= 0x80000000:
            raise ArtFormatError('bad string length at 0x%x' % self.p)
        return n

    def string(self, inverted=False):
        """Ar_ReadString FUN_00ddb0e0: length + UTF-8 bytes (bitwise-inverted when `inverted`)."""
        n = self.str_len()
        b = self._take(n)
        if inverted:
            b = bytes(~x & 0xff for x in b)
        return b.decode('utf-8', errors='replace')

    def wstring(self):
        """MFC CString >> (FUN_007d58e0): FF FE FF marker, then length and UTF-16LE text."""
        n = self.u8()
        if n == 0xff:
            w = self.u16()
            if w == 0xfffe:
                n = self.str_len()
                return self._take(2 * n).decode('utf-16le', errors='replace')
            n = w if w != 0xffff else self.u32()
        return self._take(n).decode('latin-1')


# Object directory groups, in the order FUN_00cd32c0 reads them. Each entry:
#   (label, min_version_exclusive, kind, arg)
# kind 'pairs'  : u32 n, n x (u32 class, u32 id)
# kind 'ids'    : u32 n, n x u32 id, all of class `arg`
# kind 'keys'   : like 'pairs' for version >= 0x26, else 'ids' of class 0x0b
# kind 'zero'   : u32 that must be 0
# kind 'nested' : u32 container id (class arg[0]), u32 n, n x u32 id (class arg[1])  (FUN_00cd4fe0)
# kind 'conn'   : u32 n, n x ([u32 class if version >= 0x550 else 0x509], u32 id)
DIRECTORY = [
    ('cards', None, 'pairs', None),
    ('commands', None, 'pairs', None),
    ('keys (CPhysKey)', None, 'ids', 0x09),
    ('fibre links (CPhysLWL)', None, 'ids', 0x05),
    ('nets (CPhysNet)', None, 'ids', 0x02),
    ('nodes (CPhysNode)', None, 'ids', 0x03),
    ('ports / panels', None, 'pairs', None),
    ('reserved', None, 'zero', None),
    ('reserved', None, 'zero', None),
    ('reserved', None, 'zero', None),
    ('key holders / expansions', None, 'keys', None),
    ('CPUs', None, 'pairs', None),
    ('power supplies', None, 'ids', 0x0f),
    ('GPIO inputs', None, 'ids', 0x0c),
    ('GPIO outputs', None, 'ids', 0x0d),
    ('scroll lists', None, 'ids', 0x10),
    ('groups', None, 'ids', 0x11),
    ('conferences', None, 'ids', 0x12),
    ('audio patches', None, 'ids', 0x19),
    ('users', None, 'ids', 0x23),
    ('virtual functions', None, 'ids', 0x24),
    ('logic destinations', None, 'ids', 0x41),
    ('logic gates', None, 'pairs', None),
    ('logic clocks', 0x2e, 'ids', 0x87),
    ('logic lines', None, 'ids', 0x42),
    ('logic sources', None, 'ids', 0x40),
    ('ZMXIF / MCR', 0x12, 'pairs', None),
    ('MCR objects', 0x29, 'pairs', None),
    ('port shortlists', 0x2b, 'nested', (0x41b, 0x41c)),
    ('scheduled tasks', 0x2b, 'nested', (0x59, 0x5a)),
    ('events', 0x2b, 'nested', (0x5c, 0x5d)),
] + [('IFBs %d' % i, 0x2f, 'nested', (0x70, 0x66)) for i in range(1, 11)] + [
    ('group / conference shortlists', 0x2f, 'nested', (0x422, 0x423)),
    ('virtual keys', 0x2d, 'ids', 0x41f),
    ('connections / NSA devices', 0x4ff, 'conn', None),
    ('phone books', 0x50f, 'ids', 0x1a),
]


def read_header(ar):
    magic = ar.wstring()
    if magic != 'R2000 Cfg-File':
        raise ArtFormatError('not a Director configuration file (header %r)' % magic)
    ar.version = ar.u32()
    if ar.version < 0x10:
        raise ArtFormatError('file version 0x%x too old' % ar.version)
    creator = ar.string() if ar.version >= 0x2d else None
    return {'version': ar.version, 'creator': creator}


def read_directory(ar):
    """FUN_00cd32c0 up to the Serialize loop. Returns the ordered list of (class, id, group)."""
    objs = []
    ar.u32()                              # always 0
    web_id = ar.u32()                     # root CPhysWeb object id
    objs.append((0x001, web_id, 'root'))
    if ar.version > 0x22:
        ar.u32()                          # 0x1f5
    for label, minv, kind, arg in DIRECTORY:
        if minv is not None and ar.version <= minv:
            continue
        if kind == 'zero':
            if ar.u32() != 0:
                raise ArtFormatError('directory: expected 0 at 0x%x' % (ar.p - 4))
            continue
        if kind == 'nested':
            objs.append((arg[0], ar.u32(), label))
            n = ar.u32()
            objs += [(arg[1], ar.u32(), label) for _ in range(n)]
            continue
        n = ar.u32()
        if n > 100000:
            raise ArtFormatError('directory group %r count %d at 0x%x' % (label, n, ar.p - 4))
        for _ in range(n):
            if kind == 'ids':
                objs.append((arg, ar.u32(), label))
            elif kind == 'keys' and ar.version < 0x26:
                objs.append((0x0b, ar.u32(), label))
            elif kind == 'conn' and ar.version < 0x550:
                objs.append((0x509, ar.u32(), label))
            else:
                cls = ar.u32()
                objs.append((cls, ar.u32(), label))
    return objs


def read_art(data):
    ar = Archive(data)
    hdr = read_header(ar)
    objs = read_directory(ar)
    hdr['directory_end'] = ar.p
    return hdr, objs, ar


if __name__ == '__main__':
    import sys, collections, pathlib, re
    names = {}
    for line in open(pathlib.Path(__file__).parent / 'docs' / 'director_class_codes.txt', encoding='utf-8'):
        m = re.match(r'0x([0-9a-f]+)\s+(\S+)', line)
        if m:
            names[int(m.group(1), 16)] = m.group(2)
    for f in sys.argv[1:]:
        data = open(f, 'rb').read()
        hdr, objs, ar = read_art(data)
        print('== %s: version 0x%x %s, %d objects, directory ends at 0x%x, tail %r' % (
            pathlib.Path(f).name, hdr['version'], hdr['creator'], len(objs), ar.p, data[-12:]))
        c = collections.Counter((cls, grp) for cls, _, grp in objs)
        for (cls, grp), n in sorted(c.items(), key=lambda x: x[0]):
            print('   %-32s 0x%03x %-28s %d' % (grp, cls, names.get(cls, '?'), n))
