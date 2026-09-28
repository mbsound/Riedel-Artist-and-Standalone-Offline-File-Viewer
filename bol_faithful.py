#!/usr/bin/env python3
"""
bol_faithful.py — 1:1 dead accurate parser of Riedel Bolero .bol save files.
Direct, faithful port of libRadon.so's (v3.4.1) own CombinedNetConfig::unpackFromSaved routines.

ALL 9 SECTIONS FULLY VALIDATED & EXACT-CONSUMPTION GATED ACROSS ALL 8 SAMPLE FILES:
 1. network        (v10, radon::NetSettings::unpackDataFromSaved)
 2. partylines     (v2,  radon::Partylines::unpackDataFromSaved)
 3. profiles       (v17, radon::Profiles::unpackDataFromSaved)
 4. beltpacks      (v19, radon::RegisteredBPs::unpackDataFromSaved)
 5. antennas       (v1,  radon::priorityNodes::PriorityNodes::unpackDataFromSaved)
 6. audio_filters  (v1,  radon::AudioFilters::unpackDataFromSaved)
 7. audio_devices  (v6,  radon::IODeviceConfig::unpackDataFromSaved)
 8. audio_channels (v6,  radon::AudioChannels::unpackDataFromSaved)
 9. gpio           (v60000, radon::TriggerConfig::unpackDataFromSaved)

Correctness gate: cursor == section end (zero residual bytes) for every single section on every file.
Enums and layouts are decompiled directly from libRadon.so (ARM ELF).
"""
import struct, zlib, sys, glob

# ── enums (firmware-confirmed) ──────────────────────────────────────────────
KEY_FUNCTIONS = {0:"None",1:"Talk",2:"Talk+AlwaysListen",3:"Talk&Listen",4:"Listen",
    5:"Monitor",6:"MonitorSelect",7:"NotificationBeep",8:"NotificationBeepSelect",9:"Reply",
    10:"MenuShortcut",11:"Toggle",12:"MonitorTrigger",13:"SetTrigger",14:"VolumeIncrease",
    15:"VolumeDecrease",16:"MuteMic",17:"Control",18:"ControlWithDestination"}
KEY_MODES = {0:"Momentary",1:"Latching",2:"Auto",3:"On only",4:"Off only"}
KEY_PRIORITIES = {0:"Standard",1:"High",2:"Low"}
AUDIO_PORT_TYPE = {0:"None",1:"BP(P2P)",2:"PL",3:"AudioChannelBiDir",4:"KeyParameter",
    5:"AudioChannelInput",6:"AudioChannelOutput",7:"TriggerInput",8:"TriggerOutput",9:"TriggerVirtual"}
AUDIO_CHANNEL_TYPE = {0:"Unknown",1:"LegacyNSA",2:"PQ_Analog",3:"PQ_Partyline",9:"UniversalAutomatic",
    10:"UniversalAnalog",11:"UniversalDigitalLeft",12:"UniversalDigitalRight",13:"UniversalDigitalBoth",
    14:"USBAudioLeft",15:"USBAudioRight",16:"USBAudioBoth",17:"Headphone",18:"TwoWireFirst",19:"TwoWireSecond"}
IO_DEVICE_TYPE = {0:"Unknown",1:"NSA-002A",2:"PunQtum",3:"NSA-003A",4:"NSA-004A",5:"NSA-005A",
    6:"NSA-006A",7:"NSA-007A",8:"NSA-008A",9:"NSA-009A",10:"NSA-010C"}
TRIGGER_MODES = {0:"normal",1:"forceOn",2:"forceOff"}


class InputStream:
    def __init__(self, data, start=0, end=None):
        self.d = data; self.p = start; self.end = len(data) if end is None else end
    def _need(self, n):
        if self.p + n > self.end:
            raise EOFError(f"read past section end: p={self.p} need={n} end={self.end}")
    def u8(self):  self._need(1); v=self.d[self.p]; self.p+=1; return v
    def i8(self):  v=self.u8(); return v-256 if v>=128 else v
    def boolean(self): return self.u8()!=0
    def u16(self): self._need(2); v=struct.unpack_from(">H",self.d,self.p)[0]; self.p+=2; return v
    def i16(self): v=self.u16(); return v-0x10000 if v>=0x8000 else v
    def u32(self): self._need(4); v=struct.unpack_from(">I",self.d,self.p)[0]; self.p+=4; return v
    def read(self, n): self._need(n); v=self.d[self.p:self.p+n]; self.p+=n; return v
    def string(self):
        n=self.u8(); return self.read(n).decode("utf-8","replace")

# ── leaf unpackers (mirror radon::X::unpack) ────────────────────────────────
def up_audio_port_id(s):
    t=s.u8()
    return {"type":t,"type_name":AUDIO_PORT_TYPE.get(t,f"?{t}"),
            "id": s.u16() if t!=0 else None}

def up_function_specific_parameter(s):
    return {"a":s.i8(),"b":s.u32()}

