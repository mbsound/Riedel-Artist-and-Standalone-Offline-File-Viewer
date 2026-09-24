"""
Static helpers for reading Riedel Director's Windows executable (no execution).
Usage (Python 3 + `pip install capstone`):
    DIRECTOR_EXE="path/to/Director 8.9.D2.exe" python3 -i tools/director_disasm.py
    >>> [ (hex(i.address), i.mnemonic, i.op_str) for i in dis(0x9dffe0, 20) ]
    >>> wstr(0x1016c30)   # UTF-16 string at a virtual address
Addresses below are for Director 8.9.D2 (image base 0x400000). See docs/FORMAT_NOTES.md.
"""
import os,struct,re,capstone
d=open(os.environ.get("DIRECTOR_EXE","Director 8.9.D2.exe"),'rb').read()
pe=struct.unpack('<I',d[0x3c:0x40])[0]; nsec=struct.unpack('<H',d[pe+6:pe+8])[0]; opt=struct.unpack('<H',d[pe+20:pe+22])[0]
base=struct.unpack('<I',d[pe+24+28:pe+24+32])[0]; secs=[]
for i in range(nsec):
    s=pe+24+opt+40*i; vsz,va,rsz,raw=struct.unpack('<IIII',d[s+8:s+24]); secs.append((va,vsz,raw,rsz))
def off2va(o):
    for va,vsz,raw,rsz in secs:
        if raw<=o<raw+rsz: return base+va+(o-raw)
def va2off(v):
    for va,vsz,raw,rsz in secs:
        if base+va<=v<base+va+max(vsz,rsz): return raw+(v-base-va)
def wstr(v):
    o=va2off(v)
    if o is None: return None
    e=o
    while e+1<len(d) and d[e:e+2]!=b'\0\0' and e-o<400: e+=2
    try:
        s=d[o:e].decode('utf-16le')
        return s if s and all(32<=ord(c)<127 for c in s) else None
    except: return None
md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_32)
def dis(va,n=80):
    o=va2off(va); return list(md.disasm(d[o:o+n*8],va))[:n]
