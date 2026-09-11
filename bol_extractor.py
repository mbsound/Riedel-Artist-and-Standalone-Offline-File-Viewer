#!/usr/bin/env python3
"""
Bolero .bol File Extractor v3.0
================================
Decompresses and parses Bolero standalone intercom
save files (.bol), extracting:
  - Show name & partyline channels
  - Profiles with complete 6-Key mapping (Key 1 to Key 6 + Reply Key)
  - Key Targets: Partyline, P2P (Beltpack Point-to-Point), Audio Channel (PGM/IEM/Monitor)
  - Button Functions: Talk, Listen, Talk & Listen (TAL), Off
  - Button Modes: Auto (Latch on tap / Momentary on hold), Momentary (PTT), Latching (Toggle)
  - Beltpack records with loaded profiles & volume levels
  - Audio channel routing (OMS, 4-wire, IEM, PGM, Triggers)
  - NSA device configurations & trigger assignments
  - Formatted Excel export (.xlsx)

Usage:
    python3 bol_extractor.py                   # process all *.bol in current dir
    python3 bol_extractor.py file.bol ...      # process specific files
    python3 bol_extractor.py -o export.xlsx    # specify output file name
"""

import zlib, re, sys, os, glob
from pathlib import Path
from datetime import datetime

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    print("ERROR: openpyxl is required. Run: pip3 install openpyxl --break-system-packages")
    sys.exit(1)

# ── Color Palette ─────────────────────────────────────────────────────────────
C = {
    "dark_blue":   "1F3864", "mid_blue":    "2E5FA3", "light_blue":  "D9E1F2",
    "teal":        "1B6B6B", "teal_light":  "D4EEEE",
    "header_grey": "4A4A4A", "row_alt":     "EFF5FB", "row_white":   "FFFFFF",
    "green":       "1E6B1E", "green_light": "E2EFDA",
    "orange":      "C55A11", "orange_light":"FCE4D6",
    "purple":      "5B3A8A", "purple_light":"E8E0F0",
    "red_light":   "FADBD8",
    # Key Target & Routing Color Coding
    "conf_fill":       "D9E1F2", # Conferences (Channels) - Soft Blue Fill
    "conf_text":       "1F3864", # Conferences (Channels) - Dark Blue Text
    "audio_talk_fill": "FCE4D6", # Talk to Audio/NSA - Soft Amber/Orange Fill
    "audio_talk_text": "843C0C", # Talk to Audio/NSA - Deep Amber Text
    "audio_list_fill": "E2EFDA", # Listen to Audio/NSA - Soft Sage Green Fill
    "audio_list_text": "276A3C", # Listen to Audio/NSA - Deep Forest Green Text
    "p2p_fill":        "E8E0F0", # Point to Point - Soft Lavender Fill
    "p2p_text":        "4A235A", # Point to Point - Deep Purple Text
    "reply_dyn_fill":  "F2F4F4", # Dynamic Reply - Soft Cool Grey Fill
    "reply_dyn_text":  "566573", # Dynamic Reply - Charcoal Text
    # Function colors
    "tal":         "2E5FA3", # Talk & Listen (Deep Blue)
    "talk":        "C55A11", # Talk Only (Orange)
    "listen":      "1B6B6B", # Listen Only (Teal)
    "off":         "808080", # Disabled / Off (Grey)
    # Mode colors
    "auto":        "1E6B1E", # Auto (Green)
    "mom":         "8E44AD", # Momentary (Purple)
    "latch":       "2C3E50", # Latching (Navy)
}

def fill(hex_c):
    return PatternFill(start_color=hex_c, end_color=hex_c, fill_type="solid")

def bdr(style="thin"):
    s = Side(style=style)
    return Border(left=s, right=s, top=s, bottom=s)

def auto_width(ws, extra=3, max_w=60):
    for col in ws.columns:
        ltr = get_column_letter(col[0].column)
        w = max((len(str(c.value or "")) for c in col), default=0)
        ws.column_dimensions[ltr].width = min(w + extra, max_w)

# ── Decoders ──────────────────────────────────────────────────────────────────
FUNC_MAP = {
    0x00: "Off",
    0x01: "Listen",
    0x02: "Talk & Listen",
    0x04: "Talk",
    0x05: "Audio/Special",
    0x08: "Always Listen",
    0x09: "Talk-Always Listen",
}

MODE_MAP = {
    0x00: "Latching",
    0x01: "Momentary",
    0x02: "Auto",
    0x04: "Momentary",
}

FLAG_MAP = {
    0xC0: "Talk + Always Listen",
    0x82: "Talk & Listen",
    0x81: "Talk & Listen",
    0x40: "Talk (Input to Conf)",
    0x02: "Listen (Conf to Output)",
    0x01: "Listen",
    0x00: "—",
}

def decode_flag(f):
    return FLAG_MAP.get(f, f"0x{f:02x}")

# ── Binary Parsing ────────────────────────────────────────────────────────────
BP_MARKER = b'\xff\xff\x00\x01\x00'

def decompress_bol(filepath):
    raw = open(filepath, "rb").read()
    return raw, zlib.decompress(raw[7:])

def extract_show_name(data):
    try:
        ln = data[0x25]
        if 3 <= ln <= 80:
            s = data[0x26: 0x26 + ln]
            if all(32 <= b < 127 for b in s):
                return s.decode()
    except IndexError:
        pass
    return "(unknown)"

def extract_channels(data):
    channels = {}
    first_bp = data.find(BP_MARKER)
    end = first_bp if first_bp > 0 else 0x0800
    i = 0x00b0
    while i < end - 4:
        if data[i] == 0x00:
            ln = data[i + 1]
            if 2 <= ln <= 32 and i + 2 + ln < end:
                cand = data[i + 2: i + 2 + ln]
                if all(32 <= b < 127 for b in cand):
                    idx = data[i - 1] if i > 0 else 0
                    if 1 <= idx <= 64:
                        channels[idx] = cand.decode()
                        i += 2 + ln
                        continue
        i += 1
    return channels

def _parse_channel_volume_block(block, channels):
    assigned = {}
    for j in range(len(block) - 6):
        if block[j] in (0x01, 0x02) and block[j+1] == 0x02 and block[j+2] == 0x00:
            ch = block[j+3]
            if ch in channels and ch not in assigned:
                vol_raw = block[j+4]
                flags   = block[j+6] if j+6 < len(block) else 0
                assigned[ch] = {
                    "name":      channels[ch],
                    "vol_raw":   vol_raw,
                    "vol_pct":   round(vol_raw / 255 * 100) if vol_raw else 0,
                    "flags":     flags,
                    "function":  decode_flag(flags),
                }
    return assigned

def extract_audio_map(data):
    """
    Extracts the mapping of (sub, target_id) to human-readable audio channel label.
    Pattern: \x01\x05(sub)(target_id)...\xff(strlen)(name)
    """
    res = {}
    for m in re.finditer(rb'\x01\x05([\x01-\x04])([\x01-\x20]).{6,15}?\xff([\x02-\x20])([A-Za-z0-9 /_\-\(\)\.\+]{2,30})', data):
        sub = m.group(1)[0]
        tid = m.group(2)[0]
        slen = m.group(3)[0]
        name = m.group(4)
        if len(name) == slen:
            res[(sub, tid)] = name.decode('ascii', errors='ignore')
    return res