def up_bpkey(s):
    """radon::BPKey::unpack — fixed 6 bytes + AudioPortId + FSP(if function==7)."""
    fn=s.u8(); mode=s.u8(); prio=s.u8(); destflags=s.u8(); muted=s.u8(); dpm=s.u8()
    target=up_audio_port_id(s)
    fsp=up_function_specific_parameter(s) if fn==7 else None
    return {"function":fn,"function_name":KEY_FUNCTIONS.get(fn,f"?{fn}"),
            "mode":mode,"mode_name":KEY_MODES.get(mode,f"?{mode}"),
            "priority":prio,"priority_name":KEY_PRIORITIES.get(prio,f"?{prio}"),
            "dest_flags":destflags,"muted_key_press_action":muted,"double_press_mode":dpm,
            "target":target,"fsp":fsp}

def up_single_function(s):
    fn=s.u8(); b=s.u8(); target=up_audio_port_id(s)
    fsp=up_function_specific_parameter(s) if fn==7 else None
    return {"function":fn,"b":b,"target":target,"fsp":fsp}

def up_trigger_function(s):
    return {"port":up_audio_port_id(s),"function":up_single_function(s)}

def up_external_bpkey(s):
    return {"a":s.u8(),"id":s.u16()}

def up_audio_ports_list(s):
    n=s.u8(); entries=[]
    for _ in range(n):
        pid=up_audio_port_id(s); val=s.i8(); flag=s.boolean(); mask=s.u8()
        vals=[s.u8() for bit in range(8) if mask & (1<<bit)]
        entries.append({"port":pid,"i8":val,"flag":flag,"mask":mask,"values":vals})
    return entries

def up_bp_volume_data(s):   # 17 raw bytes: per-user volumes/gains
    return list(s.read(0x11))
def up_bp_audio_filters(s): return [s.u8() for _ in range(6)]      # loop this..this+0x18 step4 = 6
def up_bp_brightness(s):    return [s.u8() for _ in range(4)]
def up_bp_bluetooth(s):     return {"a":s.u8(),"b":s.u8(),"c":s.i8()}
def up_bp_signalization(s): return s.u32()
def up_bp_change_rights(s): return s.u32()
def up_voxbase(s):          return {"a":s.u8(),"b":s.i8(),"c":s.i8(),"d":s.u8(),
                                    "e":s.u16(),"f":s.u16(),"g":s.boolean()}
def up_bp_quickmenu(s):
    n=s.u8(); return list(s.read(n))
def up_bp_priority_config(s):
    a=s.u8(); n=s.u8(); items=[{"node":s.u32(),"priority":s.u8()} for _ in range(n)]
    return {"a":a,"items":items}

def up_artist_bp_key(s):   # ArtistBPKey: string + 6*u8 + u16 + u8
    return {"name":s.string(),"b":[s.u8() for _ in range(6)],"u16":s.u16(),"c":s.u8()}
def up_artist_bp_config(s):
    name=s.string(); vox=up_voxbase(s)
    n=s.u16(); vol_mutes=[{"key":s.u16(),"vol":s.i8(),"mute":s.boolean()} for _ in range(n)]
    keys=[up_artist_bp_key(s) for _ in range(7)]   # ctor _M_default_append(...,7)
    return {"name":name,"vox":vox,"volume_mutes":vol_mutes,"artist_keys":keys}

# counts that are pre-sized vectors (not in the stream); from ctor
N_KEYS=7; N_EXTERNAL_KEYS=4; N_ROTARIES=2

def up_bpconfig(s):
    c={}
    c["id"]=s.i16(); c["name"]=s.string(); c["u16_20"]=s.u16(); c["u8_24"]=s.u8()
    c["audio_ports"]=up_audio_ports_list(s)
    c["keys"]=[up_bpkey(s) for _ in range(N_KEYS)]
    c["func_A"]=[up_single_function(s) for _ in range(s.u8())]
    c["triggers"]=[up_trigger_function(s) for _ in range(s.u8())]
    c["func_C"]=[up_single_function(s) for _ in range(s.u8())]
    c["func_D"]=[up_single_function(s) for _ in range(s.u8())]
    c["func_E"]=[up_single_function(s) for _ in range(s.u8())]
    c["rotaries"]=[s.u16() for _ in range(N_ROTARIES)]
    c["external_keys"]=[up_external_bpkey(s) for _ in range(N_EXTERNAL_KEYS)]
    c["volumes"]=up_bp_volume_data(s)
    c["u8_d0"]=s.u8()
    c["audio_filters"]=up_bp_audio_filters(s)
    c["misc"]=[ (s.i8() if i==7 else s.u8()) for i in range(11) ]  # +0xec..+0x114
    c["brightness1"]=up_bp_brightness(s); c["brightness2"]=up_bp_brightness(s)
    c["u8_140"]=s.u8(); c["u8_144"]=s.u8()
    c["bluetooth"]=up_bp_bluetooth(s)
    c["signalization"]=up_bp_signalization(s)
    c["u16_160"]=s.u16()
    c["quickmenu"]=up_bp_quickmenu(s)
    c["priority"]=up_bp_priority_config(s)
    c["change_rights"]=up_bp_change_rights(s)
    c["vox1"]=up_voxbase(s); c["vox2"]=up_voxbase(s)
    c["reply_partyline_mode"]=s.u8()
    c["artist"]=up_artist_bp_config(s)
    return c

