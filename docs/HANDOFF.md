# Riedel Director `.Art` decoder: handoff (2026-09-27)

This is for whoever continues the work, human or AI agent. Read this first, then `FORMAT_NOTES.md` §3A for the file layout.

## 1. Goal

`.Art` save files come from Riedel **Director 8.9.D2**. The goal is to turn them into formatted Excel, decoding **every** feature, including ones the user doesn't use. MCR (Master Control Room) is out of scope. `.bol` (Bolero) files come later.

The main code is `Code/artist_reader.py`, a pure-Python sequential reader. `parse_art(bytes) -> (header, records)` reads each record and checks the file ends with "ENDE". All five sample files (8.6 schema `0x520` and 8.9 schema `0x580`) parse byte-exact.

**Regression check.** Run this after every change, from `Code/`:

```
find .. -iname '*.art' -print0 | xargs -0 -n1 python -c "import sys,artist_reader as A;h,r=A.parse_art(open(sys.argv[1],'rb').read());print('ok',len(r))"
```

Expected record counts: 6112, 1345, ~6727 (Artist CRAZY changes as the user edits it), 6422, 1749.

## 2. Environment (Windows on ARM, Parallels)

- **Python:** x64 Python 3.13 at `C:\Users\mattbell\AppData\Local\Programs\Python\Python313\python.exe`. capstone needs x64.
- **Git:** `C:\Program Files\Git\cmd\git.exe`. Commit with `-c user.name="Claude" -c user.email="matt@mbsound.org"`. Don't `git add -A`, because `tools/node_modules` belongs to the user.
- **Director exe:** `Reference binaries/Director 8.9.D2.exe`. Set `DIRECTOR_EXE` to this path for `tools/dre.py`.
- **Ghidra 12.1.4:** at `%LOCALAPPDATA%\Programs\ghidra\ghidra_12.1.4_PUBLIC`.
  - JDK 21: `%LOCALAPPDATA%\Programs\jdk\jdk-21.0.12.1+1`. Set `JAVA_HOME` and `PATH`, and set `GHIDRA_HEADLESS_MAXMEM=4G`.
  - Project: `%LOCALAPPDATA%\ghidra_projects\Director89` (already analysed).
  - Headless run:
    `analyzeHeadless.bat <gp> Director89 -process Director89.exe -noanalysis -readOnly -scriptPath Code/tools/ghidra -postScript DecompileList.java <list.txt> <outdir> 0`
    (list lines are `name 0xADDR`, and any address inside the function works),
    or `-postScript DecompileRange.java 0xSTART 0xEND <outdir>`.
  - Older decompiles are in `%LOCALAPPDATA%\ghidra_projects\{uniq3/funcs, decomp3, sys, sys2, props, ...}`. `uniq3/funcs/<addr>.c` holds the serializers.
- **Artist CRAZY:** the user's test file, `Artist test files (not show files)/Artist CRAZY.Art`. Earlier versions were snapshotted to the session scratchpad and may be gone.

## 3. How fields were decoded: use these methods, most productive first

1. **Serializers.** Each class's `Serialize` (vtable slot 25) gives field order, types, version gates and member offsets. The reader cites the function for every class.
2. **Director's automation/property interface.** Each class has an id→name switch; key properties, for example, are named by `FUN_00c211b0`. Setters such as `FUN_00c215c0`, `FUN_00c7946d` (keys), `FUN_00c51640` (Talk) and `FUN_00cb9dc0` (port stream getter) map property names to member offsets. `props.json`/`propfn.json` list the 316 property names; regenerate them with the scratch scripts described below if needed.
3. **Dialogs.**
   - `tools/dialogs.py` dumps every dialog template with its control ids, labels and geometry, into `docs/director_dialogs.txt`.
   - `tools/ddx_map.py` maps each dialog class's DDX calls (member offset → control id → label, with its group box) into `docs/director_ddx.txt`.
   - A dialog's OK handler (`SendMessage(*(HWND*)(this+M+0x20))` → `obj+OFF`) links the object field to the label.
   - Ghidra names MFC `DDX_Text`. `FUN_00818bf7` = DDX_Control, `FUN_0081916c` = DDX_Check/value, `FUN_0081939f` = DDX_Radio/value.