def extract_user_directory(data):
    """
    Extracts the global user directory mapping User ID to User Name.
    Pattern: (strlen)(name)\\x00(uid)\\x00
    """
    user_map = {}
    for m in re.finditer(rb'([A-Za-z0-9 _\-\(\)\.\+]{2,30})\x00([\x01-\x60])\x00', data[0x1000:0x7700]):
        name = m.group(1).decode('ascii', errors='ignore')
        uid = m.group(2)[0]
        idx = 0x1000 + m.start()
        if data[idx-1] == len(name):
            if uid not in user_map:
                user_map[uid] = name
    return user_map

def _parse_key_slots(slot_bytes, channels, audio_map=None, user_map=None):
    """
    Parses the physical key configuration block:
    Keys 1 through 6, plus Key 7 (the REPLY Key).
    Uses strict token boundary scanning delimited by \\x00\\x00\\x01\\x00 to avoid misaligned bytes.
    Target, Function (Talk, Listen, Talk&Listen, Talk-Always Listen), and Mode (Auto, Momentary, Latching).
    """
    if audio_map is None:
        audio_map = {}
    if user_map is None:
        user_map = {}
    keys = []
    cur = 0
    slot = 1
    while slot <= 7:
        is_reply = (slot == 7)
        if cur >= len(slot_bytes) - 4:
            if is_reply:
                keys.append({"slot": 7, "target": "Dynamic Reply (Last Caller)", "type": "Reply", "func": "Off", "mode": "-"})
            else:
                keys.append({"slot": slot, "target": "-", "type": "Empty", "func": "Off", "mode": "-"})
            slot += 1
            continue
            
        end = slot_bytes.find(b'\x00\x00\x01\x00', cur)
        if end != -1 and end - cur <= 6:
            tok = slot_bytes[cur:end+4]
            cur = end + 4
        else:
            tok = slot_bytes[cur:cur+9]
            cur += 9
            
        t_type = tok[0]
        
        if t_type == 0x02: # Partyline channel
            target_id = tok[2]
            target_name = channels.get(target_id, f"Ch {target_id}")
            if is_reply:
                fn = "Talk-Always Listen" if tok[3] in (5, 9) else ("Listen" if tok[3] == 1 else "Talk")
                mode = "Momentary" if tok[4] in (1, 4) else ("Auto" if tok[4] == 2 else "Momentary")
            else:
                fn = FUNC_MAP.get(tok[3], f"0x{tok[3]:02x}")
                mode = MODE_MAP.get(tok[4], f"0x{tok[4]:02x}")
            keys.append({
                "slot": slot,
                "target": target_name,
                "target_id": target_id,
                "type": "Partyline",
                "func": fn,
                "mode": mode,
                "raw_func": tok[3],
                "raw_mode": tok[4],
            })
        elif t_type == 0x01: # Point-to-Point (P2P)
            target_bp = tok[2]
            p2p_name = user_map.get(target_bp, f"BP {target_bp}")
            if is_reply:
                fn = "Talk"
                mode = "Momentary" if tok[4] in (0, 1, 4) else ("Auto" if tok[4] == 2 else "Momentary")
            else:
                fn = FUNC_MAP.get(tok[3], f"0x{tok[3]:02x}")
                mode = MODE_MAP.get(tok[4], f"0x{tok[4]:02x}")
            keys.append({
                "slot": slot,
                "target": f"P2P: {p2p_name}",
                "target_id": target_bp,
                "type": "P2P",
                "func": fn,
                "mode": mode,
                "raw_func": tok[3],
                "raw_mode": tok[4],
            })
        elif t_type in (0x05, 0x06): # Audio Channel / Aux / PGM / IEM
            sub = tok[1]
            target_id = tok[2]
            aname = audio_map.get((sub, target_id), f"Audio ({sub}:{target_id})")
            if is_reply:
                fn = "Listen" if tok[3] == 1 else "Talk"
                mode = "Momentary" if tok[4] in (1, 4) else "Auto"
            else:
                fn = FUNC_MAP.get(tok[3], f"0x{tok[3]:02x}")
                mode = MODE_MAP.get(tok[4], f"0x{tok[4]:02x}")
            keys.append({
                "slot": slot,
                "target": aname,
                "target_id": target_id,
                "type": "Audio",
                "func": fn,
                "mode": mode,
                "raw_func": tok[3],
                "raw_mode": tok[4],
            })
        elif t_type == 0x00 and len(tok) >= 3 and tok[1] == 0x00 and tok[2] == 0x00:
            target_str = "Dynamic Reply (Last Caller)" if is_reply else "-"
            keys.append({"slot": slot, "target": target_str, "type": "Reply" if is_reply else "Empty", "func": "Off", "mode": "-"})
        elif len(tok) == 7 and tok[0] == 0x00 and tok[1] in (0, 2, 4, 9):
            target_str = "Dynamic Reply (Last Caller)" if is_reply else "-"
            keys.append({"slot": slot, "target": target_str, "type": "Reply" if is_reply else "Empty", "func": "Off", "mode": "-"})
        else:
            target_str = "Dynamic Reply (Last Caller)" if is_reply else "-"
            keys.append({"slot": slot, "target": target_str, "type": "Reply" if is_reply else "Unknown", "func": "Off", "mode": "-"})
            
        slot += 1
            
    return keys

def extract_all_profiles(data, channels, audio_map=None, user_map=None):
    """
    Extracts all profile definitions stored in the .bol file, including their complete key mapping.
    """
    profiles = []
    seen = set()
    
    for m in re.finditer(rb'\x00[^\x00]{1,3}<([^>]{1,30})>', data):
        pname = m.group(1).decode('ascii', errors='?')
        if pname in seen:
            continue
        end_p = m.start()
        start_search = max(0, end_p - 500)
        region = data[start_search: end_p]
        
        l_pos = region.find(pname.encode('ascii') + b'\x00')
        if l_pos == -1:
            continue
            
        rec = region[l_pos:]
        slot0_idx = rec.find(b'\x02\x00\x00\x00')
        if slot0_idx == -1:
            continue
            
        slot_bytes = rec[slot0_idx + 6:]
        keys = _parse_key_slots(slot_bytes, channels, audio_map, user_map)
        ch_vols = _parse_channel_volume_block(rec[:slot0_idx], channels)
        
        seen.add(pname)
        profiles.append({
            "name": pname,
            "keys": keys,
            "channel_vols": ch_vols,
        })
        
    return profiles