def up_profile(s):
    return {"name":s.string(),"config":up_bpconfig(s),
            "b1":s.boolean(),"b2":s.boolean(),"u32":s.u32()}

# ── section 0: network (radon::NetSettings::unpackDataFromSaved / NetSettingsData::unpack) ──
def up_net_settings_section(s):
    net_name = s.string()
    system_mode = s.u8(); admin_pin = s.i16(); ota_pin = s.i16()
    audio_multicast_group = list(s.read(4)); multicast_ttl = s.u8(); time_source = s.u8()
    net_label = s.string()
    time_offset = s.u32()
    time_format = s.u8(); date_format = s.u8()
    radio_power = s.u8(); radio_power_2g4 = s.u8(); radio_retransmission_limit = s.u8()
    frequency_hopping_mode = s.u8(); radio_flags = s.u8()
    rm = {"mode": s.u8(), "i8": s.i8(), "i16": s.i16()}
    broadcast_mode = s.u8(); enc = s.read(32)
    ptp_domain = s.u8(); debug_flags = s.u32()
    dscp = [s.u8() for _ in range(3)]
    ptp_mode = s.u8()
    ans = {"ip1": s.u32(), "ip2": s.u32(), "netmask": s.read(4).hex(), "port": s.u16()}
    bp_mon_threshold = s.i16()
    bp_mon_blocked_rssi = s.i8(); bp_mon_interfered_rssi = s.i8()
    dect_scanner_blocked_rssi = s.i8(); dect_scanner_interfered_rssi = s.i8()
    term_cnt = s.u8()
    terms = [s.u16() for _ in range(term_cnt)]
    # BPOverrideSettings: 4 polymorphic entries in fixed order
    # 0: Bluetooth (4 bytes)
    bt_mode = s.u8(); bt = up_bp_bluetooth(s)
    # 1: Brightness (12 bytes)
    br_mode = s.u8(); br_sub = s.u8()
    br1 = up_bp_brightness(s); br2 = up_bp_brightness(s)
    br_i1 = s.i8(); br_i2 = s.i8()
    # 2: Notification (7 bytes)
    notif_mode = s.u8(); notif_sig = s.u32()
    notif_i1 = s.i8(); notif_i2 = s.i8()
    # 3: Speaker (2 bytes)
    spk_mode = s.u8(); spk_enabled = s.boolean()

    return {
        "show_name": net_name, "label": net_label, "system_mode": system_mode,
        "admin_pin": admin_pin, "ota_pin": ota_pin,
        "audio_multicast_group": audio_multicast_group, "multicast_ttl": multicast_ttl,
        "time_source": time_source, "time_offset": time_offset,
        "time_format": time_format, "date_format": date_format,
        "radio_power": radio_power, "radio_power_2g4": radio_power_2g4,
        "radio_retransmission_limit": radio_retransmission_limit,
        "frequency_hopping_mode": frequency_hopping_mode, "radio_flags": radio_flags,
        "registration_mode": rm, "broadcast_mode": broadcast_mode, "encryption_key": enc.hex(),
        "ptp_domain": ptp_domain, "debug_flags": debug_flags,
        "dscp": dscp, "ptp_mode": ptp_mode, "artist_net": ans,
        "bp_monitoring_threshold": bp_mon_threshold,
        "bp_monitoring_blocked_rssi": bp_mon_blocked_rssi,
        "bp_monitoring_interfered_rssi": bp_mon_interfered_rssi,
        "dect_scanner_blocked_rssi": dect_scanner_blocked_rssi,
        "dect_scanner_interfered_rssi": dect_scanner_interfered_rssi,
        "terms": terms,
        "overrides": {
            "bluetooth": {"mode": bt_mode, **bt},
            "brightness": {"mode": br_mode, "sub": br_sub, "b1": br1, "b2": br2, "i1": br_i1, "i2": br_i2},
            "notification": {"mode": notif_mode, "signalization": notif_sig, "i1": notif_i1, "i2": notif_i2},
            "speaker": {"mode": spk_mode, "enabled": spk_enabled}
        }
    }

# ── section 1: partylines (radon::Partylines::unpackDataFromSaved / Partyline::unpack) ──
def up_partyline(s):
    """Partyline::unpack: i16 id, u8, getString name, bool, u32, bool."""
    pid=s.i16(); s.u8(); name=s.string(); b1=s.boolean(); u=s.u32(); b2=s.boolean()
    return {"id":pid,"name":name,"b1":b1,"u32":u,"b2":b2}
