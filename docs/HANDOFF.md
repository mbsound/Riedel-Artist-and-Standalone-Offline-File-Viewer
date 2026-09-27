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

- **Frames and cards.** `NODE_TYPE_NAMES`. Performer and Artist card, CPU and PSU names are in `card_model()`. Node-Bay text is `port_node_bay()`. Controllers are [Bay A, Bay B]. `node_geom` is the node's box on the network drawing.
- **Ports.**
  - Port Type: `port_type()`.
  - Gains: stored as (byte−36)/2 dB.
  - Room code: `room_code_label()`, with a speaker/headset mode.
  - 2nd audio channel: `port_flags` bit 12.
  - Panel settings (Port Defaults 1/2): `panel_settings()`.
  - Port index, keypad shortcut (`port_338`, to spot-check), and limit-incoming-to-phone-book.
  - Stream blocks (AES67, Dante, Bolero, SIP): named fields such as `packet_time` in µs, `payload_type`, `ssrc`, `multicast`, `bolero_user_id` and `multicast_port_to_bolero`.
  - VoIP codecs and times: `VOIP_CODECS`, `VOIP_PACKET_MS`, `VOIP_RX_BUFFER_MS`.
  - Telephone codec phone numbers, SIP phone account fields, and expansion panels (names and address = stored id − 1).
  - Checked against Director's own Ports grid CSV: `tools/check_ports_csv.py` with `docs/director_exports/*.csv`, 160/160 ports.
- **Keys.** All 18 properties: mode, latching timeout (`LATCHING_TIMEOUTS`), auto label, dim, radio button, text colour, icon, clip label, restart timer, subtitle and auto/show subtitle, group colour, scroll-list mode, action when muted (`MUTED_KEY_ACTIONS`), restore volume, signalization auto, monitoring state and scroll list.
- **Commands.**
  - Priority (`PRIORITY_NAMES`: 0 Low, 1 Standard, 2 High) is the first byte.
  - Monitoring (`MONITORING_NAMES`) is `talk_b4` and `ifb_mode`.
  - Talk flag bits: `TALK_FLAG_BITS`.
  - Also decoded: fixed number, disable crosspoint volume, trunkcall priority, the Listen and Conference-command options, Call to IFB bits, and target/route/trunk port numbers and addresses.
- **Audio patch.**
  - 6×6 crosspoints, index = input×6 + output, named by `AUDIOPATCH_INPUTS`/`OUTPUTS`, with CCP-1116 variants.
  - Mode 0 = Speaker, 1 = Headset.
  - Every DSP element is named: `AUDIOPATCH_ELEMENT_NAMES`, `audiopatch_element_text()`, `audiopatch_routes()`.
  - Option lists: `BANDPASS_HP`/`LP` (bytes stored LP first), `LIMCOMP_FIELDS` (byte order: limiter attack, release, threshold, output level, then compressor attack, release, ratio, threshold), `AMP_OUT_GAINS`, amp in = 0.5 dB steps.
- **Groups and conferences.** Keypad shortcut, icon, colour, trunk-enabled, DynaConf, and the MCR flag. Member words are port numbers.
- **IFB.** Dim scale, label, long name, endpoints.
- **GPIO.** Inverted and normally closed flags, plus GPIO index.
- **System settings (CPhysNet).**
  - `net_panel_defaults()`: system Port Defaults 1/2.
  - `net_call_key_defaults()`: Call Defaults and Key Defaults.
  - `net_port_settings()`: Port Settings page, including dim prios, character set, colours, key banks, Bolero multicast range, and the Live View password and panel PIN.
  - `net_voip_defaults()`.
  - `net_general()`: system name, IFB titles, net number, default trunking addresses, AES67 Defaults, and function colours (`FUNCTION_COLOR_ORDER`).
  - `net_markers()` with `marker_display()`: 123 key markers from `MARKER_NAMES`, with priority, persistence timeout and 1000/2000/RIF display colours.
  - `net_list_a` = nodes, `net_list_b` = fibre links, `net_i32` = network-drawing floats.

## 5. Still to do (roughly by value)

1. **Excel output.** Not started. Every decoder helper above returns Director-worded dicts ready for sheets. Show the panel PIN, Live View password and SIP credentials as plain values: per the user, they are courtesy lock-outs (usually 0000 or 1234), not security data.
2. **Remaining unnamed fields:**
   - IFB `ifb_flag_a`/`b`. The candidate is IsTrunkEnabled; the IFB property setter is in `%LOCALAPPDATA%\ghidra_projects\ifbp\00c71590.c`/`00c71d40.c`.
   - Also unnamed: GPIO `gpio_u8`/`gpio_128`, user `user_u16`/`rights` bits, logic `inputs_a/b`/`line_u8a/b`, IFB container `container_u8/u32`, NSA `nsa_u8`, codec `codec_u8`/`codec_str`.
   - Cards: `sic_u8` (also used in the Node-Bay "(n)"), `sic_u16a/b`, `aes67_*`, `madi_bytes`, `dante_u8`, and VoIP card `voip_u32`/`b1`/`b2`/`u16`/`u8`/`u8b`. Dialog 454 is the VoIP port, not the card; look for the card dialog.
   - Ports: `port_208`, `port_398`, `port_1e8`; `talk_flag_c1` (Talk bit 11 = `+0xc1`).
   - Nodes: `node_88` (= 0x100 + id), `node_8c`/`90`/`a0`/`a4`, `node_a8` (bit mask `0x2d7fffff`), and `node_4fc`/`4fe`, which look like internal counters.
   - System: `net_72c`/`730`/`734` (defaults 1/0/0), `net_7ec`, `net_colour`.
   - Scheduler and event action fields haven't been reviewed.
3. **Artist card variants.** Tell apart -108, -208 and G2 on Artist frames.
4. **ZMXIF (`0x48`).** Transcribe its serializer.
5. **Colour index → name.** Director draws colours as swatches, with no names in the exe, so colours are left as numbers (16 = none).
6. **`.bol` files.** Separate work: see the memory note on the Bolero firmware packages.

## 6. Spot-check list (one batched test save in Director should settle these)

- On a VoIP port (the SIP block in `port_d0c2c0`), which of `s1`/`s3` is RemoteSipId and which is LocalSipId. `s2` = RemoteHost is confirmed.
- System Key Defaults "Key Mode" (`net_bytes['4be']` = 1): read as Auto.
- Port Keypad Shortcut = `port_338` (65535 = none).
- Key "Monitoring state on key" (`monitoring_state`, 2 options): names unknown, because Director fills them at runtime.
- SIP phone connection flag bit 0 (`+0x3a8`): which checkbox it is.
- The Artist CRAZY system default "Copy Reply" reads True, while the other files read False. Confirm.
