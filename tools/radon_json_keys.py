"""Resolve the JSON key strings in libRadon's JsonSerializer functions.

Ghidra leaves string literals in the decompiled serializers as  (char *)(DAT_007d4328 + 0x7d3d94) : the
DAT_ word is a PC-relative literal in the binary and the string lives at  word + constant. This reads
libRadon.so (ELF32 ARM, from the NIC firmware rootfs) and prints a serializer with every such expression
replaced by the string, so each JSON key (= the web GUI's field name) sits next to the member it writes.

usage: python tools/radon_json_keys.py FUNCTION_SUBSTRING [--all]
       e.g.  serializeNetSettings   serializeBPConfig   deserializeAudioChannel
"""
import pathlib
import re
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
# Which firmware: RADON_FW=3.4.1 (default) or 3.6.0, or explicit RADON_SRC (Ghidra output of
# docs/firmware_decomp/DecompileTargets.java) and RADON_LIB (the libRadon.so it was made from).
import os
FIRMWARE = {
    '3.4.1': ('libRadon_3.4.1_serializers.c', ('Firmware 2',)),
    '3.6.0': ('libRadon_3.6.0_serializers.c', ('Bolero_Firmware_v3.6.0_incl.RN',)),
}
_FW = os.environ.get('RADON_FW', '3.4.1')
SRC = pathlib.Path(os.environ.get('RADON_SRC') or HERE / 'docs' / 'firmware_decomp' / FIRMWARE[_FW][0])
LIB = pathlib.Path(os.environ.get('RADON_LIB') or HERE.parent.joinpath('Firmware', *FIRMWARE[_FW][1], 'extracted',
                                                                      'nic_rootfs', 'usr', 'lib', 'libRadon.so'))
BASE = 0x10000        # Ghidra loaded the shared object at 0x10000: decompiled address = ELF vaddr + BASE


class Elf:
    def __init__(self, path):
        self.d = path.read_bytes()
        shoff, = struct.unpack_from('<I', self.d, 0x20)
        shentsize, shnum = struct.unpack_from('<HH', self.d, 0x2e)
        self.secs = [struct.unpack_from('<IIIIIIIIII', self.d, shoff + i * shentsize) for i in range(shnum)]

    def off(self, vaddr):
        for s in self.secs:
            addr, off, size = s[3], s[4], s[5]
            if s[1] != 8 and addr and addr <= vaddr < addr + size:   # skip NOBITS
                return off + vaddr - addr
        return None

    def u32(self, vaddr):
        o = self.off(vaddr)
        return None if o is None else struct.unpack_from('<I', self.d, o)[0]

    def cstr(self, vaddr):
        o = self.off(vaddr)
        if o is None:
            return None
        end = self.d.find(b'\0', o, o + 200)
        raw = self.d[o:end] if end > 0 else b''
        return raw.decode('latin1') if raw and all(32 <= c < 127 for c in raw) else None


LIT = re.compile(r'\(char \*\)\(DAT_([0-9a-f]{8}) \+ (0x[0-9a-f]+)\)|\(DAT_([0-9a-f]{8}) \+ (0x[0-9a-f]+)\)'
                 r'|DAT_([0-9a-f]{8}) \+ (0x[0-9a-f]+)')


def resolve(body, elf):
    def sub(m):
        g = [x for x in m.groups() if x]
        addr, add = g[0], g[1]
        word = elf.u32(int(addr, 16) - BASE)
        s = elf.cstr((word + int(add, 16) - BASE) & 0xffffffff) if word is not None else None
        return f'"{s}"' if s is not None else m.group(0)
    return LIT.sub(sub, body)


def main(args):
    want = [a for a in args if not a.startswith('--')]
    text = SRC.read_text(encoding='utf-8', errors='replace')
    elf = Elf(LIB)
    heads = list(re.finditer(r'^// ==== (radon::[^\n]+?)  @ ([0-9a-f]+) ====$', text, re.M))
    for i, m in enumerate(heads):
        if not any(w in m.group(1) for w in want):
            continue
        body = text[m.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        if 'PTR_' in body and body.count('\n') < 15:
            continue                                                  # thunk
        body = resolve(body, elf)
        body = re.sub(r'rapidjson::\s*Writer<[^\n]*>\s*::', 'W::', body)
        body = re.sub(r'\(Writer<[^()]*(?:\([^()]*\))*[^()]*>\s*\*\)', '', body)
        print(f'// ==== {m.group(1)} @ {m.group(2)}')
        print('\n'.join(l for l in body.splitlines() if l.strip()))


if __name__ == '__main__':
    main(sys.argv[1:])