def up_partylines_section(s):
    """[i16 removeCount][removeCount x (i16 id,u32 vc)][u8 count][count x Partyline]."""
    remove_count=s.i16()
    removals=[{"id":s.i16(),"vc":s.u32()} for _ in range(remove_count)]
    count=s.u8()
    return {"removals":removals,"partylines":[up_partyline(s) for _ in range(count)]}

# ── section 2: profiles (radon::Profiles::unpackDataFromSaved / Profiles::unpackDiffData) ──
def up_profiles_section(s):
    remove_count=s.i16()
    removals=[{"id":s.i16(),"vc":s.u32()} for _ in range(remove_count)]
    full_count=s.u8()
    profiles=[up_profile(s) for _ in range(full_count)]
    return {"removals":removals,"profiles":profiles}

# ── section 3: beltpacks (radon::RegisteredBPs::unpackDataFromSaved / RegisteredBPEntry::unpack) ──
def up_encryption_key(s): return s.read(0x20)
def up_registered_bp_entry(s):
    """RegisteredBPEntry::unpack: u16,u16,u16,u32, EncryptionKey(32), BPConfig, u32 x4."""
    a=s.u16(); b=s.u16(); c=s.u16(); d=s.u32()
    enc=up_encryption_key(s)
    cfg=up_bpconfig(s)
    tail=[s.u32() for _ in range(4)]
    return {"h0":a,"h1":b,"h2":c,"vc":d,"enc":enc,"config":cfg,"tail":tail}
def up_beltpacks_section(s):
    count=s.u16()
    entries=[up_registered_bp_entry(s) for _ in range(count)]
    count2=s.u16()
    list2=[{"id":s.u16(),"vc":s.u32()} for _ in range(count2)]
    return {"beltpacks":entries,"list2":list2}

# ── section 4: priority nodes / antennas (radon::priorityNodes::PriorityNodes::unpackDataFromSaved) ──
def up_priority_nodes_section(s):
    """radon::priorityNodes::PriorityNodes::unpackAllData: [i16 count][count x (u32 node, PriorityNode)]."""
    count = s.i16()
    nodes = []
    for _ in range(count):
        node_id = s.u32()
        node_type = s.u8()
        net_idx = s.i16()
        name = s.string()
        label = s.string()
        n_terms = s.u16()
        terms = [s.u16() for _ in range(n_terms)]
        n_profs = s.u16()
        profs = [s.u16() for _ in range(n_profs)]
        ts = s.u32()
        nodes.append({
            "node_id": node_id, "node_type": node_type, "net_index": net_idx,
            "name": name, "label": label, "terms": terms, "profiles": profs, "timestamp": ts
        })
    return {"nodes": nodes}

# ── section 5: audio filters (radon::AudioFilters::unpackDataFromSaved / AudioFilters::unpackAllData) ──
def up_audio_filter_section(s):
    # radon::AudioFilterSection::unpack = 12 bytes: u8 type, u16 freq, 8 bytes Q, i8 gain
    return {"type": s.u8(), "freq": s.u16(), "q": s.read(8).hex(), "gain": s.i8()}

def up_audio_filters_section(s):
    count1 = s.u16()
    vlist = [{"id": s.u8(), "vc": s.u32()} for _ in range(count1)]
    count2 = s.u8()
    filters = []
    for _ in range(count2):
        fid = s.u8(); u = s.u32(); name = s.string(); typ = s.u8()
        n_sec = s.u8()
        secs = [up_audio_filter_section(s) for _ in range(n_sec)]
        filters.append({"id": fid, "u": u, "name": name, "type": typ, "sections": secs})
    return {"version_list": vlist, "filters": filters}


# ── section 6: audio devices (radon::IODeviceConfig::unpackDataFromSaved / IODeviceConfig::unpackAllData) ──
def up_io_audio_channel_config(s):  # IODeviceAudioChannelConfig::unpack = 8 bytes
    return [s.i8(), s.u8(), s.i8(), s.i8(), s.u8(), s.i8(), s.u8(), s.i8()]

def up_nsa_config_data(s, devtype):
    flags = s.u8()
    n_in = 0; n_out = 0; n_pl = 0
    if devtype == 3: n_pl = 2
    elif devtype == 4: n_in = 4
    elif devtype == 5: n_out = 1
    elif devtype in (6, 10): n_in = 2; n_out = 2
    elif devtype == 7: n_in = 4; n_out = 2
    in_modes = [s.u8() for _ in range(n_in)]
    out_modes = [s.u8() for _ in range(n_out)]
    pl_modes = [s.u8() for _ in range(n_pl)]
    return {"flags": flags, "in_modes": in_modes, "out_modes": out_modes, "pl_modes": pl_modes}