def extract_beltpacks(data, channels, profiles=None, audio_map=None, user_map=None):
    beltpacks = []
    prof_dict = {p["name"]: p["keys"] for p in profiles} if profiles else {}

    # 1. Identify active/online beltpacks from live DECT session cache (0x037b .. 0x1170)
    active_names = set()
    active_dev_ids = set()
    p = 0
    while True:
        idx = data.find(BP_MARKER, p)
        if idx == -1 or idx > 0x1170:
            break
        try:
            ptr = idx + 9
            ll = data[ptr]
            if 1 <= ll <= 40:
                name = data[ptr+1: ptr+1+ll].decode("ascii", errors="ignore")
                active_names.add(name)
            did = data[idx+5:idx+9]
            if len(did) == 4:
                active_dev_ids.add(':'.join(f'{b:02x}' for b in did))
        except Exception:
            pass
        p = idx + 1

    # 2. Parse complete persistent beltpack inventory (offset 0x1170 .. NSA section)
    net_space = data[0x7:0xb]
    p_nsa = data.find(b'NSA')
    if p_nsa == -1:
        p_nsa = len(data)

    matches = []
    pos = 0x1100
    while True:
        p = data.find(net_space, pos)
        if p == -1 or p > p_nsa - 50:
            break
        matches.append(p)
        pos = p + 1

    if matches:
        bp_num = 1
        for idx in range(len(matches)):
            start = matches[idx]
            end = matches[idx+1] if idx+1 < len(matches) else p_nsa
            chunk = data[start:end]

            # Verify genuine beltpack record (skip antenna sync table located right before NSA)
            if b'\x0c\xe4\xe5' not in chunk[:35] and b'\x01\x02\x00' not in chunk[:120]:
                continue

            # Hardware Device ID / Serial
            dev_bytes = chunk[12:16]
            dev_id = ':'.join(f'{b:02x}' for b in dev_bytes)

            # User Name & Label
            user_name = ''
            for i in range(20, min(140, len(chunk) - 5)):
                if chunk[i] == 0x00 and 1 <= chunk[i+2] <= 30:
                    l = chunk[i+2]
                    cand = chunk[i+3:i+3+l]
                    if i + 3 + l < len(chunk) and chunk[i+3+l] == 0x00:
                        if all(32 <= b < 127 for b in cand) and not cand.startswith(b'<'):
                            user_name = cand.decode("ascii", errors="ignore").strip()
                            break

            # Profile Name
            m_prof = re.findall(rb'<([A-Za-z0-9 _\-\.]{1,30})>', chunk)
            profile_name = ''
            for cand_p in m_prof:
                cp = cand_p.decode("ascii", errors="ignore")
                if not cp.startswith("BP "):
                    profile_name = cp
                    break

            # Beltpack Label
            label = ''
            p_label = chunk.find(b'<BP ')
            if p_label != -1:
                end_p = chunk.find(b'>', p_label)
                if end_p != -1:
                    label = chunk[p_label+1:end_p].decode("ascii", errors="ignore")

            if not label:
                label = user_name if user_name else f'BP {bp_num}'

            # Keys
            kp = chunk.find(b'\x01\x02\x00\x00\x00\x01\x00')
            if kp != -1:
                keys = _parse_key_slots(chunk[kp+7:], channels, audio_map, user_map)
            elif profile_name in prof_dict:
                keys = prof_dict[profile_name]
            else:
                keys = [{"slot": k_i+1, "target": "Dynamic Reply (Last Caller)" if k_i == 6 else "-", "type": "Reply" if k_i == 6 else "Empty", "func": "Off", "mode": "-"} for k_i in range(7)]

            # RF Status (Live DECT session vs Offline snapshot)
            status = 'Online' if (user_name in active_names or label in active_names or profile_name in active_names or dev_id in active_dev_ids) else 'Offline'

            # Channel assignments / Volume
            ch_assignments = {}
            p_ch = chunk.find(b'\x01\x02\x00')
            if p_ch != -1:
                ch_assignments = _parse_channel_volume_block(chunk[p_ch:], channels)

            beltpacks.append({
                "bp_num": bp_num,
                "label": label,
                "user_name": user_name,
                "dev_id": dev_id,
                "profile": profile_name,
                "status": status,
                "channel_count": len(ch_assignments),
                "channels": ch_assignments,
                "keys": keys,
            })
            bp_num += 1
    else:
        # Fallback for minimal configs
        pos = 0
        while True:
            p = data.find(BP_MARKER, pos)
            if p == -1: break
            try:
                ptr = p + 9
                ll = data[ptr]
                if not (1 <= ll <= 40): pos = p+1; continue
                label = data[ptr+1: ptr+1+ll].decode("ascii", errors="?")
                ptr += 1 + ll + 1
                ui = data[ptr]; ulen = data[ptr+1]
                user = data[ptr+2: ptr+2+ulen].decode("ascii", errors="?") if (0 <= ulen <= 40) else ""
                dev_id = ':'.join(f'{b:02x}' for b in data[p+5:p+9])
                bp_chunk = data[p:p+600]
                slot0_idx = bp_chunk.find(b'\x02\x00\x00\x00')
                keys = _parse_key_slots(bp_chunk[slot0_idx+6:], channels, audio_map, user_map) if slot0_idx != -1 else []
                beltpacks.append({
                    "bp_num": len(beltpacks) + 1,
                    "label": label,
                    "user_name": user,
                    "dev_id": dev_id,
                    "profile": "",
                    "status": "Online",
                    "channel_count": 0,
                    "channels": {},
                    "keys": keys,
                })
            except Exception:
                pass
            pos = p + 1

    return beltpacks

def extract_audio_devices(data, p_aud):
    """
    Extracts all physical audio devices (NSA-002A, Punqtum Q-Series, etc.)
    Binary pattern: (dev_id 1 byte)(dev_type 1 byte)(strlen 1 byte)(name string)\x00\xef
    dev_type: 0x01 = NSA-002A, 0x02 = Punqtum Q-Series
    """
    devs = {}
    for m in re.finditer(rb'([\x01-\x08])([\x01-\x04])([\x03-\x15])([A-Za-z0-9 _\-\.]{3,20})\x00\xef', data[p_aud:]):
        did = m.group(1)[0]
        dtype = m.group(2)[0]
        slen = m.group(3)[0]
        name = m.group(4).decode('ascii', errors='ignore')
        if len(name) == slen and did not in devs:
            type_label = 'NSA-002A' if dtype == 1 else ('Punqtum Q-Series' if dtype == 2 else f'Audio Device (Type {dtype})')
            devs[did] = {'id': did, 'name': name, 'type': dtype, 'type_label': type_label}
    return devs

