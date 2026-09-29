"""Pair each JSON key in a libRadon serializer with the member offset it writes.

After radon_json_keys.resolve(), a serializer reads like
    FUN_007d2358(local_40, "keyName");  ...  REST::putInt(local_40, *(int *)(param_1 + 0x20), ...)
This prints  key -> first member offset used after the key (and the put* call), e.g.
    profileId          +0x20   putInt
so the offsets can be matched with the ones an unpack() stores to (tools/radon_fields.py).

usage: python tools/radon_keymap.py serializeBPConfig [serializeVox ...]
"""
import re
import sys

import radon_json_keys as R

KEY = re.compile(r'(?:W::Key\(\w+,|FUN_007d2358\(\(string \*\)\w+,)"([^"]+)"\)')
OFF = re.compile(r'\((?:param_\d|this|p\w+)\s*\+\s*(0x[0-9a-f]+|\d+)\)|(?:param_\d|this)\[(0x[0-9a-f]+|\d+)\]'
                 r'|\*\(\w+ \*\)\((?:param_\d|this)\s*\+\s*(0x[0-9a-f]+|\d+)')
CALL = re.compile(r'(REST::put\w+|W::(?:StartArray|StartObject)|serialize\w+|\w+::(?:get\w+|is\w+))')


def keymap(name, text, elf):
    heads = list(re.finditer(r'^// ==== (radon::[^\n]+?)  @ ([0-9a-f]+) ====$', text, re.M))
    for i, m in enumerate(heads):
        if not m.group(1).endswith('::' + name) or int(m.group(2), 16) < 0x400000:
            continue
        body = R.resolve(text[m.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)], elf)
        lines = body.splitlines()
        print(f'== {m.group(1)}')
        for j, line in enumerate(lines):
            k = KEY.search(line)
            if not k:
                continue
            off = call = None
            for nxt in lines[j + 1:j + 8]:
                if KEY.search(nxt):
                    break
                o = OFF.search(nxt)
                if o and off is None and 'local_' not in nxt.split('=')[0][:0]:
                    off = next(x for x in o.groups() if x)
                c = CALL.search(nxt)
                if c and call is None:
                    call = c.group(1)
            print(f'  {k.group(1):32s} {("+" + hex(int(off, 0))) if off else "":8s} {call or ""}')


if __name__ == '__main__':
    text = R.SRC.read_text(encoding='utf-8', errors='replace')
    elf = R.Elf(R.LIB)
    for n in sys.argv[1:]:
        keymap(n, text, elf)