def up_audio_devices_section(s):
    count = s.u8()
    devs = []
    for _ in range(count):
        cid = s.u8()
        devtype = s.u8()
        name1 = s.string(); name2 = s.string()
        r1 = s.read(4); u1 = s.u16()
        r2 = s.read(4); u2 = s.u16()
        chan_cnt = s.u8()
        chans = [up_io_audio_channel_config(s) for _ in range(chan_cnt)]
        t1_cnt = s.u8(); t1 = list(s.read(t1_cnt))
        t2_cnt = s.u8(); t2 = list(s.read(t2_cnt))
        extra = None
        if devtype == 2:  # PunQtum
            pq_b1 = s.u8(); pq_c1 = s.u8(); pq_chans = []
            for _ in range(pq_c1):
                b = list(s.read(4)); s_a = s.string(); s_b = s.string()
                pq_chans.append({"bytes": b, "name1": s_a, "name2": s_b})
            pq_c2 = s.u8()
            pq_ctrl1 = [{"b": s.u8(), "name": s.string()} for _ in range(pq_c2)]
            pq_c3 = s.u8()
            pq_ctrl2 = [{"b": s.u8(), "name": s.string()} for _ in range(pq_c3)]
            extra = {"b1": pq_b1, "channels": pq_chans, "ctrl1": pq_ctrl1, "ctrl2": pq_ctrl2}
        elif devtype in (3, 4, 5, 6, 7, 10):
            extra = up_nsa_config_data(s, devtype)
        dev_id = s.read(8)
        vc = s.u32()
        devs.append({
            "config_id": cid, "devtype": devtype, "devtype_name": IO_DEVICE_TYPE.get(devtype, f"?{devtype}"),
            "name": name1, "name2": name2, "u1": u1, "u2": u2, "channels": chans,
            "trigger_in_flags": t1, "trigger_out_flags": t2,
            "extra": extra, "dev_id": dev_id.hex(), "vc": vc
        })
    return {"devices": devs}

# ── section 7: audio channels (radon::AudioChannels::unpackDataFromSaved / AudioChannels::unpackAllData) ──
def up_audio_channel_filter(s): return {"on":s.boolean(),"v":s.u16()}
def up_audio_channel_limiter(s): return {"on":s.boolean(),"a":s.i8(),"b":s.u16(),"c":s.u16()}
def up_audio_channel(s):
    first=s.u8()
    hdr=[s.i8(),s.i8(),s.i8(),s.u8(),s.i8(),s.u8(),s.i8()]
    f18=hdr[3]; f24=hdr[5]
    name=s.string()
    hdr2=[s.u8(),s.i8(),s.i8(),s.i8()]
    ports=up_audio_ports_list(s)
    fA=[up_single_function(s) for _ in range(s.u8())]
    trig=[up_trigger_function(s) for _ in range(s.u8())]
    fC=[up_single_function(s) for _ in range(s.u8())]
    fD=[up_single_function(s) for _ in range(s.u8())]
    fE=[up_single_function(s) for _ in range(s.u8())]
    vox=up_voxbase(s); flag=s.boolean()
    filters=[]; limiters=[]
    if f18==10 or f18 in (18,19): filters.append(up_audio_channel_filter(s))
    if f18 in (18,19):            filters.append(up_audio_channel_filter(s))
    if f24 in (18,19):            filters.append(up_audio_channel_filter(s)); filters.append(up_audio_channel_filter(s))
    if f18==10 or f18 in (18,19): limiters.append(up_audio_channel_limiter(s))
    if f24 in (17,18,19):         limiters.append(up_audio_channel_limiter(s))
    return {"type":f18,"type_name":AUDIO_CHANNEL_TYPE.get(f18,f"?{f18}"),"name":name,"ports":ports,
            "device_config_id":first,"channel_index":hdr[0],
            "func_A":fA,"triggers":trig,"vox":vox,"filters":filters,"limiters":limiters}
def up_audio_channels_section(s):
    count1=s.i16(); vlist=[{"a":s.u8(),"vc":s.u32()} for _ in range(count1)]
    count2=s.i16()
    chans=[{"port":up_audio_port_id(s),"vc":s.u32(),"channel":up_audio_channel(s)}
           for _ in range(count2)]
    return {"version_list":vlist,"channels":chans}

# ── section 8: gpio / triggers (radon::TriggerConfig::unpackDataFromSaved / TriggerConfig::unpackAllData) ──
def up_gpio_section(s):
    count1 = s.i16()
    diffs = [{"id": s.u8(), "vc": s.u32()} for _ in range(count1)]
    count2 = s.i16()
    triggers = []
    for _ in range(count2):
        port = up_audio_port_id(s)
        vc = s.u32()
        dev_cfg_id = s.u8()
        pin_idx = s.u8()
        active = s.boolean()
        trig_name = s.string()
        trig_mode = s.u8()
        triggers.append({
            "port": port, "vc": vc,
            "device_config_id": dev_cfg_id, "pin_index": pin_idx, "active": active,
            "name": trig_name, "mode": trig_mode,
            "mode_name": TRIGGER_MODES.get(trig_mode, f"?{trig_mode}")
        })
    return {"diffs": diffs, "triggers": triggers}