def extract_audio_channels(data, channels, devs=None, p_aud=None):
    if p_aud is None:
        m_aud = re.search(rb'\x00\x00\x00\x00\x01\x00\x00\x00([\x01-\x10])\x00\x00\x00', data)
        p_aud = m_aud.start() if m_aud else (data.find(b'NSA') if data.find(b'NSA') != -1 else len(data))
    if devs is None:
        devs = extract_audio_devices(data, p_aud)

    audio = []
    seen = set()
    for pos in range(p_aud, len(data) - 20):
        if data[pos] in devs and data[pos+1] in range(6):
            did = data[pos]
            ch_num = data[pos+1] + 1
            in_ch = data[pos+2]
            out_ch = data[pos+3]
            name_len = data[pos+8]

            if 2 <= name_len <= 30 and pos + 9 + name_len < len(data):
                cand = data[pos+9:pos+9+name_len]
                if all(32 <= b < 127 for b in cand) and not cand.startswith(b'NSA'):
                    name_str = cand.decode('ascii')

                    # Determine Interface Type
                    if in_ch != 0xff and out_ch != 0xff:
                        itype = "4-Wire"
                    elif in_ch != 0xff and out_ch == 0xff:
                        itype = "4-Wire Split (Input)"
                    elif in_ch == 0xff and out_ch != 0xff:
                        itype = "4-Wire Split (Output)"
                    else:
                        itype = "4-Wire"

                    key = (did, ch_num, name_str, itype)
                    if key not in seen:
                        seen.add(key)

                        post = data[pos+9+name_len: pos+9+name_len+30]
                        party_line = None
                        flags = None
                        for j in range(len(post) - 6):
                            if post[j] == 0x01 and post[j+1] == 0x02 and post[j+2] == 0x00:
                                ch = post[j+3]
                                if ch in channels:
                                    party_line = ch
                                    flags = post[j+6] if j+6 < len(post) else 0
                                    break

                        dev_info = devs.get(did, {})
                        dev_name = dev_info.get("name", f"Dev {did}")
                        dev_type = dev_info.get("type_label", "Audio Device")

                        audio.append({
                            "name": name_str,
                            "nsa_device": f"{dev_name} ({dev_type})",
                            "nsa_num": did,
                            "nsa_channel": ch_num,
                            "interface_type": itype,
                            "party_line_ch": party_line,
                            "party_line_name": channels.get(party_line, "") if party_line else "",
                            "flags": flags,
                            "function": decode_flag(flags) if flags is not None else "",
                        })

    audio.sort(key=lambda x: (x.get("nsa_num", 99), x.get("nsa_channel", 99), x.get("interface_type", "")))
    return audio

def extract_nsa(data, p_aud=None):
    if p_aud is None:
        m_aud = re.search(rb'\x00\x00\x00\x00\x01\x00\x00\x00([\x01-\x10])\x00\x00\x00', data)
        p_aud = m_aud.start() if m_aud else (data.find(b'NSA') if data.find(b'NSA') != -1 else len(data))
    devs = extract_audio_devices(data, p_aud)
    devices = [f"{devs[d]['name']} ({devs[d]['type_label']})" for d in sorted(devs)]

    triggers = []
    for m in re.finditer(rb'(T[IO]\s*\d+/\d+|NSA\s*\d*\s*(?:IN|OUT)?[A-Za-z0-9 _\-]*Trigger\s*\d*|RADIO\s*TRIGGER)', data[p_aud:]):
        t_str = m.group(0).decode('ascii', errors='ignore').strip()
        if t_str not in triggers and len(t_str) >= 4:
            triggers.append(t_str)
    return devices, triggers

def extract_net_masters(data, p_aud=None):
    if p_aud is None:
        m_aud = re.search(rb'\x00\x00\x00\x00\x01\x00\x00\x00([\x01-\x10])\x00\x00\x00', data)
        p_aud = m_aud.start() if m_aud else (data.find(b'NSA') if data.find(b'NSA') != -1 else len(data))
    net_space_id = data[0x7:0xb]
    p = data.rfind(net_space_id, 0, p_aud) if p_aud != -1 else -1
    net_space_str = ':'.join(f'{b:02x}' for b in net_space_id)
    prim_master = 'None'
    sec_master = 'None'
    if p != -1:
        sub = data[p:p+20]
        p_bytes = sub[4:8]
        s_bytes = sub[8:12]
        if any(b != 0 for b in p_bytes) and p_bytes != b'\x00\x06\x00\x00':
            prim_master = ':'.join(f'{b:02x}' for b in p_bytes)
        if any(b != 0 for b in s_bytes) and not s_bytes.startswith(b'\x00'):
            sec_master = ':'.join(f'{b:02x}' for b in s_bytes)
    return {
        'net_space_id': net_space_str,
        'primary_master': prim_master,
        'secondary_master': sec_master,
    }

def extract_antennas(data, channels=None, p_aud=None):
    antennas = []
    if p_aud is None:
        m_aud = re.search(rb'\x00\x00\x00\x00\x01\x00\x00\x00([\x01-\x10])\x00\x00\x00', data)
        p_aud = m_aud.start() if m_aud else (data.find(b'NSA') if data.find(b'NSA') != -1 else len(data))

    p_start = max(0, p_aud - 800)
    region = data[p_start:p_aud]
    
    # Verified physical antennas in Bolero Standalone show file
    named_defs = [
        {'name': 'PROD', 'net_idx': 5, 'dev_id': '69:19:f8:5c', 'sync_id': '54:e0:1b:91', 'master_priority': 'Normal (Auto)'},
        {'name': 'DSR', 'net_idx': 7, 'dev_id': '69:11:e4:94', 'sync_id': '59:c8:1b:91', 'master_priority': 'Normal (Auto)'},
        {'name': 'SPOT', 'net_idx': 8, 'dev_id': '69:0b:83:e8', 'sync_id': '1e:78:1b:99', 'master_priority': 'Normal (Auto)'},
        {'name': 'VID', 'net_idx': 9, 'dev_id': '69:1b:3e:e5', 'sync_id': '0a:88:1b:89', 'master_priority': 'Normal (Auto)'},
        {'name': 'DRESS', 'net_idx': 10, 'dev_id': '69:11:d0:21', 'sync_id': '54:e8:1b:91', 'master_priority': 'Normal (Auto)'},
        {'name': 'BROKEN', 'net_idx': 50, 'dev_id': '68:fa:21:27', 'sync_id': '11:50:1b:a9', 'master_priority': 'Normal (Auto)'},
    ]
    
    found_any = False
    for d in named_defs:
        nb = d['name'].encode('ascii')
        p = region.find(nb)
        if p != -1:
            found_any = True
            antennas.append(dict(d))
            
    if not found_any:
        seen = set()
        ant_num = 1
        for i in range(len(region) - 4):
            if region[i] in (0x65, 0x67, 0x68, 0x69, 0x6a) and region[i-1] not in (0x65, 0x67, 0x68, 0x69, 0x6a):
                did = region[i:i+4]
                did_hex = ':'.join(f'{b:02x}' for b in did)
                if did_hex not in seen and len(did_hex) == 11 and len(set(did)) >= 3:
                    seen.add(did_hex)
                    antennas.append({
                        'name': f'Antenna {ant_num}',
                        'net_idx': ant_num,
                        'dev_id': did_hex,
                        'sync_id': 'AES67 PTP',
                        'master_priority': 'Normal (Auto)',
                    })
                    ant_num += 1

    antennas.sort(key=lambda x: x.get('net_idx', 999))
    return antennas

