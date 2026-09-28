import sys, struct
from capstone import *
LIB=r"Z:\Desktop\Verified Real Artist Files\Firmware\Firmware 2\extracted\nic_rootfs\usr\lib\libRadon.so"
d=open(LIB,"rb").read()
u=lambda f,o: struct.unpack_from(f,d,o)
e_shoff=u("<I",0x20)[0]; e_shentsize=u("<H",0x2e)[0]; e_shnum=u("<H",0x30)[0]; e_shstrndx=u("<H",0x32)[0]
secs=[u("<IIIIIIIIII",e_shoff+i*e_shentsize) for i in range(e_shnum)]
shstr=secs[e_shstrndx][4]
def sname(n):
    e=d.index(b"\0",shstr+n); return d[shstr+n:e].decode()
names={i:sname(s[0]) for i,s in enumerate(secs)}
sec={names[i]:s for i,s in enumerate(secs)}
dynsym=sec[".dynsym"]; dynstr=sec[".dynstr"]
def str_at(base,n):
    e=d.index(b"\0",base+n); return d[base+n:e].decode("latin1")
# parse symbols: name(4) value(4) size(4) info(1) other(1) shndx(2)
syms={}
cnt=dynsym[5]//16
for i in range(cnt):
    o=dynsym[4]+i*16
    nm,val,sz,info,oth,shndx=struct.unpack_from("<IIIBBH",d,o)
    if nm==0: continue
    name=str_at(dynstr[4],nm)
    syms[name]=(val,sz)
def vaddr_to_off(v):
    for s in secs:
        a,off,size=s[3],s[4],s[5]
        if s[1]!=8 and a<=v<a+size:  # not NOBITS
            return off+(v-a)
    return None
def find(sub):
    return [(n,v,sz) for n,(v,sz) in syms.items() if sub in n]
def disasm(name, maxbytes=None):
    # match exact or unique substring
    cands=[n for n in syms if n==name] or [n for n in syms if name in n]
    if not cands:
        print("NOT FOUND:",name); return
    n=cands[0]; val,sz=syms[n]
    thumb = val & 1
    addr = val & ~1
    off=vaddr_to_off(addr)
    if off is None: print("no off for",n); return
    size = sz or (maxbytes or 400)
    code=d[off:off+size]
    md=Cs(CS_ARCH_ARM, CS_MODE_THUMB if thumb else CS_MODE_ARM)
    md.detail=False
    print(f"### {n}  vaddr={hex(val)} off={hex(off)} size={size} {'THUMB' if thumb else 'ARM'}")
    for ins in md.disasm(code, addr):
        print(f"  {ins.address:08x}: {ins.mnemonic:8s} {ins.op_str}")

if __name__=="__main__":
    cmd=sys.argv[1]
    if cmd=="find":
        for n,v,sz in sorted(find(sys.argv[2]), key=lambda x:x[1]):
            print(f"{v:08x} size={sz:5d} {n}")
    elif cmd=="dis":
        disasm(sys.argv[2], int(sys.argv[3]) if len(sys.argv)>3 else None)

# ---- PLT / relocation resolution ----
def build_plt_map():
    # .rel.plt: Elf32_Rel { r_offset(u32), r_info(u32) }; sym = r_info>>8
    relplt=sec.get(".rel.plt")
    if not relplt: return {}
    got_targets={}  # got_addr -> symname
    base=relplt[4]; n=relplt[5]//8
    # dynsym ordered list for index lookup
    symlist=[]
    cnt=dynsym[5]//16
    for i in range(cnt):
        o=dynsym[4]+i*16
        nm=struct.unpack_from("<I",d,o)[0]
        symlist.append(str_at(dynstr[4],nm) if nm else "")
    for i in range(n):
        r_off,r_info=struct.unpack_from("<II",d,base+i*8)
        idx=r_info>>8
        got_targets[r_off]= symlist[idx] if idx<len(symlist) else f"?{idx}"
    return got_targets

_GOT=None
def plt_target(plt_addr):
    # A PLT stub: add ip,pc,#hi ; add ip,ip,#mid ; ldr pc,[ip,#lo]!
    global _GOT
    if _GOT is None: _GOT=build_plt_map()
    off=vaddr_to_off(plt_addr)
    from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM
    md=Cs(CS_ARCH_ARM,CS_MODE_ARM)
    ins=list(md.disasm(d[off:off+16],plt_addr))
    if len(ins)<3: return None
    hi=mid=lo=0
    try:
        hi=int(ins[0].op_str.split('#')[1],0)
        mid=int(ins[1].op_str.split('#')[1],0)
        # third: ldr pc,[ip,#lo]!
        lo=int(ins[2].op_str.split('#')[1].rstrip(']!'),0)
    except Exception as e:
        return None
    got = (plt_addr+8) + hi + mid + lo   # pc of first insn is addr+8
    return _GOT.get(got), hex(got)

def dis2(name, plt_annotate=True, size=None):
    from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM,CS_MODE_THUMB
    cands=[n for n in syms if n==name] or [n for n in syms if name in n]
    if not cands: print("NOT FOUND",name); return
    n=cands[0]; val,sz=syms[n]; thumb=val&1; addr=val&~1; off=vaddr_to_off(addr)
    size=size or sz or 600
    md=Cs(CS_ARCH_ARM, CS_MODE_THUMB if thumb else CS_MODE_ARM)
    print(f"### {n} vaddr={hex(val)} size={size} {'THUMB' if thumb else 'ARM'}")
    for ins in md.disasm(d[off:off+size],addr):
        line=f"  {ins.address:08x}: {ins.mnemonic:8s} {ins.op_str}"
        if plt_annotate and ins.mnemonic in ("bl","blx","b") and ins.op_str.startswith("#"):
            try:
                tgt=int(ins.op_str[1:],0)
                pt=plt_target(tgt)
                if pt and pt[0]: line+=f"    ; -> {pt[0][:80]}"
            except: pass
        print(line)

if __name__=="__main__" and len(sys.argv)>1 and sys.argv[1]=="dis2":
    dis2(sys.argv[2], size=int(sys.argv[3]) if len(sys.argv)>3 else None)