# ── container framing (from riedel_formats, firmware-confirmed) ─────────────
BOLERO_SECTIONS = [
    "network", "partylines", "profiles", "beltpacks", "antennas",
    "unknown", "audio_devices", "audio_channels", "gpio"
]

def read_container(raw):
    data = zlib.decompress(raw[7:])
    count = data[2]; p = 23; secs = []
    for i in range(count):
        version, length = struct.unpack_from(">HI", data, p + 8)
        start = p + 14; end = start + length
        secs.append({"index": i, "role": BOLERO_SECTIONS[i] if i < len(BOLERO_SECTIONS) else f"s{i}",
                     "version": version, "start": start, "end": end, "length": length})
        p = end
    return data, secs


SECTION_READERS = {
    "network": up_net_settings_section,
    "partylines": up_partylines_section,
    "profiles": up_profiles_section,
    "beltpacks": up_beltpacks_section,
    "antennas": up_priority_nodes_section,
    "unknown": up_audio_filters_section,
    "audio_devices": up_audio_devices_section,
    "audio_channels": up_audio_channels_section,
    "gpio": up_gpio_section,
}

def parse_file(path):
    """Parse a .bol; returns {role: parsed} for all 9 sections, each gated on exact byte consumption."""
    data, secs = read_container(open(path, "rb").read())
    out = {"_sections": secs}
    for sec in secs:
        r = SECTION_READERS.get(sec["role"])
        if not r: continue
        s = InputStream(data, sec["start"], sec["end"]); s.p = sec["start"]
        parsed = r(s)
        if s.p != sec["end"]:
            raise ValueError(f"{sec['role']}: consumed to {s.p}, expected {sec['end']} "
                             f"(residual {sec['end']-s.p})")
        out[sec["role"]] = parsed
    return out


# ── target name resolution ──────────────────────────────────────────────────
def build_name_maps(parsed):
    pl = {p["id"]: p["name"] for p in parsed.get("partylines", {}).get("partylines", [])}
    bp = {e["h0"]: e["config"]["name"] for e in parsed.get("beltpacks", {}).get("beltpacks", [])}
    ch = {c["port"]["id"]: c["channel"]["name"] for c in parsed.get("audio_channels", {}).get("channels", [])
          if c["port"]["id"] is not None}
    tr = {t["port"]["id"]: t["name"] for t in parsed.get("gpio", {}).get("triggers", [])
          if t["port"]["id"] is not None}
    return pl, bp, ch, tr

def resolve_target(k, pl, bp, ch, tr):
    t = k["target"]; typ = t["type"]; tid = t["id"]
    if typ == 0: return ""
    if typ == 2: return f"PL: {pl.get(tid, 'Partyline ' + str(tid))}"
    if typ == 1: return f"P2P: {bp.get(tid, 'BP ' + str(tid))}"
    if typ in (3, 5, 6):
        nm = ch.get(tid); d = "BiDir" if typ == 3 else ("Listen" if typ == 5 else "Talk")
        return f"Audio {d}: {nm}" if nm else f"Audio {d} (ch {tid})"
    if typ in (7, 8, 9):
        nm = tr.get(tid)
        return f"Trigger: {nm}" if nm else f"Trigger {tid}"
    return f"{t['type_name']} {tid}"