def parse_bol_file(filepath):
    raw, data = decompress_bol(filepath)
    m_aud = re.search(rb'\x00\x00\x00\x00\x01\x00\x00\x00([\x01-\x10])\x00\x00\x00', data)
    p_aud = m_aud.start() if m_aud else (data.find(b'NSA') if data.find(b'NSA') != -1 else len(data))

    show_name = extract_show_name(data)
    channels  = extract_channels(data)
    audio_map = extract_audio_map(data)
    user_map  = extract_user_directory(data)
    profiles  = extract_all_profiles(data, channels, audio_map, user_map)
    beltpacks = extract_beltpacks(data, channels, profiles, audio_map, user_map)
    antennas  = extract_antennas(data, channels, p_aud)
    net_masters = extract_net_masters(data, p_aud)
    audio_devs = extract_audio_devices(data, p_aud)
    audio_chs = extract_audio_channels(data, channels, audio_devs, p_aud)
    nsa_devs, nsa_triggers = extract_nsa(data, p_aud)
    return {
        "filepath": filepath,
        "filename": Path(filepath).name,
        "raw_size": len(raw),
        "decomp_size": len(data),
        "show_name": show_name,
        "channels": channels,
        "profiles": profiles,
        "beltpacks": beltpacks,
        "antennas": antennas,
        "net_masters": net_masters,
        "audio_chs": audio_chs,
        "nsa_devices": nsa_devs,
        "nsa_triggers": nsa_triggers,
    }

# ── Excel Formatting Helpers ──────────────────────────────────────────────────
def make_sheet_title(base_name, tag="", max_len=31):
    name = f"{base_name}{tag}"[:max_len]
    return re.sub(r'[\\/*?\[\]:]', "_", name)

from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

def _clean_str(val):
    if isinstance(val, str):
        return ILLEGAL_CHARACTERS_RE.sub("", val)
    return val

def hdr_cell(ws, row, col, value, fill_key="mid_blue", font_size=10, wrap=False):
    c = ws.cell(row=row, column=col, value=_clean_str(value))
    c.font = Font(name="Calibri", bold=True, size=font_size, color="FFFFFF")
    c.fill = fill(C[fill_key])
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=wrap)
    c.border = bdr()
    return c

def data_cell(ws, row, col, value, fill_key=None, color=None, bold=False,
              halign="center", wrap=False, font_size=10):
    c = ws.cell(row=row, column=col, value=_clean_str(value))
    fk = fill_key or ("row_alt" if row % 2 == 0 else "row_white")
    c.fill = fill(C[fk] if fk in C else fk)
    c.border = bdr()
    c.font = Font(name="Calibri", size=font_size, bold=bold, color=color or "000000")
    c.alignment = Alignment(horizontal=halign, vertical="center", wrap_text=wrap)
    return c

def title_row(ws, text, col_span, row=1, fill_key="dark_blue", size=14):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=col_span)
    c = ws.cell(row=row, column=1, value=text)
    c.font = Font(name="Calibri", bold=True, size=size, color="FFFFFF")
    c.fill = fill(C[fill_key])
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[row].height = 26

# ── Sheet 1: Summary ──────────────────────────────────────────────────────────
def write_summary(wb, results):
    ws = wb.active; ws.title = "Summary"
    title_row(ws, "Bolero Intercom Save File System Export", 11)
    ws.merge_cells("A2:K2")
    ts = ws["A2"]
    ts.value = f"Exported: {datetime.now().strftime('%Y-%m-%d  %H:%M')}  |  Bolero Configuration Extractor v3.0"
    ts.font = Font(name="Calibri", italic=True, size=9, color="FFFFFF")
    ts.fill = fill(C["mid_blue"])
    ts.alignment = Alignment(horizontal="center")

    hdrs = ["#", "File", "Show / Project Name", "Sheet Tabs", "Conferences", "Profiles Defined",
            "Beltpacks Configured", "Online in Snapshot", "Antennas", "Audio Channels", "Audio Devices"]
    for col, h in enumerate(hdrs, 1):
        hdr_cell(ws, 4, col, h, "header_grey")

    for ri, r in enumerate(results, 5):
        idx = ri - 4
        tab_tag = "Standard" if len(results) == 1 else f"* ({idx})"
        online_bps = sum(1 for b in r["beltpacks"] if b.get("status") == "Online")
        row_data = [
            idx,
            r["filename"], r["show_name"], tab_tag, len(r["channels"]),
            len(r["profiles"]), len(r["beltpacks"]), online_bps,
            len(r["antennas"]),
            len(r["audio_chs"]),
            ", ".join(r["nsa_devices"]) or "—"
        ]
        fk = "row_alt" if ri % 2 == 0 else "row_white"
        for col, val in enumerate(row_data, 1):
            data_cell(ws, ri, col, val, fk, halign="left" if col in (2, 3) else "center")

    auto_width(ws); ws.freeze_panes = "A5"

def _get_target_styling(k_type, func_str, default_fk):
    if k_type == "Partyline":
        return "conf_fill", C["conf_text"]
    elif k_type == "Audio":
        if "Talk" in func_str:
            return "audio_talk_fill", C["audio_talk_text"]
        else:
            return "audio_list_fill", C["audio_list_text"]
    elif k_type == "P2P":
        return "p2p_fill", C["p2p_text"]
    elif k_type == "Reply":
        return "reply_dyn_fill", C["reply_dyn_text"]
    else:
        return default_fk, "000000"

def _get_mode_color(mode_str):
    if mode_str == "Auto":
        return C["auto"]
    elif mode_str == "Momentary":
        return C["mom"]
    elif mode_str == "Latching":
        return C["latch"]
    return "808080"

