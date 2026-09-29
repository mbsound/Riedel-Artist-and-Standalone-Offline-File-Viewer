"""Turn a 3.4-era .bol into the 3.6.0 layout, to exercise bol_faithful's version-gated readers.

No real 3.6 save was available, so this inserts the fields 3.6.0's libRadon reads, at the positions it reads them:
  network   v10 -> v12: adminPasswordHash string after the OTA PIN, japanDectMode u8 before radioFlags
  profiles  v17 -> v18: bpDescription string after each BPConfig's bpNumber
  beltpacks v19 -> v20: the same
  audio devices v6 -> v7 (same bytes)
and checks that the result parses exactly and that everything except the new fields matches the original.

usage: python tools/make_synthetic_36.py SAVE.bol [SAVE.bol ...]   (writes nothing unless --out DIR is given)
"""
import pathlib
import struct
import sys
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import bol_faithful as B  # noqa: E402

HASH = "5ynth371c" * 7                 # stands in for the stored password hash
JAPAN = 2


def pstr(text):
    b = text.encode()
    return bytes([len(b)]) + b


def insertions(data, secs):
    """{absolute offset: bytes to insert} for one decompressed container."""
    ins = {}
    net = next(x for x in secs if x["role"] == "network")
    p = net["start"]
    p += 1 + data[p]                     # netName
    p += 1 + 2 + 2                       # systemMode, adminPin, otaPin
    ins[p] = pstr(HASH)
    p += 4 + 1 + 1                       # audioMulticastGroup, ptpDomain, timeSource
    p += 1 + data[p]                     # ntpServer
    p += 4 + 6                           # timeOffset, timeFormat..frequencyHoppingMode
    ins[p] = bytes([JAPAN])

    # BPConfig starts: record them while parsing the original
    starts = []
    orig = B.up_bpconfig

    def spy(s):
        starts.append(s.p)
        return orig(s)
    B.up_bpconfig = spy
    try:
        for role in ("profiles", "beltpacks"):
            sec = next(x for x in secs if x["role"] == role)
            s = B.InputStream(data, sec["start"], sec["end"]); s.version = sec["version"]
            B.SECTION_READERS[role](s)
    finally:
        B.up_bpconfig = orig
    for n, q in enumerate(starts):
        q += 2                           # profileId
        q += 1 + data[q]                 # bpName
        q += 2                           # bpNumber
        ins[q] = pstr("Synthetic description %d" % n)
    return ins


def convert(raw):
    data, secs = B.read_container(raw)
    ins = insertions(data, secs)
    new_version = {"network": 12, "profiles": 18, "beltpacks": 20, "audio_devices": 7}
    out = bytearray(data[:23])
    for sec in secs:
        body = bytearray()
        for i in range(sec["start"], sec["end"]):
            body += ins.get(i, b"")
            body.append(data[i])
        hdr = bytearray(data[sec["start"] - 14:sec["start"]])
        struct.pack_into(">HI", hdr, 8, new_version.get(sec["role"], sec["version"]), len(body))
        out += hdr + body
    return raw[:7] + zlib.compress(bytes(out))


def strip_new(v):
    if isinstance(v, dict):
        return {k: strip_new(x) for k, x in v.items()
                if k not in ("bp_description", "admin_password_set", "japan_dect_mode", "japan_dect_mode_name",
                             "_sections")}
    if isinstance(v, list):
        return [strip_new(x) for x in v]
    return v


def main(argv):
    out_dir = None
    if "--out" in argv:
        i = argv.index("--out"); out_dir = pathlib.Path(argv[i + 1]); del argv[i:i + 2]
    ok = True
    for f in argv:
        path = pathlib.Path(f)
        raw = path.read_bytes()
        syn = convert(raw)
        tmp = pathlib.Path(out_dir or ".") / (path.stem + "_synthetic36.bol")
        tmp.write_bytes(syn)
        try:
            a, b = B.parse_file(str(path)), B.parse_file(str(tmp))
        finally:
            if not out_dir:
                tmp.unlink()
        net = b["network"]
        descs = [x["config"]["bp_description"] for sec in ("profiles", "beltpacks") for x in b[sec][sec]]
        same = strip_new(a) == strip_new(b)
        leaked = HASH in B.to_json_text(b, path.name)     # the hash itself must never be exported
        good = (same and not leaked and net["admin_password_set"] is True and net["japan_dect_mode"] == JAPAN
                and B.saved_by_firmware(b) == "3.6" and all(d.startswith("Synthetic description") for d in descs))
        ok &= good
        print("[%s] %s: %d descriptions, password set=%s, japan=%s, rest identical=%s, hash exported=%s"
              % ("OK" if good else "FAIL", path.name, len(descs), net["admin_password_set"],
                 net["japan_dect_mode_name"], same, leaked))
    print("ALL SYNTHETIC 3.6 SAVES OK:", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