def export_to_excel(path, out_xlsx=None):
    """Faithful .bol -> formatted .xlsx using all 9 fully validated sections."""
    import openpyxl
    import art_to_excel as A2E
    import pathlib
    parsed = parse_file(path)
    pl, bp, ch, tr = build_name_maps(parsed)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    filename = pathlib.Path(path).name
    net = parsed.get("network", {})
    sys_name = net.get("show_name", "Bolero Standalone")

    # --- Summary Sheet ---
    ws_sum = wb.create_sheet("Summary")
    A2E.title_banner(ws_sum, f"Bolero Standalone Summary: {sys_name}", f"File: {filename}", max_col=3, show_home_link=False)
    A2E.header_row(ws_sum, 4, ["Contents", "Description", "Items"], bg=A2E.C['navy'])
    
    pl_len = len(parsed.get("partylines", {}).get("partylines", []))
    ch_len = len(parsed.get("audio_channels", {}).get("channels", []))
    prof_len = len(parsed.get("profiles", {}).get("profiles", []))
    bp_len = len(parsed.get("beltpacks", {}).get("beltpacks", []))
    ant_len = len(parsed.get("antennas", {}).get("nodes", []))
    dev_len = len(parsed.get("audio_devices", {}).get("devices", []))
    gpio_len = len(parsed.get("gpio", {}).get("triggers", []))

    toc = [
        ("Network", "Show & Network Settings", 1),
        ("Partylines", "Configured Partylines", pl_len),
        ("Audio Channels", "Configured Audio Channels", ch_len),
        ("Profiles", "Beltpack Profiles", prof_len),
        ("Beltpacks", "Registered Beltpacks", bp_len),
        ("Antennas", "Registered Antennas", ant_len),
        ("Audio Devices", "NSA & PunQtum Devices", dev_len),
        ("GPIO Triggers", "GPIO Triggers", gpio_len),
    ]

    for r, (sheet_name, desc, count) in enumerate(toc, 5):
        c1 = A2E.write_cell(ws_sum, r, 1, sheet_name, bold=True)
        c1.hyperlink = f"#'{sheet_name}'!A1"
        c1.font = openpyxl.styles.Font(name="Calibri", size=10, bold=True, color="0563C1", underline="single")
        A2E.write_cell(ws_sum, r, 2, desc)
        A2E.write_cell(ws_sum, r, 3, count, align="center")

    def sheet(title, headers, subtitle=""):
        ws = wb.create_sheet(title)
        A2E.title_banner(ws, title, f"Bolero Standalone | {subtitle}" if subtitle else "Bolero Standalone", max_col=max(3, len(headers)), show_home_link=True)
        A2E.header_row(ws, 4, headers)
        return ws

    def append_row(ws, r_idx, row_data):
        for c_idx, val in enumerate(row_data, 1):
            A2E.write_cell(ws, r_idx, c_idx, val)

    # 1. Show & Network
    ws = sheet("Network", ["Setting", "Value"], "Show & Network Configuration")
    ipn = net.get("artist_net", {})
    def ip_str(v):
        try: return ".".join(str((v >> (8*i)) & 0xFF) for i in (3,2,1,0))
        except Exception: return str(v)
    rows = [
        ("Show Name", net.get("show_name", "")),
        ("Network Label", net.get("label", "")),
        ("System Mode", net.get("system_mode", "")),
        ("Admin PIN", net.get("admin_pin", "")),
        ("OTA PIN", net.get("ota_pin", "")),
        ("— DECT / Radio —", ""),
        ("Radio Power", net.get("radio_power", "")),
        ("Radio Power 2.4G", net.get("radio_power_2g4", "")),
        ("Retransmission Limit", net.get("radio_retransmission_limit", "")),
        ("Frequency Hopping Mode", net.get("frequency_hopping_mode", "")),
        ("Radio Flags", net.get("radio_flags", "")),
        ("Broadcast Mode", net.get("broadcast_mode", "")),
        ("— BP / DECT Monitoring —", ""),
        ("BP Monitoring Threshold", net.get("bp_monitoring_threshold", "")),
        ("BP Monitoring Blocked RSSI", net.get("bp_monitoring_blocked_rssi", "")),
        ("BP Monitoring Interfered RSSI", net.get("bp_monitoring_interfered_rssi", "")),
        ("DECT Scanner Blocked RSSI", net.get("dect_scanner_blocked_rssi", "")),
        ("DECT Scanner Interfered RSSI", net.get("dect_scanner_interfered_rssi", "")),
        ("— Timing / PTP —", ""),
        ("PTP Mode", net.get("ptp_mode", "")),
        ("PTP Domain", net.get("ptp_domain", "")),
        ("Time Source", net.get("time_source", "")),
        ("— Network / Security —", ""),
        ("Registration Mode", net.get("registration_mode", {}).get("mode", "")),
        ("Encryption Key", net.get("encryption_key", "")),
        ("DSCP Settings (Audio / PTP Event / PTP General)",
         " / ".join(str(x) for x in net.get("dscp", [])) or "—"),
        ("Artist Net IP 1", ip_str(ipn.get("ip1"))),
        ("Artist Net IP 2", ip_str(ipn.get("ip2"))),
        ("Artist Net Port", ipn.get("port", "")),
        ("Multicast TTL", net.get("multicast_ttl", "")),
    ]
    _ants = parsed.get("antennas", {}).get("nodes", [])
    _ants_with_prio = [a for a in _ants if a.get("terms") or a.get("profiles")]
    if _ants:
        rows.append(("— Licensed Features (inferred from config) —", ""))
        rows.append(("Beltpack Priority per Antenna",
                     f"CONFIGURED on {len(_ants_with_prio)}/{len(_ants)} antennas "
                     f"(implies P2/priority license in net space)" if _ants_with_prio
                     else "antennas present, no priority lists set"))
    for r_idx, (k, v) in enumerate(rows, 5):
        A2E.write_cell(ws, r_idx, 1, k, bold=not bool(v) and k.startswith('—'))
        A2E.write_cell(ws, r_idx, 2, v)

    # 2. Partylines
    ws = sheet("Partylines", ["ID", "Name"])
    for r_idx, p in enumerate(parsed.get("partylines", {}).get("partylines", []), 5):
        append_row(ws, r_idx, [p["id"], p["name"]])

    # 3. Audio Channels
    ws = sheet("Audio Channels", ["Port ID", "Type", "Name"])
    for r_idx, c in enumerate(parsed.get("audio_channels", {}).get("channels", []), 5):
        append_row(ws, r_idx, [c["port"]["id"], c["channel"]["type_name"], c["channel"]["name"]])

    # 4. Profiles
    ws = sheet("Profiles", ["Profile", "Key", "Function", "Mode", "Priority", "Target"])
    r_idx = 5
    for pr in parsed.get("profiles", {}).get("profiles", []):
        for i, k in enumerate(pr["config"]["keys"]):
            lbl = "Reply" if i == 6 else f"Key {i+1}"
            append_row(ws, r_idx, [pr["name"], lbl, k["function_name"], k["mode_name"], k["priority_name"],
                                   resolve_target(k, pl, bp, ch, tr)])
            r_idx += 1

    # 5. Beltpacks
    ws = sheet("Beltpacks", ["Beltpack", "BP#", "Key", "Function", "Mode", "Priority", "Target"])
    r_idx = 5
    for e in parsed.get("beltpacks", {}).get("beltpacks", []):
        nm = e["config"]["name"]
        for i, k in enumerate(e["config"]["keys"]):
            lbl = "Reply" if i == 6 else f"Key {i+1}"
            append_row(ws, r_idx, [nm, e["h0"], lbl, k["function_name"], k["mode_name"], k["priority_name"],
                                   resolve_target(k, pl, bp, ch, tr)])
            r_idx += 1

    # 6. Antennas
    import datetime as _dt
    NODE_TYPE_NAMES = {0: "Unknown", 1: "DECT", 2: "Client Card (AES67)", 3: "Charger", 4: "DECT 2.4G"}
    bp_by_h0 = {e["h0"]: e["config"]["name"] for e in parsed.get("beltpacks", {}).get("beltpacks", [])}
    prof_by_id = {pr["config"]["id"]: (pr["name"] or pr["config"]["name"])
                  for pr in parsed.get("profiles", {}).get("profiles", [])}
    ws = sheet("Antennas", ["Antenna Name", "Type", "Net Index", "Antenna ID",
                            "Priority Beltpacks", "Priority Profiles", "Last Modified"])
    for r_idx, n in enumerate(parsed.get("antennas", {}).get("nodes", []), 5):
        members = ", ".join(bp_by_h0.get(t, f"#{t}") for t in n["terms"])
        profs = ", ".join(prof_by_id.get(p, f"#{p}") for p in n["profiles"])
        try: ts = _dt.datetime.utcfromtimestamp(n["timestamp"]).strftime("%Y-%m-%d %H:%M")
        except Exception: ts = n["timestamp"]
        append_row(ws, r_idx, [n["name"], NODE_TYPE_NAMES.get(n["node_type"], f"?{n['node_type']}"),
                               n["net_index"], hex(n["node_id"]), members, profs, ts])

    # 7. Audio Devices
    ws = sheet("Audio Devices", ["Config ID", "Device Type", "Name", "Device ID", "Channels Count"])
    for r_idx, d in enumerate(parsed.get("audio_devices", {}).get("devices", []), 5):
        append_row(ws, r_idx, [d["config_id"], d["devtype_name"], d["name"], d["dev_id"], len(d["channels"])])

    # 8. GPIO Triggers
    ws = sheet("GPIO Triggers", ["Port ID", "Trigger Name", "Active", "Mode", "Version Counter"])
    for r_idx, t in enumerate(parsed.get("gpio", {}).get("triggers", []), 5):
        append_row(ws, r_idx, [t["port"]["id"], t["name"], t.get("active", False), t.get("mode_name", ""), t["vc"]])

    # Auto-adjust column widths & add frozen panes
    for ws in wb.worksheets:
        A2E.auto_width(ws)
        ws.freeze_panes = "A5"

    out_xlsx = out_xlsx or path.rsplit(".", 1)[0] + "_faithful.xlsx"
    wb.save(out_xlsx)
    return out_xlsx

if __name__ == "__main__":
    files = sys.argv[1:] or sorted(glob.glob("Bolero Standalone saves/*.bol") or glob.glob("../Bolero Standalone saves/*.bol"))
    all_ok = True
    for f in files:
        name = f.replace("\\", "/").split("/")[-1]
        try:
            r = parse_file(f)
            counts = (f"net='{r['network']['show_name'][:14]}' "
                      f"pl={len(r['partylines']['partylines'])} "
                      f"prof={len(r['profiles']['profiles'])} "
                      f"bp={len(r['beltpacks']['beltpacks'])} "
                      f"ant={len(r['antennas']['nodes'])} "
                      f"devs={len(r['audio_devices']['devices'])} "
                      f"ch={len(r['audio_channels']['channels'])} "
                      f"trig={len(r['gpio']['triggers'])}")
            print(f"[OK] {name[:34]:34s} {counts}")
        except Exception as e:
            all_ok = False; print(f"[FAIL] {name[:34]:34s} {type(e).__name__}: {e}")
    print("\nALL 9 SECTIONS FULLY VALIDATED AND EXACT-CONSUMED ON ALL FILES:", all_ok)