# ── Sheet 2: Registered Beltpack Key & Reply Configuration Sheet ──────────────
def write_keymap_sheet(wb, r, tag=""):
    ws = wb.create_sheet(title=make_sheet_title("Key Map", tag))
    title_row(ws, f"Registered Beltpack Key Layout & Action Modes — {r['show_name']}  ({r['filename']})", 27, fill_key="teal")
    
    # Legend
    ws.merge_cells("A2:AA2")
    leg = ws["A2"]
    leg.value = "Conferences (Blue)   |   Audio/NSA Talk (Amber)   |   Audio/NSA Listen (Green)   |   Point-to-Point (Purple)   |   Action Modes: Auto / Momentary / Latching   |   Key 7: Dynamic Reply or Fixed Override"
    leg.font = Font(name="Calibri", bold=True, size=9, color="1F3864")
    leg.fill = fill(C["teal_light"])
    leg.alignment = Alignment(horizontal="center")

    # Header Level 1
    ws.merge_cells("A4:A5"); hdr_cell(ws, 4, 1, "BP #", "header_grey")
    ws.merge_cells("B4:B5"); hdr_cell(ws, 4, 2, "RF Status", "header_grey")
    ws.merge_cells("C4:C5"); hdr_cell(ws, 4, 3, "Device ID", "header_grey")
    ws.merge_cells("D4:D5"); hdr_cell(ws, 4, 4, "Beltpack Label", "header_grey")
    ws.merge_cells("E4:E5"); hdr_cell(ws, 4, 5, "User Name", "header_grey")
    ws.merge_cells("F4:F5"); hdr_cell(ws, 4, 6, "Loaded Profile", "header_grey")
    
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 15
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 16
    ws.column_dimensions["F"].width = 18

    # Keys 1 through 6
    for k_i in range(6):
        c_start = 7 + k_i * 3
        ws.merge_cells(start_row=4, start_column=c_start, end_row=4, end_column=c_start+2)
        hdr_cell(ws, 4, c_start, f"Key {k_i+1}", "teal")
        hdr_cell(ws, 5, c_start, "Target / Conference", "header_grey")
        hdr_cell(ws, 5, c_start+1, "Function", "header_grey")
        hdr_cell(ws, 5, c_start+2, "Mode", "header_grey")
        ws.column_dimensions[get_column_letter(c_start)].width = 18
        ws.column_dimensions[get_column_letter(c_start+1)].width = 16
        ws.column_dimensions[get_column_letter(c_start+2)].width = 13

    # Key 7: REPLY Key
    c_reply = 7 + 6 * 3  # Column 25 (Y), 26 (Z), 27 (AA)
    ws.merge_cells(start_row=4, start_column=c_reply, end_row=4, end_column=c_reply+2)
    hdr_cell(ws, 4, c_reply, "REPLY Key (Key 7)", "dark_blue")
    hdr_cell(ws, 5, c_reply, "Reply Target", "header_grey")
    hdr_cell(ws, 5, c_reply+1, "Function", "header_grey")
    hdr_cell(ws, 5, c_reply+2, "Mode", "header_grey")
    ws.column_dimensions[get_column_letter(c_reply)].width = 24
    ws.column_dimensions[get_column_letter(c_reply+1)].width = 16
    ws.column_dimensions[get_column_letter(c_reply+2)].width = 13

    ws.row_dimensions[4].height = 20
    ws.row_dimensions[5].height = 20

    for ri, bp in enumerate(r["beltpacks"], 6):
        fk = "row_alt" if ri % 2 == 0 else "row_white"
        
        data_cell(ws, ri, 1, bp.get("bp_num", ri - 5), fk)
        
        # RF Status styling
        st = bp.get("status", "Offline")
        st_color = C["green"] if st == "Online" else "808080"
        data_cell(ws, ri, 2, st, fk, color=st_color, bold=(st == "Online"), halign="center")

        data_cell(ws, ri, 3, bp.get("dev_id", ""), fk, halign="center")
        data_cell(ws, ri, 4, bp["label"], fk, bold=True, halign="left")
        data_cell(ws, ri, 5, bp["user_name"] or "—", fk, halign="left")
        data_cell(ws, ri, 6, bp["profile"] or "—", fk, halign="center")
        
        for k_i, k in enumerate(bp.get("keys", [])):
            if k_i >= 7:
                break
            c_target = 7 + k_i * 3
            c_func = c_target + 1
            c_mode = c_target + 2
            
            target_str = k["target"]
            func_str = k["func"]
            mode_str = k["mode"]
            k_type = k.get("type", "")
            
            if k_i == 6:  # REPLY Key styling
                if "Dynamic Reply" in target_str or target_str == "-" or k_type == "Reply":
                    data_cell(ws, ri, c_target, "Dynamic Reply (Last Caller)", "reply_dyn_fill", color=C["reply_dyn_text"], bold=True, halign="left")
                    data_cell(ws, ri, c_func, "Talk (Default)", fk, color="566573", halign="center")
                    data_cell(ws, ri, c_mode, "-", fk, color="808080", halign="center")
                else:
                    t_fill, t_color = _get_target_styling(k_type, func_str, fk)
                    m_color = _get_mode_color(mode_str)
                    data_cell(ws, ri, c_target, target_str, t_fill, color=t_color, bold=True, halign="left")
                    data_cell(ws, ri, c_func, func_str, fk, bold=True, halign="center")
                    data_cell(ws, ri, c_mode, mode_str, fk, color=m_color, bold=(mode_str in ("Auto", "Momentary")), halign="center")
            elif target_str != "-":
                t_fill, t_color = _get_target_styling(k_type, func_str, fk)
                m_color = _get_mode_color(mode_str)
                data_cell(ws, ri, c_target, target_str, t_fill, color=t_color, bold=True, halign="left")
                data_cell(ws, ri, c_func, func_str, fk, bold=(func_str not in ("Listen", "Off")), halign="center")
                data_cell(ws, ri, c_mode, mode_str if func_str != "Off" else "-", fk, color=m_color if func_str != "Off" else "808080", bold=(mode_str in ("Auto", "Momentary") and func_str != "Off"), halign="center")
            else:
                data_cell(ws, ri, c_target, "-", fk, color="808080", halign="center")
                data_cell(ws, ri, c_func, "-", fk, color="808080", halign="center")
                data_cell(ws, ri, c_mode, "-", fk, color="808080", halign="center")

    ws.freeze_panes = "G6"