4. **Option lists.** These come from the combo-fill functions (`SendMessage 0x143`/`0x151`) or from static string tables. If a table is filled at runtime, find the static source it's copied from; the marker table at `0xfee9c0` was found this way.
5. **Byte scans.** `tools/dre.py` has `xrefs_imm`, `callers`, `func_start`, `wstr`/`astr`. To find writers of `+OFF`, scan for the disp32 bytes; capstone's linear sweep stops at data.
6. **Test saves.** Only for spot checks, batched into one save. The user prefers code-first decoding.

Pitfalls:
- The decompiler hides implicit-ECX string targets. Read the `lea edx,[reg+OFF]` before `call 0xddb0e0` (Ar_ReadString) in the disassembly instead.
- Ghidra's "removing unreachable block" can drop switch cases. If a list looks short, read the jump table.

## 4. What is decoded (see the reader: every named field and helper cites its source)

- **Frames and cards.** `NODE_TYPE_NAMES`. Performer and Artist card, CPU and PSU names are in `card_model()`. Card generation variants (-108, -208, G2, -008, SIC) are decoded from `FUN_00ccbb20` based on frame chassis `node['node_type']` (+0x4f8). Node-Bay text is `port_node_bay()`. Controllers are [Bay A, Bay B]. `node_geom` is the node's box on the network drawing. `node_address` (+0x500, Property 2 'NodeAddress'), `node_id` (+0x88 = 0x100 + node_address), `soa` (+0x4fc, Property 3 'Soa' - Start of Allocation ring port offset), and `noa` (+0x4fe, Property 4 'Noa' - Number of Allocations frame port count).
- **Ports.**
  - Port Type: `port_type()`.
  - Gains: stored as (byte−36)/2 dB.
  - Room code: `room_code_label()`, with a speaker/headset mode.
  - 2nd audio channel: `second_audio_channel` (pre-0x2e `port_1e8` or `port_flags` bit 12).
  - Port Architecture: `port_architecture` (+0x208: 0 = SIC AES67 card, 1 = classic client card, 2 = virtual/connection).
  - Audiopatch flags: `audiopatch_flags` (+0x398: 9-byte array of DSP bypass/mute flags).
  - Panel settings (Port Defaults 1/2): `panel_settings()`.
  - Port index, keypad shortcut (`port_338`, to spot-check), and limit-incoming-to-phone-book.
  - Stream blocks (AES67, Dante, Bolero, SIP): named fields such as `packet_time` in µs, `payload_type`, `ssrc`, `multicast`, `bolero_user_id` and `multicast_port_to_bolero`.
  - VoIP SIP block (`port_d0c2c0`): `local_sip_id` (+0x08, `s1`), `remote_host` (+0x04, `s2`), `remote_sip_id` (+0x0c, `s3`), and `audio_codec` (FUN_00cb9dc0 & FUN_00d0c2c0).
  - VoIP codecs and times: `VOIP_CODECS`, `VOIP_PACKET_MS`, `VOIP_RX_BUFFER_MS`.
  - Telephone codec phone numbers, SIP phone account fields, and expansion panels (names and address = stored id − 1).
  - Checked against Director's own Ports grid CSV: `tools/check_ports_csv.py` with `docs/director_exports/*.csv`, 160/160 ports.
