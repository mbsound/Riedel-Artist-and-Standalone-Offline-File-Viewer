# Bolero firmware — enum & field reference

Source of truth for the *semantic* layer of the `.bol` format: the Bolero Standalone
Web GUI and `libRadon.so`, both pulled from official firmware packages now in
`Firmware/`. This is the label layer (what a value *means*); the byte layout layer is
in `FORMAT_NOTES.md` §2.

## Provenance

| Firmware | Version | NIC rootfs built | Notes |
|---|---|---|---|
| `Firmware/Firmware/` | Bolero **3.3.0-10** (branch 3.3.x) | Apr 2024 | matches the `ghidra_analysis.txt` symbol dump |
| `Firmware/Firmware 2/` | Bolero **3.4.1-15** (branch 3.4.x) | Nov 2025 | newest; enums below extracted from this |

- Web GUI (AngularJS): `.../extracted/nic_rootfs/var/www/scripts/app-*.js` (unminified — real names).
- Binary serializer: `.../extracted/nic_rootfs/usr/lib/libRadon.so` (ELF32 ARM, has `.dynsym`, 24.8k symbols).
- `NIC_FW-*.pack` is a `RIEDEL-NAND-DESC` container; the NIC rootfs is a squashfs at an
  internal offset (carve using the superblock's `bytes_used` at +0x28). Extract with
  `PySquashfsImage`. Script: scratchpad `radon_disasm.py` (capstone) resolves symbols → offsets.

**Rule unchanged:** a value is *confirmed* only from Director, a live Bolero web UI, the
firmware itself, or the file. Enums below are firmware-confirmed (GUI/JSON layer). Where the
`.bol` **binary** uses a *different* encoding than the GUI, that is called out explicitly.

## GUI/JSON enums (from `app-*.js` `CONFIG`)

These are the values `radonApp` exposes over its JSON/REST API and the GUI renders.

### KEY_FUNCTIONS_ENUM
```
NONE:0  TALK:1  TALK_ALWAYS_LISTEN:2  TALK_AND_LISTEN:3  LISTEN:4  MONITOR:5
MONITOR_SELECT:6  NOTIFICATION_BEEP:7  NOTIFICATION_BEEP_SELECT:8  REPLY:9
MENU_SHORTCUT:10  TOGGLE:11  MONITOR_TRIGGER:12  SET_TRIGGER:13  VOLUME_INCREASE:14
VOLUME_DECREASE:15  MUTE_MIC:16  CONTROL:17  CONTROL_WITH_DESTINATION:18
```

### KEY_MODES_ENUM  (GUI/JSON only — see warning under "binary mapping")
```
MOMENTARY:0  LATCHING:1  AUTO:2
```

### KEY_PRIORITIES_ENUM
```
STANDARD:0  HIGH:1  LOW:2
```

### AUDIO_PORT_TYPE  ← **matches the `.bol` key-token TYPE byte**
```
NONE:0  BP:1  PL:2  AUDIO_CHANNEL_BI_DIR:3  KEY_PARAMETER:4
AUDIO_CHANNEL_INPUT:5  AUDIO_CHANNEL_OUTPUT:6
TRIGGER_INPUT:7  TRIGGER_OUTPUT:8  TRIGGER_VIRTUAL:9
```

### AUDIO_CHANNEL_TYPE
```
UNKNOWN:0  LEGACY_NSA:1  PQ_ANALOG:2  PQ_PARTYLINE:3
UNIVERSAL_AUTOMATIC:9  UNIVERSAL_ANALOG:10  UNIVERSAL_DIGITAL_LEFT:11
UNIVERSAL_DIGITAL_RIGHT:12  UNIVERSAL_DIGITAL_BOTH:13
USB_AUDIO_LEFT:14  USB_AUDIO_RIGHT:15  USB_AUDIO_BOTH:16  HEADPHONE:17
TWO_WIRE_FIRST_CHANNEL:18  TWO_WIRE_SECOND_CHANNEL:19
```

### IP_SETTINGS.TYPES_ENUM
```
AUTO:0  DHCP:1  STATIC:2
```

## Binary (`.bol` / RTX) mapping — confirmed vs open

The `.bol` is written by `libRadon.so`'s **RTXSerializer** (`::pack` methods), which is a
**different, lower-level encoding** than the GUI/JSON enums above. Verified so far:

- **Key-token TYPE byte == `AUDIO_PORT_TYPE`.** The current parser's token types line up
  exactly: `0x01`=BP (P2P, target is a beltpack ID), `0x02`=PL (partyline), `0x05`=audio
  channel input, `0x06`=audio channel output. `0x03` (bi-dir) / `0x07`–`0x09` (triggers)
  are defined but unseen in the 8 sample files. **This replaces the earlier "inferred"
  note** — it is now firmware-backed.

- **Key MODE byte is NOT `KEY_MODES_ENUM`.** Distribution over 3,707 keys in the 8 samples:
  `0`→3216 (87%), `2`→421 (11%), `1`→70 (2%). If the file used the GUI enum (MOMENTARY=0),
  87% of keys would be Momentary, which is implausible. The dominant `0` is the unset/default
  value = **Auto** (Bolero's default mode), consistent with the Director-confirmed Artist
  CPhysKey encoding (0=Auto, 1=Momentary, 2=Latching). Corroborating: Talk-only keys
  (func `4`) skew to mode `2`/`1` and rarely `0` — real Talk keys are PTT/latching, not Auto.
  **Still open:** which of `1`/`2` is Momentary vs Latching. Resolve with a one-change test
  save (like the Artist test) or the Ghidra pass below. Do **not** apply the GUI enum here.

- **Key FUNC byte is its own low-level talk/listen state**, not `KEY_FUNCTIONS_ENUM`.
  Observed values `0,1,2,4,9` (parser reads: `1`=Listen, `2`=Talk&Listen, `4`=Talk,
  `8`=Always-Listen, `9`=Talk+Always-Listen, `0`=none). This looks like a talk/listen state
  field, distinct from the 0–18 GUI function enum. Needs Ghidra confirmation.

## CONFIRMED via decompilation (Ghidra 12.1.4 on libRadon.so 3.4.1)

Full decompilation of the serializer family is saved at
`docs/firmware_decomp/libRadon_3.4.1_serializers.c` (3,371 functions). Tools:
`radon_disasm.py` (capstone, resolves symbol→offset + PLT), `DecompileTargets.java`
(the Ghidra headless script). Re-run: `analyzeHeadless <proj> radonHL -import libRadon.so
-postScript DecompileTargets.java` with JDK 21. These findings are firmware-grade confirmed.

### BPKey struct + field semantics (from `BPKey::set`, `BPKey::pack`, `deserializeBpKey`)
`BPKey::set(BPKeyFunction, BPKeyMode, BPKeyPriority, int, MutedKeyPressAction,
BPKeyDoublePressMode, AudioPortId const&, FunctionSpecificParameter const&)` stores to:

| Offset | Field | Enum / validator | Valid |
|---|---|---|---|
| +4  | **function** | `BPKeyFunction` (`isValidNum` ≤ 0x12) | 0–18 |
| +8  | **mode** | `BPKeyMode` (`isValidNum` ≤ 4) | 0–4 |
| +0xc| **priority** | `BPKeyPriority` (`isValidNum` ≤ 2) | 0–2 |
| +0x10| int (destination flags) | — | — |
| +0x14| **mutedKeyPressAction** | (`isValidNum` ≤ 2) | 0–2 |
| +0x18| **doublePressMode** | `BPKeyDoublePressMode` (`isValidNum` ≤ 2) | 0–2 |
| +0x1c| **target** `AudioPortId` | type@+0x20, u16 id@+0x24 | — |
| +0x28| FunctionSpecificParameter | packed only when function needs one | — |

- **`BPKeyFunction` == `KEY_FUNCTIONS_ENUM` exactly** (validator bound 0x12=18 == the 0–18 GUI enum;
  `convertBPKeyFunction` is an identity thunk; `deserializeBPKeyFunction` stores the JSON int as-is).
  So the `.bol` **function** value = 0 None, 1 Talk, 2 Talk+AlwaysListen, 3 Talk&Listen, 4 Listen,
  5 Monitor, 6 MonitorSelect, 7 NotifBeep, 8 NotifBeepSelect, 9 Reply, 10 MenuShortcut, 11 Toggle,
  12 MonitorTrigger, 13 SetTrigger, 14 VolUp, 15 VolDown, 16 MuteMic, 17 Control, 18 ControlWithDest.
- **`BPKeyMode` = {0 Momentary, 1 Latching, 2 Auto, 3 On-only, 4 Off-only}** (matches GUI
  `EXTERNAL_KEY_MODES`). NOTE the input mode is *normalized per function* in `deserializeBpKey`
  before storing (e.g. functions without a mode get forced values), so a raw byte must be read in
  the context of its function.
- **Target = `AudioPortId`**: `pack` writes `[u8 type]` and, iff type≠0, `[u16 id]`. `type` is
  `AUDIO_PORT_TYPE` (BP 1 → P2P beltpack id, PL 2 → partyline, 5/6 audio in/out, 7–9 triggers).

### `.bol` RTX key emit order (`RTXSerializer::serializeBPKey`)
Per key: `putString(label)` → `putUInt8(function)` → then, gated by function value:
mode(+8), priority(+0xc for func 1–5), destination-flags(+0x10), packed
`(muted@+0x14 & 0xF) | (doublePress@+0x18 << 4)`, `AudioPortId` target → trailing `00 <arg> 00`.
`serializeBPKeys` loops keys 1–6 + Reply (7 iterations, 28-byte stride).

### ⚠ Impact on the current parser (bug)
The removed `bol_extractor.py` read a key token as `[type][sub][id][func][mode]`, but the real stream is
`[label][function][mode][priority]…[AudioPortId type][id]` — **reversed** (function is near the
start; type/id are the AudioPortId at the end). Its `FUNC_MAP` (1=Listen, 4=Talk) and `MODE_MAP`
(0=Auto) do **not** match the firmware. The 87%-zero "mode" byte it tallied was most likely
*priority* (usually Standard=0) or a trailing `00`, not the mode field — which is why the old
frequency reasoning pointed the wrong way. **Next step: rewrite the beltpack/profile key reader to
follow `serializeBPKey`/`serializeBpConfig` exactly, then re-validate against all 8 samples.**
Before shipping, still validate the on-disk *framing* (RTXEntityDescriptor headers around each
record) byte-for-byte, since that wraps these fields.

## (Original TODO — now largely done) Finalize the binary key encoding

The function that packs beltpack keys is
`radon::RTXSerializer::serializeBPKeys` (3.4.1 vaddr `0x3a9b04`; also `serializeBpConfig`
`0x3aab64`). It loops 7 times (keys 1–6 + Reply) over a 28-byte (`0x1c`) in-memory key
struct and calls a templated RtxData writer (reached via PLT `0x2f4580`, so field encoding
must be read from the decompiled body, not the disassembly stub). Point
`DecompileSerializers.java` at `serializeBPKeys`, `serializeBpConfig`,
`serializeProfileDescriptions` (`0x3aa8d4`), `serializeBPAudioPorts` (`0x3a9938`) and
`serializePLDescriptions` (`0x3aa3b4`) to read the exact field order and the func/mode
integer meanings.
