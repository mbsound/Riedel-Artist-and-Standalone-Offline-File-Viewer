"""
Map dialog member offsets to Director's own control labels.

MFC dialogs bind controls in DoDataExchange with calls like DDX_xxx(pDX, IDC, &this->member).
This scans every such call in Director, groups them by the calling function (one per dialog class),
picks the dialog template whose control ids match best, and prints, per class:
    member offset, DDX kind, control id, control type, label
where the label is the control's own text (checkbox / radio / button) or the nearest static text
before it in the template. A setter that reads 'in_ECX + 0x260' is using the control at member
0x240 (its HWND sits at +0x20); a plain int member (checkbox / radio value) is used directly.

Usage: python tools/ddx_map.py > docs/director_ddx.txt
"""
import os, sys, re, struct, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dre import d, TEXT, va2off, dis, func_start
import dialogs as DLG

# DDX helpers found by call frequency with (pDX, IDC, &member) arguments.
DDX_FUNCS = {0x818bf7: 'control', 0x81916c: 'value', 0x81939f: 'radio'}


def call_sites():
    lo = va2off(TEXT[1])
    blob = d[lo:lo + TEXT[2]]
    for m in re.finditer(rb'\xe8(....)', blob, re.S):
        tgt = TEXT[1] + m.end() + struct.unpack('<i', m.group(1))[0]
        if tgt in DDX_FUNCS:
            yield TEXT[1] + m.start(), DDX_FUNCS[tgt]


def args_before(call):
    """Walk back over the three pushes: returns (idc or None, member offset or None)."""
    ins = [i for i in dis(call - 40, 20) if i.address < call][-8:]
    regs, idc, member = {}, None, None
    pushes = []
    for i in ins:
        if i.mnemonic == 'mov' and re.fullmatch(r'e[a-z]x, 0x[0-9a-f]+', i.op_str):
            regs[i.op_str[:3]] = int(i.op_str.split(', ')[1], 16)
        if i.mnemonic == 'lea':
            mm = re.fullmatch(r'(e[a-z]x), \[e[a-z]{2} \+ (0x[0-9a-f]+)\]', i.op_str)
            if mm:
                regs['lea_' + mm.group(1)] = int(mm.group(2), 16)
        if i.mnemonic == 'push':
            pushes.append(i.op_str)
    if len(pushes) >= 3:
        mem, idp = pushes[-3], pushes[-2]
        if re.fullmatch(r'0x[0-9a-f]+', idp):
            idc = int(idp, 16)
        elif idp in regs:
            idc = regs[idp]
        member = regs.get('lea_' + mem)
    return idc, member


def build():
    by_fn = collections.defaultdict(list)
    for call, kind in call_sites():
        idc, member = args_before(call)
        if idc is None or member is None:
            continue
        by_fn[func_start(call)].append((member, kind, idc))
    return by_fn


def labels_for(ctrls):
    """control id -> (type, label). Own text for checkbox / radio / button; otherwise the static text
    to the left on the same row, else the nearest static above."""
    statics = [(r, t.strip()) for cid, k, t, r in ctrls if k == 'Static' and t.strip()]
    out = {}
    for cid, kind, text, r in ctrls:
        if kind in ('Static', 'GroupBox'):
            continue
        own = text.strip()
        if own and kind in ('CheckBox', 'Radio', 'Button'):
            out.setdefault(cid, (kind, own))
            continue
        x, y, w, h = r
        cy = y + h / 2
        row = [(x - (sr[0] + sr[2]), t) for sr, t in statics
               if sr[1] - 2 <= cy <= sr[1] + sr[3] + 2 and sr[0] < x]
        if row:
            out.setdefault(cid, (kind, min(row)[1]))
            continue
        above = [(y - sr[1], t) for sr, t in statics if sr[1] < y and abs(sr[0] - x) < 40]
        out.setdefault(cid, (kind, min(above)[1] if above else ''))
    return out


def main():
    dlgs = DLG.dialogs()
    by_fn = build()
    for fn, rows in sorted(by_fn.items()):
        ids = {r[2] for r in rows}
        best, score = None, 0
        for did, (cap, ctrls) in dlgs.items():
            s = len(ids & {c[0] for c in ctrls})
            if s > score:
                best, score = did, s
        cap, ctrls = dlgs.get(best, ('?', []))
        lab = labels_for(ctrls)
        print('DDX %s  dialog %s "%s"  (%d/%d ids matched)' % (hex(fn), best, cap, score, len(ids)))
        for member, kind, idc in sorted(rows):
            t, l = lab.get(idc, ('?', ''))
            print('   +0x%-5x %-8s id %-6d %-9s %s' % (member, kind, idc, t, l))


if __name__ == '__main__':
    main()