- **Keys.** All 18 properties: mode, latching timeout (`LATCHING_TIMEOUTS`), auto label, dim, radio button, text colour, icon, clip label, restart timer, subtitle and auto/show subtitle, group colour, scroll-list mode, action when muted (`MUTED_KEY_ACTIONS`), restore volume, signalization auto, monitoring state and scroll list.
- **Colour Palette.** Decoded 16-step palette table at `0xfeb6e0` (`SWATCH_COLORS`, `swatch_color_name`): 0 Orange (#FFB366), 1 Yellow (#FFFF73), 2 Yellow-Green (#D0FF73), 3 Light Green (#A2FF73), 4 Green (#73FF73), 5 Mint (#80FFAA), 6 Cyan-Green (#73FFD0), 7 Cyan (#73FFFF), 8 Light Blue (#80AAFF), 9 Blue (#7373FF), 10 Indigo (#B38CFF), 11 Violet (#D073FF), 12 Magenta (#FF73E8), 13 Rose (#FF66B3), 14 Red (#FF6666), 15 Light Grey (#D7D7D7), 16 None.
- **Commands.**
  - Priority (`PRIORITY_NAMES`: 0 Low, 1 Standard, 2 High) is the first byte.
  - Monitoring (`MONITORING_NAMES`) is `talk_b4` and `ifb_mode`.
  - Talk flag bits: `TALK_FLAG_BITS`, including bit 9 (`allow_fixed_number`), bit 10 (`allow_phonebook`), and bit 11 (`allow_dialpad`, Property 17 'AllowDialpad').
  - Also decoded: fixed number, disable crosspoint volume, trunkcall priority, the Listen and Conference-command options, Call to IFB bits, and target/route/trunk port numbers and addresses.
- **Audio patch.**
  - 6×6 crosspoints, index = input×6 + output, named by `AUDIOPATCH_INPUTS`/`OUTPUTS`, with CCP-1116 variants.
  - Mode 0 = Speaker, 1 = Headset.
  - Every DSP element is named: `AUDIOPATCH_ELEMENT_NAMES`, `audiopatch_element_text()`, `audiopatch_routes()`.
  - Option lists: `BANDPASS_HP`/`LP` (bytes stored LP first), `LIMCOMP_FIELDS` (byte order: limiter attack, release, threshold, output level, then compressor attack, release, ratio, threshold), `AMP_OUT_GAINS`, amp in = 0.5 dB steps.
- **Groups and conferences.** Keypad shortcut, icon, colour (`SWATCH_COLORS`), trunk-enabled, DynaConf, and the MCR flag. Member words are port numbers.
- **IFB.** Dim scale, label, long name, endpoints, `is_trunk_enabled` (+0x12, bit 1), `ifb_flag_a` (+0x11, bit 0 internal engine flag). Containers have `container_version` (+0x84, constant 2) and `container_index` (+0x88, 0-indexed for "IFB-Container %u of 10").
- **GPIO.** Inverted and normally closed flags, GPIO index, `channel_selection` (+0x11c, property index 5), and `off_delay` (+0x128, OffDelay in ms up to 10000ms).
- **Users and permissions.** `user_manager` (+0xa0), `USER_RIGHT_BITS` with 16 decoded permission flags (from CUserPP DIALOG 184 and FUN_00ccd0e0), and object base trailer rights mask (1=Edit, 2=Create children, 4=Delete children).
- **Logic.** `from_pin` and `to_pin` (output/input pin indices on CPhysLogicLine), `active_inputs` and `not_active_inputs` (triggering Active vs Not Active on CPhysLogicDst), and float coordinates for `rect`.
- **VoIP and Codecs.** VoIP card properties (`primary_dns`, `secondary_dns`, `tcp_udp_port`, `dns_hostname`, `dscp`, `link_mode`), Codec connection (`channel_selection`, `auto_answer`, `auto_dial_enabled`, `auto_dial_number`), and NSA connections (`input_channel`, `output_channel`).
- **ZMXIF (`0x48`).** Transcribed from `FUN_00d03c80` and registered in `READERS`.
- **SIC cards.** `sub_bay` (+0x8c, 1-based sub-bay index), `start_port` (+0x8e, first allocated port index), and `allocated_ports` (+0x90, AllocatedPorts count). SIC MADI decoded 1:1 with `assigned_ports`, `frame_length` (56/64), `sync_external`, `smux`, and `sync_mode`. SIC AES67 decoded with interface port/GPIO allocations. SIC Dante decoded with `allocated_ports`. Classic MADI card (+0x104..0x106) decoded with `up_interface` (Optical/Electrical), `down_interface`, `frame_length` (56/64), and `channel_block` (1..8).
- **System settings (CPhysNet).**
  - `net_panel_defaults()`: system Port Defaults 1/2.
  - `net_call_key_defaults()`: Call Defaults and Key Defaults.
  - `net_port_settings()`: Port Settings page, including dim prios, character set, colours, key banks, Bolero multicast range, and the Live View password and panel PIN.
  - `net_monitor_defaults()`: Dialog 703 Monitor Defaults. **Corrected by Claude:** `+0x72c` = `monitor_call_to_ifb`, `+0x730` = `monitor_call_to_port` (both switchable / always on / always off), `+0x734` = `monitor_keystate` (initial off / initial on). Store FUN_00a2a820, init FUN_00a2a8f0; groups placed by template geometry. Key names unchanged, so the Excel sheet needs no change.
  - `net_voip_defaults()`.
  - `net_general()`: system name, IFB titles, net number, default trunking addresses, AES67 Defaults, function colours (`FUNCTION_COLOR_ORDER`, decoded via `SWATCH_COLORS`), and `define_colors_automatically` (Dialog 729).
  - `net_markers()` with `marker_display()`: 123 key markers from `MARKER_NAMES`, with priority, persistence timeout and 1000/2000/RIF display colours.
  - `net_list_a` = nodes, `net_list_b` = fibre links, `net_i32` = network-drawing floats.
- **Excel Exporter (`Code/art_to_excel.py`).**
  - Generates a complete, beautiful 14-sheet workbook directly driven by `artist_reader.py` with zero heuristic guesswork or `NOT_DECODED` placeholders:
    1. `Summary`: System metadata, release, schema, node/card/port/key/conference/group/IFB/patch counts.
    2. `System Settings`: Complete CPhysNet settings (System Name, Net Number, Default Trunking Addresses, AES67 Defaults, Monitor Defaults Dialog 703, Color Defaults Dialog 729, Call & Key Defaults Dialog 207/208, Port Settings Dialog 209 with plain PIN/passwords, Key Markers).
    3. `Nodes & Topology`: All frame mainframes with Node #, Node ID (`0x100 + address`), Chassis Model, Ring SOA, NOA, Controller A/B, PSU redundancy, and Optical Fibre Ring links (CPhysLWL).
    4. `Cards & Slots`: Bay slots, sub-bay allocations, card models, start port, allocated ports, Media 1 & 2 IP configurations, MADI sync modes, Dante names, and VoIP DNS/hostname.
    5. `Ports`: 1:1 replica of Director's Ports Grid (Port #, Label, Long Name, Alias, Subtitle, Port Type, Node-Bay, Architecture, Gains, Room Code/Mode, 2nd Channel, Shortcuts, Bolero multicast / SIP host / NSA channels).
    6. `Panels & Keys`: Every key across all SmartPanels, Bolero beltpacks, and expansion modules (Key #, Label, Subtitle, Mode, Latching Timeout, Primary Command & Target, Priority, Secondary stacked command).
    7. `Conferences`: All conferences (Partylines) with label, alias, long name, trunking, DynaConf, shortcut, and full resolved member ports list.
    8. `Groups`: All directed talkgroups with label, long name, shortcut, trunk address, and full resolved member ports list.
    9. `IFB Routing`: All IFB broadcast channels with IFB #, label, long name, dim level, trunking, and resolved Input, Mix-Minus, and Output endpoints.
    10. `Audio Patch`: Mixing matrices and DSP element chains (unmuted crosspoints, muted output amps, bandpass high/low cut filters, limiter/compressor dynamics, input gains).
    11. `Logic & GPIO`: Hardware GPI input channels, relay output channels, logic gates, and internal matrix logic lines.
    12. `IP Trunks`: Dedicated sheet for inter-matrix IP trunklines, VoIP connections, and SIP accounts with host addresses and codecs.
    13. `Users & Access`: All operator & administrator accounts with username, full name, role, rights mask, decoded permissions, and courtesy lock PIN/password.
    14. `Scheduler`: Automated scheduler tasks with SYSTEMTIME calendar recurrence, times, and linked matrix events.

## 5. Parallel Work Division on Artist (Multi-Agent Protocol)

To maximize throughput and prevent file conflicts, work on Artist is strictly partitioned into two decoupled tracks:

### TRACK A: Claude's Assigned Duties (Core Reverse Engineering & Reader Decodes)
**Scope:** `artist_reader.py`, `Reference binaries/Director 8.9.D2.exe`, Ghidra (`%LOCALAPPDATA%\ghidra_projects\Director89`), `tools/dre.py`, `docs/HANDOFF.md`.
**Deliverables:**
1. **Solve Remaining Spot-Checks in Director Binary:**
   - **SIP phone connection flag bit 0 (`+0x3a8`):** Trace Dialog 639 / Dialog 676 or setter in `Reference binaries/Director 8.9.D2.exe` to find the exact UI checkbox name.
   - **Key "Monitoring state on key" options:** Identify the string values for the 2 combo box choices in Dialog 205 (Key Details).
   - **System Key Defaults "Key Mode" (`net_bytes['4be']` = 1):** Verify the exact enum string in Dialog 207.
   - **Port Keypad Shortcut (`port_338`):** Verify control ID and setter in the Ports configuration dialog.
   - **System Default "Copy Reply" flag:** Confirm whether Artist CRAZY's `True` value reflects the Dialog 208 checkbox.
2. **Decode Any Remaining Unmapped Flags:**
   - Ensure all property setters and record trailers are decoded 1:1.
   - Maintain 100% backward-compatibility aliases on all records.
3. **Regression Gate:**
   - Run the regression test after every modification:
     `python -c "import glob, artist_reader as A; [print(f, len(A.parse_art(open(f, 'rb').read())[1])) for f in glob.glob('../**/*.Art', recursive=True)]"`
   - Expected counts: `6112`, `6422`, `1749`, `1345`, `6727`.
4. **Git Protocol:**
   - Commit author MUST be: `-c user.name="Claude" -c user.email="matt@mbsound.org"`.
   - Never run `git add -A` (protect `tools/node_modules/`).
   - Only commit `artist_reader.py` and documentation files.

### TRACK B: Antigravity's Assigned Duties (Excel Reporting Engine & Presentation)
**Scope:** `Code/art_to_excel.py`, `Code/export_tool.py`.
**Deliverables:**
1. **Swatch Color Integration:**
   - Add "Group Color" and "Text Color" columns to Sheet 6 (`Panels & Keys`) using `swatch_color_name` (displaying both color name and hex code).
   - Add "Color" column to Sheet 7 (`Conferences`) and Sheet 8 (`Groups`).
   - Add Dialog 729 Function Colors and Monitor Defaults to Sheet 2 (`System Settings`).
2. **VoIP SIP Accounts on Grid:**
   - Display `local_sip_id`, `remote_host`, `remote_sip_id` on Sheet 5 (`Ports`) and Sheet 12 (`IP Trunks`).
3. **Visual Styling & Formatting:**
   - Polish headers, column widths, freeze panes, number formats (e.g. dB gains, IP addresses, port numbers).
4. **Unified CLI Runner (`Code/export_tool.py`):**
   - Provide a single command-line interface to batch export `.Art` (and `.bol`) files to Excel and JSON with verification logs.

---

## 6. Spot-check list (Status & Findings)

- [x] **VoIP Port SIP Block (`port_d0c2c0`):** CONFIRMED. `s1` (+0x08) = `local_sip_id`, `s2` (+0x04) = `remote_host`, `s3` (+0x0c) = `remote_sip_id`.
- [x] **Artist Card Variants:** CONFIRMED. `FUN_00ccbb20` computes card variants (-108, -208, G2, -008, SIC) based on chassis `node['node_type']`.
- [x] **Swatch Color Palette:** CONFIRMED. Table `0xfeb6e0` contains 16 COLORREF swatches (0..15 + 16 None).
- [x] **IFB Flags (+0x11 / +0x12):** CONFIRMED. `f & 1` (+0x11) = internal engine flag, `(f >> 1) & 1` (+0x12) = `is_trunk_enabled`.
- [x] **VoIP SIP-ID getters (re-verified by Claude):** `FUN_007dcbd0` (LocalSipId) reads block `+0x08`, `FUN_007dcba0` (RemoteSipId) reads `+0x0c`.
- [x] **System Key Defaults "Key Mode" (`net_bytes['4be']`):** stored as the list position of `FUN_00b12360` (Auto / Momentary (PTT) / Latching); the store `FUN_00b93b10` writes CB_GETCURSEL directly. Value 1 = **Momentary (PTT)** (not Auto).
- [x] **Port Keypad Shortcut = `port_338` (65535 = none):** `FUN_00cfd900` ("%s %i Keypad Shortcut(s) changed to <none>") writes `+0x338`.
- [x] **Key "Monitoring state on key"** (`monitoring_state` / `monitoring_state_name`): 0 = "initial off", 1 = "initial on" (list built at `0x6d1dd7` into `0x12fe24c`).
- [x] **SIP phone connection flag bit 0 (`+0x3a8`):** the "SIP transport protocol" **UDP** radio (control `0x732`; TCP is `0x731`) → `sip_transport`.
- [x] **System Default "Copy Reply":** `+0x4b7` <- dialog 206 checkbox 1879 "Enable Copy Reply" (FUN_00b97dd0). Only stored from schema `0x560` (8.9), so 8.6 files have no value (read as False); CRAZY's True is real.

## 7. Track A: still unnamed (after Claude's 2026-09-27 pass)

All fields listed here earlier are now resolved. Every stored field has a Director name, or is documented as reserved/legacy with the code evidence.

Resolved on 2026-09-28:
- **Node `+0x8c`** is the Serial Number (`serial_number`, 8-digit hex, blank when 0). Setter `FUN_00ca5040`; the node dialog `FUN_00b9f990` rejects a serial already used by another node.
- **Node `+0xa0` / `+0xa4` / `+0xa8`** are the alarm masks. Relay 1 is `relay1_mask` / `relay1_alarms`, Relay 2 is `relay2_mask` / `relay2_alarms`, and the Error mask is `error_mask` / `error_alarms`.
  - The bit names are in `NODE_ALARM_BITS`, taken from the "Error mask" page (init `FUN_00b9e360`, DDX `FUN_00b9e680`, dialog 260).
  - The default is `0x2d7fffff`. Converting a frame to Artist S masks it with `0x8060001f`.
  - Suggested Excel columns for the Nodes sheet: Serial Number, Error Alarms, Relay 1 Alarms, Relay 2 Alarms.
- **Node `+0x90`:** reserved. Its setter `FUN_00ca5140` has no caller in 8.9, and it initialises to 0.
- **GPIO** `gpio_u8` / `gpio_128`: already aliased as `channel_selection` / `off_delay`. **User** `user_u16`: already aliased as `user_manager`.
- **AES67 cards (SIC and panel):** the old keys are kept and named copies added.
  - `media[]` gains `dhcp`, `sip_port`, `dscp`, `igmp_version` and `network_speed` (SIC only).
  - `aes67_bytes` is PTP, parsed into `ptp_settings`: domain, priority 1/2, mode (multicast/hybrid), role (automatic/TimeReceiver), and the four intervals as signed log2 seconds.
  - The old `ptp` key is in fact the DNS page, now also in `dns`: automatic, primary, secondary, suffix.
  - `aes67_stream` plus `aes67_u8` are the NMOS page, now in `nmos`: port, IS-04 versions, registration mode/address/port/version, interface, enabled.
  - SIC only: `aes67_16` is `device_uuid`, and `aes67_tail` is `bolero_discovery_ip` / `bolero_discovery_port` (the Discovery page).
  - `aes67_list_a/b` are the ids of owned child objects; the loader ignores them.
  - Suggested Excel additions for the Cards sheet: PTP role/mode and priorities, NMOS enabled, Bolero discovery IP:port, DHCP / IGMP per media.
- **Commands:** `cmd_ref` is the object that auto-created the command (`created_by`; the UI shows " (created by %s)", `FUN_00c57290`). `cmd_bit4` (`+0x94`) is reserved: only load, save and init touch it in 8.9.
- **System:** `net_i32` is the network-drawing box (`net_geom`, as floats). `net_colour` (`+0x4e4`) is a legacy colour: its setter `FUN_00c9dd10` has no caller and the default is `ffffff`.
- **VoIP card** `voip_u32`: reserved. The loader `FUN_00c28870` discards it and the writer always writes 0.

Suggested method:
- Find the object's dialog in `docs/director_ddx.txt`.
- Its OK handler maps `obj+OFF` to the control. To locate it, byte-scan for the disp32 write, like the Monitor Defaults fix.
- Place controls by template geometry, not by the DDX label guess.
