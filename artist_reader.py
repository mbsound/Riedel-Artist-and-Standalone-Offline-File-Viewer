"""
Sequential reader for Riedel Director `.Art` configuration files, transcribed from Director 8.9.D2's
own load code (see docs/FORMAT_NOTES.md Â§5). Unlike the pattern-matching parser in riedel_formats.py,
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


def u32_list(ar):
    return [ar.u32() for _ in range(ar.u32())]


# ---------------------------------------------------------------------------------------------
# Shared base trailer: CPhysObj::Serialize FUN_00ca8eb0 + user rights FUN_00caacf0.
# Every class's Serialize reads its own fields first and ends with this.
# ---------------------------------------------------------------------------------------------
def read_base(ar, o):
    o['base_5c'] = ar.u32()               # object field +0x5c (0x4000 in 8.6 files, 0x5000 in 8.9)
    o['owner_user'] = ar.u32()            # CPhysUser id (the "system id" of the old notes)
    o['base_58'] = ar.u32()               # object id looked up via FUN_0078e4f0, 0 = none
    n = ar.u32() if ar.version < 0x25 else ar.u8()
    o['user_rights'] = [(ar.u32(), ar.u8()) for _ in range(max(n, 0))]


# ---------------------------------------------------------------------------------------------
# Per-class readers. Each reads the class-specific part of the record into dict `o`.
# ---------------------------------------------------------------------------------------------
def read_web(ar, o):
    """CPhysWeb (0x001) FUN_00cd6b00: the configuration root."""
    o['name'] = ar.wstring() if ar.version < 0x30 else ar.string()
    o['demo_marker'] = ar.u32()           # 0xFEEDFEED = demo configuration (Director refuses to open)
    o['web_u32_a'] = ar.u32()             # written as 1
    o['web_7ad90'] = ar.u32() if ar.version >= 0x29 else 0
    if ar.version >= 0x530:
        o['web_7ad94'] = ar.u32()
        o['web_str_a'] = ar.string()
    if ar.version >= 0x535:
        o['web_str_b'] = ar.string()
    if ar.version >= 0x2c:
        f = ar.u32()
        o['web_flags'] = f                # bits 0..2 -> +0x8c/+0x8d/+0x8e
    elif ar.version > 0x10:
        o['web_flags'] = ar.u32()
    o['web_ids_a'] = u32_list(ar)         # object ids (+0x6efe4 array)
    o['web_ids_b'] = u32_list(ar)         # written empty
    if ar.version >= 0x13:
        o['web_list_c'] = u32_list(ar)    # +0x6f1b0
    if ar.version >= 0x18:
        entries = []
        for _ in range(ar.u32()):
            name = ar.wstring()
            a = u32_list(ar)
            b = u32_list(ar)
            entries.append({'name': name, 'a': a, 'b': b})
        o['web_named_lists'] = entries


# ----- cards (CPhysClient*) -----------------------------------------------------------------
def read_client(ar, o):
    """CPhysClient FUN_00c245b0: slot and frame."""
    o['slot'] = ar.i32()                  # +0x84 (bay = slot + 1 on 1024 frames)
    o['node'] = ar.u32()                  # CPhysNode id


def read_client_panel(ar, o):
    """CPhysClientPanel FUN_00c26820: classic 8-port card."""
    read_client(ar, o)
    o['ports'] = [(ar.u32(), ar.u32()) for _ in range(8)]   # (input object, output object) per port


def read_card_classic(ar, o):
    """COAX / CAT5 / AIO / ADAT / SubSic: FUN_00c277c0 and siblings."""
    read_client_panel(ar, o)


def read_card_madi(ar, o):
    """CPhysClientMadi FUN_00c256f0."""
    read_client_panel(ar, o)
    o['madi_bytes'] = ar._take(3).hex()


def read_card_dante(ar, o):
    """CPhysClientPanelDante FUN_00bf75b0."""
    read_client_panel(ar, o)
    o['dante_name'] = ar.string()


def read_card_gpio(ar, o):
    """CPhysClientGpio FUN_00c24d90: 16 GPIO in/out pairs."""
    read_client(ar, o)
    o['gpio'] = [(ar.u32(), ar.u32()) for _ in range(16)]


def read_card_voip(ar, o):
    """CPhysClientVoIP FUN_00c28870."""
    read_client_panel(ar, o)
    v = ar.version
    dhcp = ar.u8() if v >= 0x37 else 0
    if not dhcp:
        o['ip'], o['mask'], o['gateway'], o['voip_u32'] = ar.u32(), ar.u32(), ar.u32(), ar.u32()
    o['voip_dhcp'] = bool(dhcp)
    if v > 0x36:
        f2 = ar.u8()
        if not f2:
            o['voip_b1'], o['voip_b2'] = ar.u32(), ar.u32()
        o['voip_flag2'] = bool(f2)
        o['voip_u16'] = ar.u16()
        o['voip_name'] = ar.string()
        o['voip_u8'] = ar.u8()
    if v > 0x38:
        o['voip_u8b'] = ar.u8()


def read_sic_base(ar, o):
    """CPhysClientUic/Sic FUN_00c01900: network card base."""
    read_client(ar, o)
    o['sic_u8'] = ar.u8()
    o['name'] = ar.string()
    o['sic_u16a'] = ar.u16()
    o['sic_u16b'] = ar.u16()
    if ar.version >= 0x3e0:
        o['sub_objects'] = u32_list(ar)   # e.g. CPhysClientSubSic ids
    if ar.version >= 0x500:
        o['sic_list2'] = [ar.u32() for _ in range(ar.u16())]


def read_aes67_media(ar, o, owner_is_sic, key='media'):
    """CClientAES67MediaProperties FUN_00a057c0."""
    m = {}
    if ar.version >= 0x2f0:
        m['ip'], m['mask'], m['gateway'] = ar.u32(), ar.u32(), ar.u32()
        m['flag'] = ar.u32() & 1
        m['u16'] = ar.u16()
        m['u8a'] = ar.u8()
        m['u8b'] = ar.u8()
    if ar.version >= 0x450 and owner_is_sic:   # owner vtable+0xb8: true for SIC cards, false otherwise
        m['u8c'] = ar.u8()
    o.setdefault(key, []).append(m)


def read_aes67_ptp(ar, o):
    """CClientAES67PtpProperties FUN_00a06660."""
    if ar.version >= 0x240:
        o['ptp'] = {'u8': ar.u8(), 'a': ar.u32(), 'b': ar.u32(), 's1': ar.string(), 's2': ar.string()}


def read_aes67_a03fd0(ar, o):
    if ar.version >= 0x2f0:
        o['aes67_bytes'] = ar._take(9).hex()


def read_aes67_a037a0(ar, o):
    if ar.version >= 0x2f0:
        s = {'u16': ar.u16()}
        s['list'] = [ar.u16() for _ in range(ar.u16())]
        s['u8'], s['u32'], s['u16a'], s['u16b'], s['u8b'] = ar.u8(), ar.u32(), ar.u16(), ar.u16(), ar.u8()
        o['aes67_stream'] = s
    if ar.version >= 0x300:
        o['aes67_u8'] = ar.u8()


def read_card_aes67_old(ar, o):
    """FUN_00bf5ea0: AES67 panel card before file version 0x2f0."""
    v = ar.version
    m = {}
    if v > 0x45:
        m['ip'], m['mask'], m['gateway'] = ar.u32(), ar.u32(), ar.u32()
        m['flag'] = ar.u32() & 1
        m['u16'] = ar.u16()
        m['u8a'], m['u8b'] = ar.u8(), ar.u8()
    if v > 0x6f:
        m['u8c'], m['u8d'] = ar.u8(), ar.u8()
    if v > 0x19f:
        m['u8e'] = ar.u8()
    if v > 0x21f:
        m['u8f'] = ar.u8()
    o['media'] = [m]
    if v > 0x23f:
        read_aes67_ptp(ar, o)
    if v > 0x24f:
        o['aes67_bytes'] = ar._take(5).hex()
    if v > 0x2ef:
        read_aes67_a037a0(ar, o)


def read_card_panel_aes67(ar, o):
    """CPhysClientPanelAes67 FUN_00bf6370."""
    read_client_panel(ar, o)
    if ar.version < 0x2f0:
        read_card_aes67_old(ar, o)
    else:
        read_aes67_media(ar, o, owner_is_sic=False)
        read_aes67_ptp(ar, o)
        read_aes67_a03fd0(ar, o)
        read_aes67_a037a0(ar, o)


def read_card_nic(ar, o):
    """CPhysClientNic FUN_00bf5150: SIC base + 10 x (u8, u16, u16)."""
    read_sic_base(ar, o)
    o['nic_slots'] = [(ar.u8(), ar.u16(), ar.u16()) for _ in range(10)]


def read_card_sic_aes67(ar, o):
    """CPhysClientSicAes67 FUN_00bfb340 (+ FUN_00bfb150)."""
    v = ar.version
    read_sic_base(ar, o)
    if v >= 0x550:
        o['aes67_list_a'] = [ar.u32() for _ in range(ar.u8())]
        o['aes67_list_b'] = [ar.u32() for _ in range(ar.u8())]
    if v >= 0x320:
        o['interfaces'] = [(ar.u8(), ar.u8() if v >= 0x550 else None) for _ in range(3)]
    read_aes67_media(ar, o, owner_is_sic=True)
    if v >= 0x2f0:
        read_aes67_media(ar, o, owner_is_sic=True)      # secondary (redundant) network
    read_aes67_ptp(ar, o)
    read_aes67_a03fd0(ar, o)
    read_aes67_a037a0(ar, o)
    if v >= 0x370:
        o['aes67_16'] = ar._take(16).hex()
    if v >= 0x580:
        o['aes67_tail'] = (ar.u32(), ar.u16())


def read_card_sic_madi(ar, o):
    """CPhysClientSicMadi FUN_00c00360: two MADI interfaces."""
    read_sic_base(ar, o)
    ifs = []
    for _ in range(2):
        i = [ar.u8(), ar.u8()]
        if ar.version >= 0x310:
            i.append(ar.u8())
        if ar.version >= 0x410:
            i.append(ar.u8())
        ifs.append(i)
    o['madi_interfaces'] = ifs


def read_card_sic_dante(ar, o):
    """CPhysClientSicDante FUN_00a32b70."""
    read_sic_base(ar, o)
    o['dante_name'] = ar.string()
    if ar.version >= 0x4d0:
        o['dante_u8'] = ar.u8()


# ----- key commands (CPhysCommand subclasses) -------------------------------------------------
def old_string(ar):
    """FUN_00a8bab0: pre-0x43 string, u8 length + ANSI bytes."""
    n = ar.u8()
    return ar._take(n).decode('cp1252', errors='replace') if n else ''


def skip_counted(ar):
    """FUN_00dda1c0 + FUN_00dd77e0: a length and that many ignored bytes."""
    ar.skip(ar.str_len())


def read_cmd_head(ar, o, key='cmd_u8'):
    """The u8 + u16 every command starts with (u32 + u32 before 0x25). Returns the u16."""
    if ar.version < 0x25:
        o[key] = ar.u32() & 0xff
        w = ar.u32() & 0xffff
    else:
        o[key] = ar.u8()
        w = ar.u16()
    o['cmd_word'] = w
    return w


def read_old_port_list(ar):
    if ar.version < 0x25:
        ar.skip(3 * ar.u32())


def read_cmd_base(ar, o):
    """CPhysCommand FUN_00c57640: trailing command flags, object ref and name."""
    v = ar.version
    if v > 0x24:
        f = ar.u8()
        o['cmd_flags'] = f
        o['cmd_mode'] = (f >> 1) & 7      # +0x8c
        o['cmd_trunk_flag'] = f & 1       # vtable+0xec at save time
        if v > 0x39:
            o['cmd_bit4'] = (f >> 4) & 1  # +0x94
        if v > 0x2c:
            o['cmd_ref'] = ar.u32()       # FUN_0078e4f0 lookup, 0 = none
    if v >= 0x43:
        o['cmd_name'] = ar.string()
    elif v > 0x2f:
        o['cmd_name'] = old_string(ar)


def read_cmd_talk(ar, o):
    """CPhysCmdTalk (0x13, "Call to Port") FUN_00c543d0."""
    v = ar.version
    w = read_cmd_head(ar, o)
    trunk = (w >> 5) & 1                  # vtable+0xec = byte +0xb8 bit 5
    o['trunk'] = bool(trunk)
    f = ar.u32()
    o['talk_flags'] = f
    if v >= 0x28:
        o['talk_mode'] = f & 0x27
        if v >= 0x2f0:
            o['talk_b4'] = 0 if f & 0x40 else (1 if f & 0x80 else 2)
    if v >= 0x500:
        o['talk_ext'] = {'b8': (f >> 8) & 1, 'b9': (f >> 9) & 1, 'b10': (f >> 10) & 1, 'b11': (f >> 11) & 1}
    if v < 0x480:
        o['talk_old_u8'] = ar.u8()
    if v < 0x480 or not trunk:
        o['target'] = ar.u32()            # port object id (0 / 0xffffffff = none)
        o['target_u16a'] = ar.u16()
        o['target_u16b'] = ar.u16()
    read_old_port_list(ar)
    o['key'] = ar.u32()                   # owning CPhysCmdContainer (key) id
    if v >= 0x29 and (v < 0x480 or trunk):
        o['trunk_a'], o['trunk_b'] = ar.u32(), ar.u32()
        o['trunk_name'] = ar.string()
    if v >= 0x500:
        o['talk_str'] = ar.string()
    read_cmd_base(ar, o)


def read_cmd_listen(ar, o):
    """CPhysCmdListen (0x14) FUN_00c45650."""
    v = ar.version
    w = read_cmd_head(ar, o)
    trunk = (w >> 4) & 1                  # vtable+0xec = byte +0x98 bit 4
    o['trunk'] = bool(trunk)
    if v < 0x480:
        o['listen_old'] = ar._take(3).hex()
    if v < 0x480 or not trunk:
        o['target'] = ar.u32()
        o['target_u16'] = ar.u16()
    read_old_port_list(ar)
    o['key'] = ar.u32()
    if v >= 0x29 and (v < 0x480 or trunk):
        o['trunk_a'], o['trunk_b'] = ar.u32(), ar.u32()
        o['trunk_name'] = ar.string()
    read_cmd_base(ar, o)


def read_cmd_gpio(ar, o):
    """CPhysCmdGpio (0x15) FUN_00c3cf40."""
    v = ar.version
    o['cmd_word'] = ar.u32() if v < 0x25 else ar.u16()
    o['gpio'] = gid = ar.u32()            # CPhysGpioIn/Out id
    if v > 0x13:
        if v < 0x550:
            o['gpio_old'] = (ar.u16(), ar._take(5).hex())
        elif gid:
            k = ar.u8()
            o['gpio_kind'] = k
            if k == 0 or k == 3:
                o['gpio_ref'] = ar.u32()
            elif k == 1:
                o['gpio_port'], o['gpio_a'], o['gpio_b'] = ar.u16(), ar.u8(), ar.u8()
            elif k == 2:
                o['gpio_bytes'] = ar._take(4).hex()
    o['key'] = ar.u32()
    read_cmd_base(ar, o)


def read_cmd_conf(ar, o):
    """CPhysCmdConf (0x16, "Call to Conference") FUN_00c33340."""
    v = ar.version
    read_cmd_head(ar, o)
    o['conf_u8a'] = ar.u8()               # +0x99
    if v >= 0x11:
        o['conf_u8b'] = ar.u8()           # +0x9c
    o['conference'] = ar.u32()            # CPhysConf id
    o['key'] = ar.u32()
    if v >= 0x14:
        o['conf_u8c'] = ar.u8()           # +0x9b
    if 0x29 <= v <= 0x2a:
        ar.u32(); ar.u32(); skip_counted(ar)
    read_cmd_base(ar, o)


def read_cmd_group(ar, o):
    """CPhysCmdGroup (0x17, "Call to Group") FUN_00c3f620."""
    v = ar.version
    read_cmd_head(ar, o)
    o['group'] = ar.u32()                 # CPhysGroup id
    o['key'] = ar.u32()
    if 0x29 <= v <= 0x2a:
        ar.u32(); ar.u32(); skip_counted(ar)
    read_cmd_base(ar, o)


def read_cmd_reply(ar, o):
    """CPhysCmdReply (0x18) FUN_00c48460."""
    v = ar.version
    w = read_cmd_head(ar, o)
    if v >= 0x30:
        o['reply_flags'] = w & 7
    o['key'] = ar.u32()
    read_cmd_base(ar, o)


def read_cmd_route(ar, o):
    """CPhysCmdRoute (0x0a) FUN_00c4a6d0: route a source port to a destination port."""
    v = ar.version
    read_cmd_head(ar, o)
    if v < 0x480:
        o['route_old'] = ar._take(2).hex()
    o['route_a'], o['route_a_u16'] = ar.u32(), ar.u16()
    o['route_b'], o['route_b_u16'] = ar.u32(), ar.u16()
    read_old_port_list(ar)
    o['key'] = ar.u32()
    if 0x29 <= v < 0x480:
        for _ in range(2):
            ar.u32(); ar.u32(); skip_counted(ar)
    read_cmd_base(ar, o)


def read_cmd_logic(ar, o):
    """CPhysCmdLogic (0x44) FUN_00c47060."""
    o['logic'] = ar.u32()
    o['cmd_word'] = ar.u32() if ar.version < 0x25 else ar.u16()
    o['key'] = ar.u32()
    read_cmd_base(ar, o)


def read_cmd_beep(ar, o):
    """CPhysCmdBeep (0x35) FUN_00c2adf0."""
    o['cmd_word'] = ar.u32() if ar.version < 0x25 else ar.u16()
    o['target'] = ar.u32()
    o['target_u16'] = ar.u16()
    o['key'] = ar.u32()
    read_cmd_base(ar, o)


def read_cmd_call_ifb(ar, o):
    """CPhysCmdCallToIFB (0x67) FUN_00c2d410."""
    v = ar.version
    o['cmd_u8'] = ar.u8()
    w = ar.u16()
    o['cmd_word'] = w
    trunk = (w >> 5) & 1                  # vtable+0xec = byte +0xa8 bit 5
    o['trunk'] = bool(trunk)
    if v >= 0x2f0:
        b = ar.u8()
        o['ifb_mode'] = 0 if b & 1 else (1 if b & 2 else 2)
    if v < 0x480 or not trunk:
        o['ifb'] = ar.u32()               # CPhysIFB id (0 / 0xffffffff = none)
    o['key'] = ar.u32()
    if v >= 0x38 and (v < 0x480 or trunk):
        o['trunk_a'] = ar.u32()
        o['trunk_u16'] = ar.u16()
        o['trunk_name'] = ar.string()
    read_cmd_base(ar, o)


# ----- keys (CPhysKey) ------------------------------------------------------------------------
# Stored key mode (bits 6-7 of the first flag word) -> Director's internal mode value (+0x11c).
KEY_MODE_INTERNAL = {0: 1, 1: 2, 2: 3, 3: 0}


def read_key(ar, o):
    """CPhysKey (0x09) FUN_00c7b160 (+ key base FUN_00c21050)."""
    v = ar.version
    o['slot'] = ar.u32() if v < 0x25 else ar.u8()          # +0x10c key position on its holder
    o['label'] = ar._take(8).decode('cp1252', 'replace').rstrip('\0') if v < 0x43 else ar.string()
    if v < 0x25:
        ar.u32()
        o['key_b114'] = ar.u32()
        old = ar.u8()
        o['mode_internal'] = {0: 1, 1: 2, 2: 3}.get(old, 0)
        w1 = 0
    else:
        w1 = ar.u16()
        o['flags1'] = w1
        o['key_b114'] = (w1 >> 1) & 1
        o['key_b143'] = (w1 >> 2) & 1
        o['key_b142'] = (w1 >> 3) & 3
        o['key_b120'] = (w1 >> 5) & 1
        o['mode_internal'] = KEY_MODE_INTERNAL[(w1 >> 6) & 3]
    w2 = 0
    if v >= 0x2f0:
        w2 = ar.u16()
        o['flags2'] = w2
        o['key_b138'] = w2 & 1
        if v >= 0x350:
            o['key_b140'] = (w2 >> 1) & 1
        if v >= 0x560:
            o['key_b132'] = (w2 >> 8) & 1
    o['key_b141'] = (w2 >> 2) if v >= 0x430 else None
    o['key_u8'] = ar.u8()                                  # +0x118
    if v < 0x25:
        ar.u8()
        o['commands'] = u32_list(ar)
    else:
        o['commands'] = [ar.u32() for _ in range(ar.u16())]   # CPhysCommand ids on this key
        o['key_b129'] = (w1 >> 13) & 1
    o['holder'] = ar.u32()                                 # CPhysKeyHolder (panel / expansion) id
    sel = (w1 >> 8) & 3 if v >= 0x2c else 0
    o['key_b119'] = ar.u8() if sel == 2 else sel
    if v >= 0x3d and (w1 >> 10) & 1:
        if ar.u8() != 0xff:
            raise ArtFormatError('key colour marker at 0x%x' % (ar.p - 1))
        o['colour'] = ar._take(3).hex()
    o['key_b126'] = ar.u16() if v >= 0x3e and (w1 & 0x800) else 1
    if v >= 0x3e:
        o['key_b128'] = (w1 >> 12) & 1
    if v >= 0x1e0:
        o['long_name'] = ar.string()
        n = ar.i16()
        o['key_i16'] = 16 if n == -1 else n
        o['key_b131'] = (w1 >> 15) & 1
        o['key_b130'] = (w1 >> 14) & 1


# ----- network / frames ---------------------------------------------------------------------
def read_lwl(ar, o):
    """CPhysLWL (0x05) FUN_00c89bb0: fibre link between two frames."""
    o['lwl_pairs'] = [(ar.i32(), ar.i32()) for _ in range(ar.u32())]
    o['node_a'] = ar.u32()
    o['node_b'] = ar.u32()


def read_key_markers(ar, o):
    """FUN_00c96c20: panel key markers (u8 count; u32 flags, name, u8, u8 each)."""
    marks = []
    for _ in range(ar.u8()):
        flags = ar.u32()
        if ar.version < 0x2f:
            skip_counted(ar)
            name = ''
        else:
            name = ar.string()
        marks.append({'flags': flags, 'name': name, 'a': ar.u8(), 'b': ar.u8()})
    o['key_markers'] = marks


def read_net(ar, o):
    """CPhysNet (0x02) FUN_00c99630: system-wide settings."""
    v = ar.version
    if v < 0x43:
        o['net_name'] = ar._take(0x20).decode('cp1252', 'replace').rstrip('\0')
        if v < 0x2b:
            skip_counted(ar)
        skip_counted(ar)
    o['net_i32'] = [ar.i32() for _ in range(4)]          # +0x48c, +0x494, +0x490, +0x498
    o['net_list_a'] = u32_list(ar)
    o['net_list_b'] = u32_list(ar)
    o['web'] = ar.i32()                                  # CPhysWeb id
    o['net_6fc'] = ar.u8()
    read_key_markers(ar, o)
    b = o['net_bytes'] = {}
    b['49e'], b['49f'], b['4a0'] = ar.u8(), ar.u8(), ar.u8()
    if v < 0x350:
        ar.u8()
    m = ar.u8()
    if v < 0x50:
        m = {2: 7, 3: 3, 4: 2}.get(1 if m == 2 else m, 1)
    b['4a4'] = m
    b['4a8'] = ar.u8()
    ar.u8(); ar.u8()                                     # written as 7 and 2
    b['4a9'] = ar.u8()
    if v >= 0x340:
        b['4aa'] = ar.u8()
    for k in ('4ac', '4ad', '4b0', '4b1', '4b2', '4b3', '4b4', '4b5'):
        b[k] = ar.u8()
    if v >= 0x550:
        b['4b6'] = ar.u8()
    if v >= 0x560:
        b['4b7'] = ar.u8()
    for k in ('4b9', '4ba', '4bb', '4bc'):
        b[k] = ar.u8()
    ar.u8()                                              # written as 7
    for k in ('4bd', '4be', '4bf', '4d0', '4c3', '4c4', '4c5', '4c6', '4c7', '4c8'):
        b[k] = ar.u8()
    if v >= 0x25:
        b['4ab'] = ar.u8()
        if v < 0x350:
            ar.u8(); ar.u8()
        b['4c1'] = ar.u8() == 1
        b['4c0'] = ar.u8()
        s = ar.i16()
        o['net_718'] = s if s in (0x3a4, 0x4e3, 0x4e4) else 0
    if v > 0x25:
        ar.u8()                                          # written as 4
    if v >= 0x27:
        o['net_6fe'], o['net_700'] = ar.u16(), ar.u16()
    if v >= 0x30:
        o['net_702'] = ar.u16()
    if v >= 0x2c:
        b['4d1'] = ar.u8()
    if v >= 0x28:
        o['net_4ae'] = ar.u16()
    if v >= 0x3d:
        if ar.u8() != 0xff:
            raise ArtFormatError('net colour marker at 0x%x' % (ar.p - 1))
        o['net_colour'] = ar._take(3).hex()
    if v >= 0x44:
        b['4b8'] = ar.u8()
    if v >= 0x2f0:
        o['net_72c'], o['net_730'], o['net_734'] = ar.u8(), ar.u8(), ar.u8()
    elif v >= 0x210:
        o['net_72c'] = ar.u8()
    if v > 0x2f:
        o['net_strings'] = [ar.string() for _ in range(4)]
    if v >= 0x3c:
        o['net_71c'] = [ar.i32() for _ in range(4)]
    if v >= 0x3f:
        o['net_4d8'], o['net_4d4'] = ar.u8(), ar.u8()
        b['4c2'] = ar.u8() == 1
    if v > 0x3f:
        o['net_73c'] = ar.i32()
        o['net_744'], o['net_740'] = ar.u8(), ar.u8()
        o['net_749'] = ar.u8() == 1
        o['net_748'] = ar.u8()
        o['net_754'] = ar.u8() == 1
        o['net_strings2'] = [ar.string() for _ in range(3)]
    if v > 0x6f:
        o['net_759'], o['net_75b'], o['net_75c'] = ar.u8(), ar.u8(), ar.u8()
        o['net_760'], o['net_764'] = ar.i32(), ar.i32()
        o['net_768'], o['net_76a'] = ar.u16(), ar.u16()
        o['net_76c'] = ar.u8()
        o['net_76e'] = ar.u16()
        o['net_770'] = ar.u8()
    if v > 0x13f:
        o['net_75a'] = ar.u8()
    if v > 0x25f:
        o['net_4ca'] = ar.u16()
    if v > 0x34f:
        b['4ce'], b['4cf'] = ar.u8(), ar.u8()
    if v > 0x35f:
        o['net_772'] = ar.u16()
    if v > 0x3cf:
        o['net_secret_a'] = ar.string(inverted=True)     # stored bit-inverted
        o['net_secret_b'] = ar.string(inverted=True)
    if v > 0x3df:
        b['4cc'], b['4cd'] = ar.u8() != 0, ar.u8() != 0
    if v > 0x41f:
        o['net_788'], o['net_78a'] = ar.u8(), ar.u8()
        o['net_78b'] = ar.u8() == 1
        o['net_named_codes'] = [(ar.u16(), ar.string()) for _ in range(2)]   # CArray sized 2 in the constructor
    if v > 0x45f:
        o['net_789'] = ar.u8()
    if v > 0x46f:
        o['net_798'], o['net_79c'] = ar.i32(), ar.i32()
    if v > 0x4af:
        o['net_78c'] = ar.u8()
    if v > 0x4bf:
        o['net_78d'] = ar.u8()
    if v > 0x4ef:
        o['net_758'] = ar.u8() != 0
    if v > 0x55f:
        o['net_7a0'] = list(ar._take(0x13))
        o['net_7ec'] = ar.u8() != 0


def read_node(ar, o):
    """CPhysNode (0x03) FUN_00ca2500: an Artist frame."""
    v = ar.version
    o['node_format'] = ar.i32()                          # written as 0x580 by 8.9 (+0x4f4)
    if v < 0x43:
        o['name'] = ar._take(0x20).decode('cp1252', 'replace').rstrip('\0')
    o['node_geom'] = [struct.unpack('<f', ar._take(4))[0] for _ in range(4)]   # +0x514 +0x51c +0x518 +0x520
    o['slots'] = [ar.u32() for _ in range(18)]           # card object id per slot (+0xac)
    if v > 0x2f:
        o['slot_classes'] = [ar.u32() for _ in range(18)]   # the card's class code
    o['controllers'] = [ar.u32() for _ in range(2)]      # +0x504
    o['power_supplies'] = [ar.u32() for _ in range(2)]   # +0x50c
    o['net'] = ar.u32()                                  # CPhysNet id
    if v > 0x1d:
        ar.u32(); ar.u32()
        o['node_a0'], o['node_a4'], o['node_a8'] = ar.i32(), ar.i32(), ar.i32()
    o['node_list'] = [ar.u32() for _ in range(ar.i32())]   # +0xf4
    o['node_500'] = ar.u8()
    o['node_88'], o['node_8c'] = ar.i32(), ar.i32()
    o['node_4fc'], o['node_4fe'] = ar.u16(), ar.u16()
    ar.u32(); ar.u16(); ar.u32(); ar.u32()               # written as zeros
    o['node_90'] = ar.i32()
    o['node_4f8'] = ar.i32() if v >= 0x24 else 0
    if v > 0x2f:
        o['name'] = ar.string()


# ----- ports and panels (CPhys11xxBase::Serialize FUN_00cbcfa0 -> load FUN_00cad990) ----------
PANEL_12XX = (0x505, 0x506, 0x517)                   # RSP-1232HL, RSP-1216HL, DSP-1216HL
PANEL_23XX = (0x434, 0x435, 0x436, 0x443, 0x444)     # RSP-2318 Pro/Plus/Basic, DSP-2312 Plus/Basic


def read_gpio_ref(ar, o, prefix):
    """GPIO output reference + trigger union (same encoding as CPhysCmdGpio)."""
    v = ar.version
    o[prefix] = gid = ar.u32()
    if v > 0x13:
        if v < 0x550:
            o[prefix + '_old'] = (ar.u16(), ar._take(5).hex())
        elif gid:
            k = ar.u8()
            o[prefix + '_kind'] = k
            if k in (0, 3):
                o[prefix + '_ref'] = ar.u32()
            elif k == 1:
                o[prefix + '_port'], o[prefix + '_a'], o[prefix + '_b'] = ar.u16(), ar.u8(), ar.u8()
            elif k == 2:
                o[prefix + '_bytes'] = ar._take(4).hex()


def read_pool_holder(ar, o, pool_state=0):
    """FUN_00be1fa0: codec / SIP port pool membership (port +0x358)."""
    if pool_state == 2:
        o['pool_list'] = [ar.u32() for _ in range(ar.u8())]
    ref = ar.u32()
    o['pool_ref'] = ref
    if ref:
        kind = ar.u8()
        o['pool_kind'] = kind
        if kind in (0, 1):
            raise ArtFormatError('pool holder serializer (CPoolHolder%s) not implemented, at 0x%x'
                                 % ('Codec' if kind == 0 else 'Sip', ar.p))


def read_port_c0d420(ar):
    """FUN_00c0d420: 4-wire / AES67 audio stream settings (flag bit 0)."""
    v, s = ar.version, {}
    if v >= 0x1a0:
        s['name'] = ar.string()
    if v < 0x3f0:
        s['streams'] = [(ar.u32(), ar.u16())]
    else:
        s['streams'] = [(ar.i32(), ar.i16()) for _ in range(2)]
    if v >= 0x1a0:
        s['name2'], s['flag'] = ar.string(), ar.u8() == 1
        ar.u8()
    s['u16a'] = ar.u16()
    if v >= 0x70:
        s['u16b'] = ar.u16()
    if v >= 0x1a0:
        s['u8a'] = ar.u8()
    if v >= 0x1d0:
        s['u8b'] = ar.u8()
    return s


def read_port_stream(ar, with_u16b):
    """FUN_00c08780 (flag bit 1) / FUN_00c0b370 (flag bit 2): primary + secondary network streams."""
    v, s = ar.version, {}
    if v < 0x320:
        s['streams'] = [(ar.u32(), ar.u32(), ar.u16()) if with_u16b else (ar.u32(), ar.u16())]
    else:
        s['streams'] = [(ar.i32(), ar.i32(), ar.i16(), ar.string()) if with_u16b else
                        (ar.i32(), ar.i16(), ar.string()) for _ in range(2)]
    s['u16'], s['u8a'], s['u8b'] = ar.u16(), ar.u8(), ar.u8()
    s['u32a'], s['u32b'], s['u8c'] = ar.u32(), ar.u32(), ar.u8()
    if v < 0x320:
        s['old_name'] = ar.string()
    s['u8d'], s['u8e'] = ar.u8(), ar.u8()
    if v >= 0x1a0:
        s['u16c'] = ar.u16()
    if with_u16b and v >= 0x70:
        s['u16d'] = ar.u16()
    if with_u16b and v >= 0x1d0:
        s['u8f'] = ar.u8()
    if v >= 0x200:
        s['u32c'] = ar.u32()
    if v >= 0x370:
        s['bytes16'] = ar._take(16).hex()
    return s


def read_panel_ui(ar, cls):
    """C12xxPanelUIProperties FUN_00a2e1c0 / C23xxPanelUIProperties FUN_00a2dd00."""
    v, u = ar.version, {}
    if cls in PANEL_12XX:
        u['u8a'], u['u8b'] = ar.u8(), ar.u8()
    u['flag'] = ar.u8() == 1
    u['named_codes'] = [(ar.u16(), ar.string()) for _ in range(2)]   # copied from CPhysNet's 2 entries
    if v > 0x3cf:
        u['secret_a'], u['secret_b'] = ar.string(inverted=True), ar.string(inverted=True)
    if v > 0x4af:
        u['u8c'] = ar.u8()
    if v >= 0x4c0:
        u['u8d'] = ar.u8()
    return u


def read_port(ar, o, pool_state=0):
    """CPhys11xxBase load FUN_00cad990: every port, panel and beltpack type.
    pool_state 2 = the port is a pool holder (CDM-102 sets it via FUN_00be1700)."""
    v, cls = ar.version, o['class']
    o['port_208'] = ar.u8() if v >= 0x390 else 0xffffffff
    if v > 0x36:
        read_pool_holder(ar, o, pool_state)
    if v < 0x2c:
        o['name'] = ar._take(0x20).decode('cp1252', 'replace').rstrip('\0')
    elif v < 0x43:
        o['name'] = old_string(ar)
    if v < 0x2b:
        ar.skip(8)
    if v < 0x43:
        o['label'] = ar._take(8).decode('cp1252', 'replace').rstrip('\0')
        o['alias'] = ar._take(8).decode('cp1252', 'replace').rstrip('\0') if v >= 0x2d else ''
    else:
        o['name'] = ar.string()
        o['alias'] = ar.string()
    if v < 0x39:
        ar.skip(8)
    if v < 0x2e:
        o['port_2cc'], n = ar.u32(), ar.u32()
    else:
        o['port_2cc'], n = ar.u8(), ar.u8()
    ar.skip(4 * n)
    o['port_1b0'], o['port_1b1'], o['port_1b2'], o['port_2f4'] = ar.u8(), ar.u8(), ar.u8(), ar.u8()
    if v < 0x2e:
        ar.u8(); ar.u8()
    o['port_number'] = ar.u16()                          # +0x288
    if v >= 0x31:
        ar.skip(4 * ar.u32())
    else:
        raise ArtFormatError('port layout before file version 0x31 not implemented')
    o['card'] = ar.u32()                                 # CPhysClientPanel id
    n = ar.u16() if v >= 0x430 else 1
    o['scroll_lists'] = [ar.u32() for _ in range(n)]
    if v < 0x2e:
        ar.skip(4)
    read_gpio_ref(ar, o, 'gpio_out')
    n = ar.u32() if v < 0x2e else ar.u8()
    ar.skip(8 * n)
    ar.skip(0x30)
    if v >= 0x2e:
        ar.skip(4 * ar.u32())
    if v < 0x2e:
        o['port_1e8'] = ar.u8()
    o['port_1b3'] = ar.u8()
    if v < 0x2e:
        ar.skip(2)
    o['port_1b4'] = ar.u8()
    if v >= 0x340:
        o['port_1b5'] = ar.u8()
    flags = 0
    if 0x25 <= v < 0x2d:
        o['port_1b6'], o['port_flags_old'] = ar.u8(), ar.u8()
    elif v >= 0x2d:
        o['port_1b6'] = ar.u8()
        flags = o['port_flags'] = ar.u32()
    o['port_1b7'], o['port_1b8'] = ar.u8(), ar.u8()
    if v > 0x25:
        ar.u8()
    if v < 0x2e:
        ar.skip(3)
    o['port_1c1_5'] = ar._take(5).hex()
    if v < 0x2e:
        ar.skip(2)
    if v >= 0x27:
        o['port_1ba'] = ar.u16()
    if v >= 0x28:
        o['port_1bc'] = ar.u16()
    if v >= 0x29:
        o['trunk_address'] = ar.i32()                    # +0x2d0
    if 0x2a <= v <= 0x2d:
        raise ArtFormatError('port layout 0x2a-0x2d (FUN_00cab860) not implemented')
    if v >= 0x30:
        if ar.u8() & 1:
            s = {'s1': ar.string(), 's2': ar.string(), 's3': ar.string(), 'u32': ar.u32(),
                 'b': ar._take(4).hex()}
            if v >= 0x40:
                s['s4'] = ar.string()
            o['port_d0c2c0'] = s
        sub = 0
        if v > 0x45:
            sub = ar.u8()
            if v >= 0x320 and sub:
                o['port_214'] = ar.u8() - 1
            if sub & 1:
                o['audio_settings'] = read_port_c0d420(ar)
            if v > 0x6f:
                if sub & 2:
                    o['stream_rx'] = read_port_stream(ar, with_u16b=True)
                if sub & 4:
                    o['stream_tx'] = read_port_stream(ar, with_u16b=False)
        if v > 0x13f:
            b = ar.u8() if v < 0x390 else 0
            if (sub & 8) or (b & 1):
                s = {}
                if v > 0x13f:
                    s['u32'], s['u16a'], s['u16b'] = ar.u32(), ar.u16(), ar.u16()
                if v > 0x3af:
                    s['u16c'] = ar.u16()
                o['port_c101c0'] = s
        if v > 0x2ef and ar.u8() & 1:
            o['port_c10a80'] = (ar.u16(), ar.u16())
        o['port_str'] = ar.string()
    if v > 0x30:
        o['port_398'] = list(ar._take(ar.u8()))
        o['port_388'] = ar.u8()
    if v >= 0x3d and v >= 0x2d and (flags >> 21) & 1:
        if ar.u8() != 0xff:
            raise ArtFormatError('port colour marker at 0x%x' % (ar.p - 1))
        o['colour'] = ar._take(3).hex()
    if v < 0x43:
        if v >= 0x3a:
            ar.skip(8 + 6 + 4)
    else:
        o['port_strings'] = [ar.string() for _ in range(3)]
    if v >= 0x41:
        o['port_1cc'], o['port_1d0'] = ar.u8(), ar.u8()
    if v > 0x1df:
        o['port_str2'] = ar.string()
        if cls in PANEL_12XX:
            o['panel_ui'] = read_panel_ui(ar, cls)
    if v > 0x39f and cls in PANEL_23XX:
        o['panel_ui'] = read_panel_ui(ar, cls)
    if v > 0x51f:
        o['port_354'] = ar.u8() & 1
        o['phone_book'] = ar.u32()
    if v >= 0x380:
        o['port_338'] = ar.u16()


# Expansion panels: key slots stored = vtable+0xc0 x vtable+0xc8 (tools/class_consts.py 0xc0 0xc8).
EXPANSION_SLOTS = {0x00b: 32, 0x40b: 12, 0x40c: 32, 0x40e: 32, 0x40f: 32, 0x411: 32, 0x413: 32,
                   0x415: 32, 0x418: 32, 0x419: 24, 0x427: 32, 0x431: 16, 0x433: 12, 0x437: 48,
                   0x507: 32}


def read_expansion(ar, o):
    """CPhysDCP1016Eslave::Serialize FUN_00c65490: expansion panels and slave halves."""
    v = ar.version
    if v < 0x2c:
        o['name'] = ar._take(0x20).decode('cp1252', 'replace').rstrip('\0')
    o['expansion_id'] = ar.i32()                         # +0x188
    if v < 0x2c:
        ar.u32()
    o['key_slots'] = [ar.u32() for _ in range(EXPANSION_SLOTS[o['class']])]   # CPhysKey ids
    o['host_panel'] = ar.u32()                           # CPhysPanel this expansion is attached to


def read_cdm102(ar, o):
    """CPhysCDM102 FUN_00c23fa0: two short strings, then the normal port record."""
    if ar.version > 0x36:
        o['cdm_a'], o['cdm_b'] = old_string(ar), old_string(ar)
        read_port(ar, o, pool_state=2)
    else:
        read_port(ar, o)


def read_sip_phone(ar, o):
    """CPhysSipPhoneConnection (0x502) FUN_00cca330: SIP account + port record (pool holder)."""
    v = ar.version
    f = ar.u8()
    o['sip_flags'] = f
    o['sip_strings'] = [ar.string() for _ in range(6)]
    o['sip_i32'] = ar.i32()
    o['sip_u32'] = ar.u32()                              # written as 5
    if v > 0x3f:
        o['sip_str7'] = ar.string()
    read_port(ar, o, pool_state=2)


def read_codec_conn(ar, o):
    """CPhysCodecConnection (0x508) FUN_00a34540."""
    o['voip_device'] = ar.u32()                          # CPhysConnectVoipDevice id
    o['codec_u8'] = ar.u8()
    o['codec_flags'] = ar.u8()
    if ar.version > 0x53f:
        o['codec_str'] = ar.string()
    read_port(ar, o)


def read_nsa_conn(ar, o):
    """CPhysNsaConnectionIn/Out/Connection (0x513-0x515): NSA device ref + byte(s) + port record."""
    o['nsa_device'] = ar.i32()
    o['nsa_u8'] = ar.u8()
    if o['class'] == 0x515:
        o['nsa_u8b'] = ar.u8()
    read_port(ar, o)


def read_frame_module(ar, o):
    """CPhysCPU* FUN_00ca7420 / CPhysPowerSupply FUN_00cc0ae0: position + frame."""
    o['position'] = ar.i32()                             # +0x88
    o['node'] = ar.u32()                                 # CPhysNode id


def read_gpio_source(ar, o):
    """Shared tail of GPIO in/out: card / panel / device source, then the name."""
    o['card_gpio'] = ar.u32()                            # GPIO card (+0x8c into it)
    o['panel'] = ar.u32()                                # CPhysPanel (+0x188 into it)
    if ar.version > 0x54f:
        o['device'] = ar.i32()                           # FUN_007d8600 source (+0x4a8)
        o['nsa_device'] = ar.i32()
        o['gpio_u8'] = ar.u8()
    if ar.version > 0x2f:
        o['name'] = ar.string()


def read_gpio_in(ar, o):
    """CPhysGpioIn (0x0c) FUN_00c685a0."""
    v = ar.version
    if v < 0x30:
        o['name'] = ar._take(0x20).decode('cp1252', 'replace').rstrip('\0')
    elif v < 0x43:
        skip_counted(ar)
    o['gpio_110'], o['gpio_120'] = ar.i32(), ar.i32()
    o['users'] = u32_list(ar) if v < 0x25 else [ar.u32() for _ in range(ar.u16())]
    read_gpio_source(ar, o)


def read_gpio_out(ar, o):
    """CPhysGpioOut (0x0d) FUN_00c6a3d0."""
    v = ar.version
    if v < 0x30:
        o['name'] = ar._take(0x20).decode('cp1252', 'replace').rstrip('\0')
    elif v < 0x43:
        skip_counted(ar)
    o['gpio_110'], o['gpio_120'] = ar.i32(), ar.i32()
    o['gpio_128'] = ar.u8() if v < 0x550 else ar.u32()
    o['users'] = u32_list(ar) if v < 0x25 else [ar.u32() for _ in range(ar.u16())]
    if v < 0x2b:
        raise ArtFormatError('GPIO out before 0x2b not implemented')
    o['label'] = ar._take(8).decode('cp1252', 'replace').rstrip('\0') if v < 0x43 else ar.string()
    if v < 0x39:
        ar.skip(8)
    read_gpio_source(ar, o)


def read_scroll_list(ar, o):
    """CPhysScrollList (0x10) FUN_00cc6f30."""
    v = ar.version
    if v < 0x42:
        raise ArtFormatError('scroll list before 0x42 not implemented')
    entries = []
    for _ in range(ar.u16()):
        e = {'command': ar.u32()}
        w = ar.u16()
        e['flags'] = w
        e['u8'] = ar.u8()
        e['label'] = ar.string()
        if v >= 0x2c:
            e['u8b'] = ar.u8()
        if v >= 0x2f:
            e['i16'] = ar.i16()
        entries.append(e)
    o['entries'] = entries
    if v > 0x2f:
        o['name'] = ar.string()
    if v > 0x37f:
        o['scroll_flag'] = ar.u8() & 1


def read_member_gpio_tail(ar, o):
    """Group / conference tail: GPIO output, trunk flags + address, long name."""
    v = ar.version
    read_gpio_ref(ar, o, 'gpio_out')
    if v >= 0x25:
        o['flags'] = ar.u8()
        if v < 0x29:
            ar.skip(8)
        else:
            o['trunk_address'] = ar.i32()
    if v > 0x2f:
        o['long_name'] = ar.string()


def read_group(ar, o):
    """CPhysGroup (0x11, talk group) FUN_00c6d980."""
    v = ar.version
    if v < 0x42:
        raise ArtFormatError('group before 0x42 not implemented')
    o['label'] = ar.string()
    members = [ar.u32() for _ in range(ar.u32())]
    o['members'] = members
    o['member_words'] = [ar.u16() for _ in members]
    live = [m for m in members if m in ar.ids]          # Director drops unresolved members here
    if v > 0x36:
        o['member_flags'] = list(ar._take(len(live)))
    read_member_gpio_tail(ar, o)
    if v >= 0x380:
        o['group_90'] = ar.u16()
    if v > 0x55f:
        o['group_92'] = ar.u16()
        n = ar.i16()
        o['group_94'] = 16 if n == -1 else n


def read_conference(ar, o):
    """CPhysConf (0x12) FUN_00c59e90."""
    v = ar.version
    if v < 0x42:
        raise ArtFormatError('conference before 0x42 not implemented')
    o['label'] = ar.string()
    o['alias'] = ar.string()
    members = [ar.u32() for _ in range(ar.u32())]
    o['members'] = members
    o['member_words'] = [ar.u16() for _ in members]      # bit 0 -> member flag
    ar.skip(len(members))
    if v >= 0x11:
        o['member_flags'] = list(ar._take(len(members)))   # & 0xef on load
    read_member_gpio_tail(ar, o)
    if v > 0x55f:
        o['conf_ac'] = ar.u16()
        n = ar.i16()
        o['conf_ae'] = 16 if n == -1 else n


# Audio patch element chain built by the constructor (FUN_00c1f0c0(0, 0)), in array order.
# Current-format sizes: crosspoint 2 (level, on bit7), amp20db 1, switch 1, amp in/out 2, band-pass 2, limiter 8.
AUDIOPATCH_CHAIN = ([('crosspoint', 2)] * 36 + [('amp20db', 1)] * 2 + [('switch', 1)] +
                    [('amp_in', 2)] * 4 + [('bandpass', 2)] * 4 + [('limiter', 8)] * 2 +
                    [('bandpass', 2)] * 6 + [('limiter', 8)] * 4 + [('amp_out', 2)] * 6)


def read_audiopatch(ar, o):
    """CPhysAudiopatch (0x19) FUN_00c1ff70: per-port mixing / DSP matrix."""
    v = ar.version
    if v < 0x2f:
        raise ArtFormatError('audio patch before 0x2f not implemented')
    if v < 0x43:
        o['name_old'] = old_string(ar)
    o['patch_mode'] = ar.u32()                           # +0x84
    els = []
    for kind, size in AUDIOPATCH_CHAIN:
        b = ar._take(size)
        if kind == 'crosspoint':
            els.append({'kind': kind, 'level': b[0], 'on': b[1] >> 7})
        elif kind in ('amp_in', 'amp_out'):
            els.append({'kind': kind, 'gain': b[0], 'flag': b[1] >> 7})
        else:
            els.append({'kind': kind, 'values': list(b)})
    o['elements'] = els
    o['panel'] = ar.u32()                                # CPhysPanel the patch belongs to
    if v > 0x2f:
        o['name'] = ar.string()


def read_user(ar, o):
    """CPhysUser (0x23) FUN_00ccd0e0."""
    v = ar.version
    if v < 0x30:
        o['user_strings'] = [ar.wstring() for _ in range(4)]
        o['user_u16'], o['rights'] = ar.u16(), ar.u16()
        return
    o['name'], o['full_name'], o['password'] = ar.string(), ar.string(), ar.string()
    o['user_u16'] = ar.u16()
    o['rights'] = ar.u16() if v < 0x3f else ar.u32()


def read_virtfn(ar, o):
    """CPhysVirtFn (0x24) FUN_00ccec90: virtual function (a key without a physical button)."""
    v = ar.version
    if v < 0x2c:
        o['vf_type'] = ar._take(0x20).decode('cp1252', 'replace').rstrip('\0')
    o['vf_id'] = ar.i32()                                # +0x10c
    o['commands'] = u32_list(ar) if v < 0x25 else [ar.u32() for _ in range(ar.u16())]
    o['panel'] = ar.u32()


# ----- logic --------------------------------------------------------------------------------
LOGIC_SRC_TYPES_NO_REF = (1, 8, 9, 10, 0xc, 0xd, 0xe, 0xf)


def read_logic_src(ar, o):
    """CPhysLogicSrc (0x40) FUN_00c886b0: a logic input (GPI, port activity, key, ...)."""
    v = ar.version
    o['name'] = ar.wstring() if v < 0x2b else ar.string()
    if v < 0x2b:
        ar.wstring()
    o['label'] = ar.wstring() if v < 0x43 else ar.string()
    if v >= 0x2d:
        f = ar.u8()
        o['invert'], o['src_flag'] = f & 1, (f >> 1) & 1
    if v >= 0x2a:
        o['src_type'] = ar.u8()
        o['src_ref'] = ar.u32()                          # meaning depends on src_type


def read_logic_dst(ar, o):
    """CPhysLogicDst (0x41) FUN_00c7f8d0: a logic output."""
    v = ar.version
    if v < 0x43:
        o['name'] = ar._take(0x20).decode('cp1252', 'replace').rstrip('\0')
    o['rect'] = [ar.i32() for _ in range(4)]
    o['inputs_a'] = [ar.u32() for _ in range(ar.u8())]
    o['inputs_b'] = [ar.u32() for _ in range(ar.u8())]
    o['sources'] = [(ar.u32(), [ar.f32() for _ in range(4)]) for _ in range(ar.u8())]
    o['commands'] = [ar.u32() for _ in range(ar.i32())]
    if v > 0x2e:
        o['lines'] = [ar.u32() for _ in range(ar.u8())]
    o['dst_ref'] = ar.u32()
    if v > 0x2f:
        o['name'] = ar.string()


def read_logic_line(ar, o):
    """CPhysLogicLine (0x42) FUN_00c870e0: a wire between logic elements."""
    o['line_u8a'], o['line_u8b'] = ar.u8(), ar.u8()
    o['from'], o['to'], o['dst'] = ar.u32(), ar.u32(), ar.u32()
    o['points'] = [(ar.i32(), ar.i32()) for _ in range(ar.u32())]


def read_logic_gate(ar, o):
    """CPhysLogicGate (AND/OR/NOT/split/NOP/NOR/XOR/XNOR/NAND/D-flip-flop/mono-flop) FUN_00c82440."""
    if ar.version < 0x2b:
        skip_counted(ar)
    o['rect'] = [ar.u32() for _ in range(4)]
    o['inputs'] = [(ar.u32(), ar.u8()) for _ in range(ar.u8())]
    o['outputs'] = [(ar.u32(), ar.u8()) for _ in range(ar.u8())]
    o['dst'] = ar.u32()


def read_logic_monoflop(ar, o):
    """CPhysLogicGateMonoFlop (0x86) FUN_00c845a0: pulse time + retrigger flag, then the gate."""
    o['monoflop_time'] = ar.u32()
    o['monoflop_flag'] = ar.u8() & 1
    read_logic_gate(ar, o)


def read_logic_clock(ar, o):
    """CPhysLogicClock (0x87) FUN_00c7d8d0 (no base trailer)."""
    o['clock'] = [ar.u32() for _ in range(5)]
    o['dst'] = ar.u32()


# ----- shortlists, scheduler, events --------------------------------------------------------
def read_nothing(ar, o):
    """Root containers (port shortlists, group/conf shortlists, scheduler, events): trailer only."""


def read_port_shortlist(ar, o):
    """CPhysPortShortlist (0x41c) FUN_00cbffc0."""
    o['name'] = ar.string()
    o['panels'] = u32_list(ar)


def read_group_conf_shortlist(ar, o):
    """CPhysGroupConfShortlist (0x423) FUN_00c6fbd0."""
    o['name'] = ar.string()
    o['groups'] = u32_list(ar)
    o['conferences'] = u32_list(ar)


def read_scheduler_task(ar, o):
    """CPhysSchedulerTask (0x5a) FUN_00cc4d30."""
    o['name'] = ar.string()
    o['schedule'] = list(ar._take(7))                    # +0x88..0x8e (days / time fields)
    o['task_u16'] = ar.u16()
    o['event'] = ar.i32()


EVENT_ACTIONS = {1: 'mcr_conference', 2: 'call_to_conference', 3: 'port_to_port', 4: 'logic_source',
                 5: 'call_to_group', 6: 'call_to_port', 7: 'listen_to_port'}


def read_event_action(ar):
    """FUN_00c5f7a0 factory + CEvAct*::Serialize (vtable +0x28)."""
    v, t = ar.version, ar.u8()
    a = {'type': EVENT_ACTIONS.get(t, t)}
    if t == 1:                                           # CEvActMcrConf FUN_00c625a0
        a['conference'] = ar.u32()
        a['members'] = u32_list(ar)
    elif t == 2:                                         # CEvActCmdConf FUN_00c63fb0
        a['conference'], a['flags'], a['port'] = ar.u32(), ar.u8(), ar.u32()
    elif t == 3:                                         # CEvActPortToPort FUN_00c61bc0
        a['flags'], a['source'], a['dest'] = ar.u8(), ar.u32(), ar.u32()
        if v > 0x2f:
            a['label_a'], a['label_b'] = old_string(ar), old_string(ar)
    elif t == 4:                                         # CEvActCmdLogicSrc FUN_00c633b0
        a['logic_source'], a['port'] = ar.u32(), ar.u32()
    elif t == 5:                                         # CEvActCmdGroup FUN_00c63900
        a['group'], a['flag'], a['port'] = ar.u32(), ar.u8(), ar.u32()
    elif t in (6, 7):                                    # CEvActCallToPort / ListenToPort
        a['flags'], a['source'], a['dest'] = ar.u8(), ar.u32(), ar.u32()
        if t == 6 and v > 0x42:
            a['label'] = ar.string()
        elif v > 0x2f:
            a['label'] = old_string(ar)
    else:
        raise ArtFormatError('unknown event action type %d at 0x%x' % (t, ar.p - 1))
    return a


def read_event(ar, o):
    """CPhysEvent (0x5d) FUN_00c605c0."""
    o['active'] = ar.u8() != 0
    o['name'] = ar.string()
    o['actions'] = [read_event_action(ar) for _ in range(ar.u32())]


# ----- IFBs ---------------------------------------------------------------------------------
def read_ifb_endpoint(ar, name):
    """FUN_00c747b0: IFB audio endpoint; loaders registered for types 1, 2 and 4 only."""
    t = ar.u8() if ar.version >= 0x37 else 1
    if t == 0:
        return None
    e = {'role': name, 'type': t}
    if t == 1:                                           # port FUN_00aeeea0
        e['port'], e['u16'] = ar.u32(), ar.u16()
    elif t == 2:                                         # group FUN_00aee860
        e['group'] = ar.u32()
    elif t == 4:                                         # trunk FUN_00aef350
        e['a'], e['b'], e['u16'] = ar.u32(), ar.u32(), ar.u16()
    else:
        raise ArtFormatError('IFB endpoint type %d has no loader in Director' % t)
    return e


def read_ifb(ar, o):
    """CPhysIFB (0x66) FUN_00c74080."""
    o['ifb_number'] = ar.u16()
    if ar.version < 0x43:
        o['name'] = ar._take(8).decode('cp1252', 'replace').rstrip('\0')
    else:
        o['name'] = ar.string()
    o['input'] = read_ifb_endpoint(ar, 'input')
    o['mix_minus'] = read_ifb_endpoint(ar, 'mix-minus')
    o['output'] = read_ifb_endpoint(ar, 'output')
    d = ar.u8()
    o['dim_level'] = 5 if d > 7 else d                   # +0x20
    f = ar.u8()
    o['ifb_flag_a'], o['ifb_flag_b'] = f & 1, (f >> 1) & 1
    o['long_name'] = ar.string()


def read_ifb_container(ar, o):
    """CPhysIFBContainer (0x70) FUN_00c77d70: base trailer FIRST, then its own fields."""
    read_base(ar, o)
    o['container_u8'] = ar.u8()
    o['container_u32'] = ar.u32()


def read_phone_book(ar, o):
    """CPhysPhoneBook (0x1a) FUN_00a44c80."""
    o['entries'] = [{'name': ar.string(), 'number': ar.string()} for _ in range(ar.u16())]
    o['name'] = ar.string()


# Classes whose Serialize does not call CPhysObj::Serialize at the end (no trailing base record).
NO_BASE_TRAILER = {0x087, 0x070}

READERS = {
    0x001: read_web,
    0x002: read_net,
    0x003: read_node,
    0x040: read_logic_src,
    0x041: read_logic_dst,
    0x042: read_logic_line,
    0x043: read_logic_gate, 0x045: read_logic_gate, 0x046: read_logic_gate, 0x047: read_logic_gate,
    0x080: read_logic_gate, 0x081: read_logic_gate, 0x082: read_logic_gate, 0x083: read_logic_gate,
    0x084: read_logic_gate, 0x085: read_logic_gate, 0x086: read_logic_monoflop,
    0x087: read_logic_clock,
    0x059: read_nothing, 0x05c: read_nothing, 0x41b: read_nothing, 0x422: read_nothing,
    0x05a: read_scheduler_task,
    0x05d: read_event,
    0x41c: read_port_shortlist,
    0x423: read_group_conf_shortlist,
    0x066: read_ifb,
    0x01a: read_phone_book,
    0x070: read_ifb_container,
    0x010: read_scroll_list,
    0x019: read_audiopatch,
    0x023: read_user,
    0x024: read_virtfn,
    0x011: read_group,
    0x012: read_conference,
    0x00c: read_gpio_in,
    0x00d: read_gpio_out,
    0x00f: read_frame_module,
    0x037: read_frame_module,
    0x038: read_frame_module,
    0x039: read_frame_module,
    0x04c: read_frame_module,
    0x050: read_frame_module,
    0x051: read_frame_module,
    0x052: read_frame_module,
    0x06a: read_frame_module,
    0x408: read_cdm102,
    0x502: read_sip_phone,
    0x508: read_codec_conn,
    0x513: read_nsa_conn,
    0x514: read_nsa_conn,
    0x515: read_nsa_conn,
    0x005: read_lwl,
    0x009: read_key,
    0x00a: read_cmd_route,
    0x013: read_cmd_talk,
    0x014: read_cmd_listen,
    0x015: read_cmd_gpio,
    0x016: read_cmd_conf,
    0x017: read_cmd_group,
    0x018: read_cmd_reply,
    0x035: read_cmd_beep,
    0x044: read_cmd_logic,
    0x067: read_cmd_call_ifb,
    0x101: read_card_classic,       # COAX-108
    0x102: read_card_classic,       # CAT5-108
    0x103: read_card_classic,       # AIO-108
    0x106: read_card_classic,       # ADAT
    0x107: read_card_madi,
    0x108: read_card_voip,
    0x109: read_card_panel_aes67,
    0x10a: read_card_dante,
    0x10b: read_card_sic_aes67,
    0x10c: read_card_nic,
    0x10d: read_card_classic,       # CPhysClientSubSic (8-port block of a SIC card)
    0x10e: read_card_sic_madi,
    0x10f: read_card_sic_dante,
    0x201: read_card_gpio,
}
# Every class whose Serialize is CPhys11xxBase's (see tools/ghidra/serialize_list.txt).
for _c in (0x401, 0x402, 0x403, 0x404, 0x405, 0x406, 0x407, 0x409, 0x40a, 0x40d, 0x410, 0x412, 0x414,
           0x416, 0x417, 0x41a, 0x41d, 0x41e, 0x420, 0x421, 0x424, 0x425, 0x426, 0x428, 0x429, 0x430,
           0x432, 0x434, 0x435, 0x436, 0x438, 0x439, 0x440, 0x441, 0x442, 0x443, 0x444, 0x445,
           0x505, 0x506, 0x50d, 0x517):
    READERS[_c] = read_port
for _c in EXPANSION_SLOTS:
    READERS[_c] = read_expansion


def read_objects(ar, objs, stop_on_unknown=True):
    """The Serialize loop of FUN_00cd32c0: one record per directory entry, in order."""
    out = []
    ar.ids = {oid for _, oid, _ in objs}
    for cls, oid, grp in objs:
        fn = READERS.get(cls)
        start = ar.p
        if fn is None:
            if stop_on_unknown:
                return out, (cls, oid, grp, start)
            raise ArtFormatError('no reader for class 0x%x' % cls)
        o = {'class': cls, 'id': oid, 'group': grp, 'offset': start}
        fn(ar, o)
        if cls not in NO_BASE_TRAILER:
            read_base(ar, o)
        o['length'] = ar.p - start
        out.append(o)
    return out, None


def read_art(data):
    ar = Archive(data)
    hdr = read_header(ar)
    objs = read_directory(ar)
    hdr['directory_end'] = ar.p
    return hdr, objs, ar


def parse_art(data):
    """Read a whole .Art file. Returns (header, records). Raises ArtFormatError on any mismatch,
    including a missing 'ENDE' end marker (FUN_00cdc5a0 checks it the same way)."""
    hdr, objs, ar = read_art(data)
    recs, stop = read_objects(ar, objs)
    if stop:
        cls, oid, grp, pos = stop
        raise ArtFormatError('no reader for class 0x%x (%s) at 0x%x' % (cls, grp, pos))
    end = ar.wstring()
    if end != 'ENDE' or ar.p != len(data):
        raise ArtFormatError('expected ENDE at end of file, got %r at 0x%x' % (end, ar.p))
    return hdr, recs


if __name__ == '__main__':
    import sys, collections, pathlib, re
    names = {}
    for line in open(pathlib.Path(__file__).parent / 'docs' / 'director_class_codes.txt', encoding='utf-8'):
        m = re.match(r'0x([0-9a-f]+)\s+(\S+)', line)
        if m:
            names[int(m.group(1), 16)] = m.group(2)
    show_dir = '--dir' in sys.argv
    for f in [a for a in sys.argv[1:] if not a.startswith('--')]:
        data = open(f, 'rb').read()
        hdr, objs, ar = read_art(data)
        print('== %s: version 0x%x %s, %d objects, directory ends at 0x%x' % (
            pathlib.Path(f).name, hdr['version'], hdr['creator'], len(objs), ar.p))
        if show_dir:
            c = collections.Counter((cls, grp) for cls, _, grp in objs)
            for (cls, grp), n in sorted(c.items(), key=lambda x: x[0]):
                print('   %-32s 0x%03x %-28s %d' % (grp, cls, names.get(cls, '?'), n))
        try:
            recs, stop = read_objects(ar, objs)
        except ArtFormatError as e:
            print('   ERROR', e)
            continue
        done = collections.Counter(r['class'] for r in recs)
        print('   read %d records: %s' % (len(recs), ', '.join('%s x%d' % (names.get(c, hex(c)), n) for c, n in done.items())))
        if recs:
            last = recs[-1]
            print('   last record: %s id %d at 0x%x len %d, trailer 0x%x owner %d' % (
                names.get(last['class']), last['id'], last['offset'], last['length'], last['base_5c'], last['owner_user']))
        if stop:
            cls, oid, grp, pos = stop
            print('   stopped at %s (0x%x) id %d [%s] offset 0x%x' % (names.get(cls, '?'), cls, oid, grp, pos))
            print('   next bytes:', data[pos:pos + 64].hex(' '))
        elif ar.p < len(data):
            print('   finished at 0x%x; remaining %r' % (ar.p, data[ar.p:ar.p + 16]))