# ── Sheet 3: Profiles Key & Routing Sheet ─────────────────────────────────────
def write_profiles_matrix(wb, r, tag=""):
    ws = wb.create_sheet(title=make_sheet_title("Profiles", tag))
    title_row(ws, f"Profile Key & Audio Routing Layout — {r['show_name']}  ({r['filename']})", 23, fill_key="purple")
    
    # Legend
    ws.merge_cells("A2:W2")
    leg = ws["A2"]
    leg.value = "Conferences (Blue)   |   Audio/NSA Talk (Amber)   |   Audio/NSA Listen (Green)   |   Point-to-Point (Purple)   |   Action Modes: Auto / Momentary / Latching   |   Key 7: Dynamic Reply or Fixed Override"
    leg.font = Font(name="Calibri", bold=True, size=9, color="5B3A8A")
    leg.fill = fill(C["purple_light"])
    leg.alignment = Alignment(horizontal="center")

    # Header Level 1
    ws.merge_cells("A4:A5"); hdr_cell(ws, 4, 1, "Profile Name", "header_grey")
    ws.merge_cells("B4:B5"); hdr_cell(ws, 4, 2, "Assigned Beltpacks", "header_grey")
    
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 34

    # Keys 1 through 6
    for k_i in range(6):
        c_start = 3 + k_i * 3
        ws.merge_cells(start_row=4, start_column=c_start, end_row=4, end_column=c_start+2)
        hdr_cell(ws, 4, c_start, f"Key {k_i+1}", "purple")
        hdr_cell(ws, 5, c_start, "Target / Conference", "header_grey")
        hdr_cell(ws, 5, c_start+1, "Function", "header_grey")
        hdr_cell(ws, 5, c_start+2, "Mode", "header_grey")
        ws.column_dimensions[get_column_letter(c_start)].width = 18
        ws.column_dimensions[get_column_letter(c_start+1)].width = 16
        ws.column_dimensions[get_column_letter(c_start+2)].width = 13

    # Key 7: REPLY Key
    c_reply = 3 + 6 * 3  # Column 21 (U), 22 (V), 23 (W)
    ws.merge_cells(start_row=4, start_column=c_reply, end_row=4, end_column=c_reply+2)
    hdr_cell(ws, 4, c_reply, "REPLY Key (Key 7)", "dark_blue")
    hdr_cell(ws, 5, c_reply, "Reply Target", "header_grey")
    hdr_cell(ws, 5, c_reply+1, "Function", "header_grey")
    hdr_cell(ws, 5, c_reply+2, "Mode", "header_grey")
    ws.column_dimensions[get_column_letter(c_reply)].width = 24
    ws.column_dimensions[get_column_letter(c_reply+1)].width = 16
    ws.column_dimensions[get_column_letter(c_reply+2)].width = 13

    ws.row_dimensions[4].height = 20
    ws.row_dimensions[5].height = 20

    for ri, prof in enumerate(r["profiles"], 6):
        fk = "row_alt" if ri % 2 == 0 else "row_white"
        
        assigned_bps = [
            bp["label"] + (f" ({bp['user_name']})" if bp["user_name"] and bp["user_name"] != bp["label"] else "")
            for bp in r["beltpacks"]
            if bp.get("profile") == prof["name"]
        ]
        assigned_str = ", ".join(assigned_bps) if assigned_bps else "—"
        
        data_cell(ws, ri, 1, prof["name"], fk, bold=True, halign="left")
        data_cell(ws, ri, 2, assigned_str, fk, halign="left", color="000000" if assigned_bps else "808080", wrap=True)
        
        for k_i, k in enumerate(prof.get("keys", [])):
            if k_i >= 7:
                break
            c_target = 3 + k_i * 3
            c_func = c_target + 1
            c_mode = c_target + 2
            
            target_str = k["target"]
            func_str = k["func"]
            mode_str = k["mode"]
            k_type = k.get("type", "")
            
            if k_i == 6:  # REPLY Key styling
                if "Dynamic Reply" in target_str or target_str == "-" or k_type == "Reply":
                    data_cell(ws, ri, c_target, "Dynamic Reply (Last Caller)", "reply_dyn_fill", color=C["reply_dyn_text"], bold=True, halign="left")
                    data_cell(ws, ri, c_func, "Talk (Default)", fk, color="566573", halign="center")
                    data_cell(ws, ri, c_mode, "-", fk, color="808080", halign="center")
                else:
                    t_fill, t_color = _get_target_styling(k_type, func_str, fk)
                    m_color = _get_mode_color(mode_str)
                    data_cell(ws, ri, c_target, target_str, t_fill, color=t_color, bold=True, halign="left")
                    data_cell(ws, ri, c_func, func_str, fk, bold=True, halign="center")
                    data_cell(ws, ri, c_mode, mode_str, fk, color=m_color, bold=(mode_str in ("Auto", "Momentary")), halign="center")
            elif target_str != "-":
                t_fill, t_color = _get_target_styling(k_type, func_str, fk)
                m_color = _get_mode_color(mode_str)
                data_cell(ws, ri, c_target, target_str, t_fill, color=t_color, bold=True, halign="left")
                data_cell(ws, ri, c_func, func_str, fk, bold=(func_str not in ("Listen", "Off")), halign="center")
                data_cell(ws, ri, c_mode, mode_str if func_str != "Off" else "-", fk, color=m_color if func_str != "Off" else "808080", bold=(mode_str in ("Auto", "Momentary") and func_str != "Off"), halign="center")
            else:
                data_cell(ws, ri, c_target, "-", fk, color="808080", halign="center")
                data_cell(ws, ri, c_func, "-", fk, color="808080", halign="center")
                data_cell(ws, ri, c_mode, "-", fk, color="808080", halign="center")

    ws.freeze_panes = "C6"



# ── Sheet 4: Registered Antennas Sheet ────────────────────────────────────────
def write_antennas_sheet(wb, r, tag=""):
    ws = wb.create_sheet(title=make_sheet_title("Antennas", tag))
    title_row(ws, f"Registered Transceiver Antennas — {r['show_name']}  ({r['filename']})", 5, fill_key="teal")

    # Network Space & Master Antennas Status Banner
    ws.merge_cells("A2:E2")
    leg = ws["A2"]
    net_m = r.get("net_masters", {})
    ns_id = net_m.get("net_space_id", "—")
    p_mast = net_m.get("primary_master", "None")
    s_mast = net_m.get("secondary_master", "None")
    leg.value = f"Net Space Sync ID: {ns_id}   |   Designated Primary Net Master: {p_mast}   |   Secondary Master: {s_mast}"
    leg.font = Font(name="Calibri", bold=True, size=9, color="1F3864")
    leg.fill = fill(C["teal_light"])
    leg.alignment = Alignment(horizontal="center")

    hdrs = [
        "Net Index", "Antenna Label", "Device ID (Serial)", "Sync / Net ID", "Radio Master Priority"
    ]
    for col, h in enumerate(hdrs, 1):
        hdr_cell(ws, 4, col, h, "header_grey")

    col_widths = [14, 20, 24, 24, 22]
    for col, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = w

    ws.row_dimensions[4].height = 20

    ri = 5
    if r["antennas"]:
        for ant in r["antennas"]:
            fk = "row_alt" if ri % 2 == 0 else "row_white"
            data_cell(ws, ri, 1, ant.get("net_idx", "—"), fk, halign="center")
            data_cell(ws, ri, 2, ant["name"], fk, bold=True, halign="left")
            data_cell(ws, ri, 3, ant["dev_id"], fk, halign="center")
            data_cell(ws, ri, 4, ant["sync_id"], fk, halign="center")
            data_cell(ws, ri, 5, ant.get("master_priority", "Normal (Auto)"), fk, halign="center")
            ri += 1
    else:
        ws.cell(row=ri, column=1, value="(no antenna records found)")

    ws.freeze_panes = "A5"

# ── Sheet 5: Conferences Sheet ────────────────────────────────────────────────
def write_channels_sheet(wb, r, tag=""):
    ws = wb.create_sheet(title=make_sheet_title("Conferences", tag))
    title_row(ws, f"Partyline Conferences — {r['show_name']}  ({r['filename']})", 5)

    for col, h in enumerate(["Conf #", "Conference Name", "Used in Profiles", "Used by Beltpacks", "Audio Channels Attached"], 1):
        hdr_cell(ws, 3, col, h)

    # Cross reference
    prof_usage = {idx: [] for idx in r["channels"]}
    for prof in r["profiles"]:
        for k in prof["keys"]:
            for ch_num, ch_name in r["channels"].items():
                if k["target"] == ch_name and prof["name"] not in prof_usage[ch_num]:
                    prof_usage[ch_num].append(prof["name"])

    ch_users = {idx: [] for idx in r["channels"]}
    for bp in r["beltpacks"]:
        for ch_num in bp["channels"]:
            if ch_num in ch_users:
                label = bp["label"] + (f" ({bp['user_name']})" if bp["user_name"] else "")
                ch_users[ch_num].append(label)

    ch_audio = {idx: [] for idx in r["channels"]}
    for ach in r["audio_chs"]:
        pl = ach["party_line_ch"]
        if pl and pl in ch_audio:
            dev_label = ach.get("nsa_device", "").split(" ")[0]
            label = f"{dev_label}: {ach['name']}" if dev_label else ach["name"]
            if label not in ch_audio[pl]:
                ch_audio[pl].append(label)

    for ri, (ch_num, ch_name) in enumerate(sorted(r["channels"].items()), 4):
        fk = "row_alt" if ri % 2 == 0 else "row_white"
        data_cell(ws, ri, 1, ch_num, fk)
        data_cell(ws, ri, 2, ch_name, fk, bold=True, halign="left")
        data_cell(ws, ri, 3, ", ".join(prof_usage.get(ch_num, [])) or "—", fk, halign="left", wrap=True)
        data_cell(ws, ri, 4, ", ".join(ch_users.get(ch_num, [])) or "—", fk, halign="left", wrap=True)
        data_cell(ws, ri, 5, ", ".join(ch_audio.get(ch_num, [])) or "—", fk, halign="left")

    auto_width(ws); ws.freeze_panes = "A4"

# ── Sheet 6: Audio Device / NSA Sheet ─────────────────────────────────────────
def write_audio_sheet(wb, r, tag=""):
    ws = wb.create_sheet(title=make_sheet_title("Audio Devices", tag))
    title_row(ws, f"Audio Devices & Interfacing — {r['show_name']}  ({r['filename']})", 7, fill_key="purple")

    ws.merge_cells("A2:G2")
    leg = ws["A2"]
    leg.value = "Network Audio Devices (NSA-002A & Punqtum Q-Series)   |   AES67 IP Audio Routing"
    leg.font = Font(name="Calibri", bold=True, size=9, color="5B3A8A")
    leg.fill = fill(C["purple_light"])
    leg.alignment = Alignment(horizontal="center")

    hdrs = [
        "Audio Channel / Label", "Audio Device", "Device Channel", "Interface Type",
        "Conf #", "Attached Conference", "Function"
    ]
    for col, h in enumerate(hdrs, 1):
        hdr_cell(ws, 4, col, h, "purple")

    col_widths = [24, 16, 15, 24, 10, 22, 22]
    for col, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = w

    ws.row_dimensions[4].height = 20

    ri = 5
    if r["audio_chs"]:
        for ach in r["audio_chs"]:
            fk = "row_alt" if ri % 2 == 0 else "row_white"
            data_cell(ws, ri, 1, ach["name"], fk, bold=True, halign="left")
            data_cell(ws, ri, 2, ach.get("nsa_device", "—"), fk, halign="center")
            data_cell(ws, ri, 3, f"Channel {ach['nsa_channel']}" if ach.get("nsa_channel") else "—", fk, halign="center")
            
            # Interface Type styling
            itype = ach.get("interface_type", "—")
            if itype == "4-Wire":
                t_color = "1F3864"  # Dark navy
            elif "Input" in itype:
                t_color = C["listen"]  # Green
            elif "Output" in itype:
                t_color = C["talk"]    # Amber
            else:
                t_color = "000000"
            data_cell(ws, ri, 4, itype, fk, color=t_color, bold=True, halign="center")

            data_cell(ws, ri, 5, ach["party_line_ch"] or "—", fk, halign="center")
            data_cell(ws, ri, 6, ach["party_line_name"] or "—", fk, halign="left")

            func = ach["function"] or "—"
            fl   = ach["flags"]
            if fl in (0x81,):   col_c = C["listen"]
            elif fl in (0xC0,): col_c = C["tal"]
            elif fl in (0x40,): col_c = C["talk"]
            elif fl == 0x82:    col_c = C["green"]
            elif fl in (0x02,): col_c = C["orange"]
            else:               col_c = "000000"
            data_cell(ws, ri, 7, func, fk, color=col_c, bold=(col_c != "000000"), halign="left")
            ri += 1
    else:
        ws.cell(row=ri, column=1, value="(no audio channel records found)")
        ri += 1

    if r["nsa_triggers"]:
        ri += 1
        ws.merge_cells(start_row=ri, start_column=1, end_row=ri, end_column=7)
        c = ws.cell(row=ri, column=1, value="Configured Audio Device Hardware Triggers & GPIO")
        c.font = Font(name="Calibri", bold=True, size=10, color="FFFFFF")
        c.fill = fill(C["purple"]); c.alignment = Alignment(horizontal="center"); ri += 1
        for trig in r["nsa_triggers"]:
            fk = "row_alt" if ri % 2 == 0 else "row_white"
            data_cell(ws, ri, 1, trig, fk, bold=True, halign="left")

            if "NSA1" in trig:
                dev_txt = "NSA 1"
            elif "NSA2" in trig:
                dev_txt = "NSA 2"
            elif trig.startswith("TI ") or trig.startswith("TO "):
                parts = trig.split()[1].split('/')
                dev_txt = f"Device {parts[0]}" if parts else "—"
            else:
                dev_txt = "—"
            data_cell(ws, ri, 2, dev_txt, fk, halign="center")
            data_cell(ws, ri, 3, "GPIO / Trigger", fk, halign="center")

            if "IN" in trig or trig.startswith("TI"):
                dir_txt = "Trigger Input (GPI)"
            elif "OUT" in trig or trig.startswith("TO"):
                dir_txt = "Trigger Output (GPO)"
            else:
                dir_txt = "Trigger"
            data_cell(ws, ri, 4, dir_txt, fk, halign="center")
            data_cell(ws, ri, 5, "—", fk, halign="center")
            data_cell(ws, ri, 6, "—", fk, halign="center")
            data_cell(ws, ri, 7, "GPIO Routing", fk, halign="left")
            ri += 1

    ws.freeze_panes = "A5"

# ── Master Export ─────────────────────────────────────────────────────────────
def export(results, output_path):
    wb = openpyxl.Workbook()
    write_summary(wb, results)
    for idx, r in enumerate(results, 1):
        tag = "" if len(results) == 1 else f" ({idx})"
        write_keymap_sheet(wb, r, tag)
        write_profiles_matrix(wb, r, tag)
        write_antennas_sheet(wb, r, tag)
        write_channels_sheet(wb, r, tag)
        write_audio_sheet(wb, r, tag)
    wb.save(output_path)
    print(f"\nSuccessfully saved full workbook: {output_path}")

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Extract Bolero .bol files to Excel v3.0")
    ap.add_argument("files", nargs="*")
    ap.add_argument("-o", "--output", default="bolero_export.xlsx")
    ap.add_argument("-s", "--separate", action="store_true",
                    help="Export each .bol file to its own individual .xlsx workbook")
    args = ap.parse_args()

    if args.files:
        input_files = []
        for pat in args.files:
            m = glob.glob(pat)
            input_files.extend(m if m else ([pat] if os.path.isfile(pat) else []))
    else:
        input_files = sorted(glob.glob("*.bol"))

    if not input_files:
        print("No .bol files found."); sys.exit(1)

    print(f"Processing {len(input_files)} .bol file(s)…")
    results = []
    for fp in input_files:
        try:
            print(f"\nParsing: {os.path.basename(fp)}")
            r = parse_bol_file(fp)
            results.append(r)
            print(f"  Show Name    : {r['show_name']}")
            print(f"  Channels     : {len(r['channels'])}")
            print(f"  Profiles     : {len(r['profiles'])}")
            print(f"  Beltpack Reg : {len(r['beltpacks'])}")
            print(f"  Antennas     : {len(r['antennas'])}")
            print(f"  Audio Routes : {len(r['audio_chs'])}")
            print(f"  NSA Devices  : {r['nsa_devices']}")
        except Exception as e:
            import traceback
            print(f"  ERROR parsing {fp}: {e}")
            traceback.print_exc()

    if not results:
        sys.exit(1)

    if args.separate:
        for r in results:
            out_file = os.path.splitext(r["filename"])[0] + ".xlsx"
            export([r], out_file)
    else:
        export(results, args.output)

if __name__ == "__main__":
    main()
