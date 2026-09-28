# Bolero `.bol` save format — firmware-exact specification

Derived by decompiling `libRadon.so` (3.4.1) with Ghidra and reading the **actual unpack
routines** the firmware uses to load a save. This is the authoritative read model: a faithful
reader must mirror these `::unpack` methods exactly and **consume each section to its declared
length with zero leftover bytes** (the correctness gate).

All 9 sections in this document have been validated with zero residual bytes across all 8 production
`.bol` save files in `Bolero Standalone saves/`.

Decompiled source references:
- `docs/firmware_decomp/libRadon_3.4.1_serializers.c`
- `docs/firmware_decomp/unpack_bodies_ref.c`
- `docs/firmware_decomp/func_index.txt`

---

## 1. Serializer Architecture

libRadon has **two** key/config serializers. They are NOT interchangeable:

1. **Save file (`.bol`)** → `CombinedNetConfig::packForSaving` / `unpackFromSaved`, which drives the
   fixed-layout `X::pack` / `X::unpack` methods (`BPConfig::unpack`, `BPKey::unpack`, …) over a plain
   byte `OutputStream` / `InputStream`. **This is what a `.bol` reader must implement.**
2. **Live network transfer** → `RTXSerializer::serialize*` (`serializeBPKey`, …), a block-fragment
   protocol (`checkAndSplit` into ≤245-byte blocks) that also writes per-key label strings and
   omits fields conditionally. **Not used by the save file.**

Field *meanings and enums* are shared between the two; only the framing differs.

---

## 2. Stream Primitives (`InputStream`)

All multi-byte numeric values are stored in **big-endian** order.

- `getUInt8()` / `getInt8()`: 1 byte.
- `getBool()`: 1 byte (`0x00` = false, non-zero = true).
- `getUInt16()` / `getInt16()`: 2 bytes, big-endian (`>H` / `>h`).
- `getUInt32()` / `getInt32()`: 4 bytes, big-endian (`>I` / `>i`).
- `getString()`: `[u8 length][length bytes]` (ASCII / UTF-8 string).
- `read(n)`: `n` raw bytes.
- `TimestampVC`: 8 bytes (`[u32 timestamp][u32 vc]`).
- `AudioPortId`: `[u8 type]` + (if `type != 0`) `[u16 id]`.

---

## 3. Container & Section Framing (`CombinedNetConfig::unpackFromSaved`)

On-disk container structure:
```
[u16 checksum]
[u8  container_version = 0x02]
[u32 inflated_length (big-endian)]
[zlib compressed payload]
```

Decompressed stream header:
```
TimestampVC (8 bytes: u32 saved_at, u32 vc)
u16 NetConfig version (0x0006)
u8  section count (9)
TimestampVC (8 bytes)
u32 net_space_id
```

Followed by `section_count` sequential sections. Each section has a 14-byte envelope:
```
TimestampVC (8 bytes: u32 timestamp, u32 vc)
u16 section_version
u32 section_length
[section_length bytes of section data]
```

Standard fingerprint across 3.3.x–3.4.x: `2/6/10.2.17.19.1.1.6.6.60000`
Approved Section Order:
| Index | Role Name | Version | Origin | Firmware Class |
|---|---|---|---|---|
| 0 | `network` | 10 | 0x2b | `radon::NetSettings` |
| 1 | `partylines` | 2 | 0x24 | `radon::Partylines` |
| 2 | `profiles` | 17 | 0x30 | `radon::Profiles` |
| 3 | `beltpacks` | 19 | 0x2f | `radon::RegisteredBPs` |
| 4 | `antennas` | 1 | 0x6b | `radon::priorityNodes::PriorityNodes` |
| 5 | `unknown` (audio filters) | 1 | 0x5b | `radon::AudioFilters` |
| 6 | `audio_devices` | 6 | 0x3d | `radon::IODeviceConfig` |
| 7 | `audio_channels` | 6 | 0x3b | `radon::AudioChannels` |
| 8 | `gpio` | 60000 | 0x3f | `radon::TriggerConfig` |

---

## 4. Section 0: Network Settings (`radon::NetSettings`)

Routine: `radon::NetSettings::unpackDataFromSaved` → `radon::NetSettingsData::unpack`

### Byte Layout:
1. `getString()`: `netName` (show / network name)
2. `getUInt8()`: `systemMode` (`SystemMode`: 0 Standalone/AES67, 1 Standalone/Link, 2 Artist)
3. `getInt16()`: `adminPin`
4. `getInt16()`: `otaPin`
5. `read(4)`: `audioMulticastGroup` (`SimpleIp` address bytes)
6. `getUInt8()`: `multicastTtl`
7. `getUInt8()`: `timeSource` (`TimeSource`: 0 Internal, 1 NTP, 2 PTP)
8. `getString()`: `netLabel` (network label)
9. `getInt32()`: `timeOffset`
10. `getUInt8()`: `timeFormat` (`TimeFormat`: 0 24h, 1 12h)
11. `getUInt8()`: `dateFormat` (`DateFormat`: 0 YMD, 1 DMY, 2 MDY)
12. `getUInt8()`: `radioPower` (`RadioPower`)
13. `getUInt8()`: `radioPower2G4` (`RadioPower`)
14. `getUInt8()`: `radioRetransmissionLimit` (`RadioRetransmissionLimit`)
15. `getUInt8()`: `frequencyHoppingMode`
16. `getUInt8()`: `radioFlags` (bit 0: radio enabled, bit 1: radio priority, bit 2: bp mon threshold, bit 3: 2G4 high power, bit 4: dect scanner, bit 5: web server encryption)
17. `RegistrationMode::unpack`:
    - `u8 mode` (0 Open, 1 Pin, 2 Closed)
    - `i8`
    - `i16`
18. `getUInt8()`: `broadcastMode`
19. `read(32)`: `broadcastEncryptionKey` (AES-256 key bytes)
20. `getUInt8()`: `ptpDomain`
21. `getUInt32()`: `debugFlags`
22. `DSCPSettings::unpack`:
    - 3 × `getUInt8()`: DSCP audio, DSCP PTP event, DSCP PTP general
23. `getUInt8()`: `ptpMode`
24. `ArtistNetSettings::unpack`:
    - `u32 ip1`, `u32 ip2`, `read(4) netmask`, `u16 port` (byte-swapped)
25. `getInt16()`: `bpMonitoringThreshold`
26. 4 × `getInt8()`:
    - `bpMonitoringBlockedRssiThreshold`
    - `bpMonitoringInterferedRssiThreshold`
    - `dectScannerBlockedRssiThreshold`
    - `dectScannerInterferedRssiThreshold`
27. `getUInt8()`: `term_count`
28. `term_count` × `getUInt16()`: assigned `TermId`s
29. `BPOverrideSettings::unpack`: 4 polymorphic override records in fixed sequence:
    - **Override 0 (Bluetooth, 4 bytes)**: `u8 mode`, `u8 a`, `u8 b`, `i8 c`
    - **Override 1 (Brightness, 12 bytes)**: `u8 mode`, `u8 sub`, 2 × `BPBrightness` (each 4 × `u8`), `i8 i1`, `i8 i2`
    - **Override 2 (Notification, 7 bytes)**: `u8 mode`, `u32 signalization`, `i8 i1`, `i8 i2`
    - **Override 3 (Speaker, 2 bytes)**: `u8 mode`, `bool enabled`

---

## 5. Section 1: Partylines (`radon::Partylines`)

Routine: `radon::Partylines::unpackDataFromSaved`

### Byte Layout:
1. `getInt16()`: `remove_count`
2. `remove_count` × `[i16 id][u32 vc]`: tombstoned partyline records
3. `getUInt8()`: `count` (number of active partylines)
4. `count` × `Partyline::unpack`:
   - `getInt16()`: `id` (partyline ID, 1-indexed)
   - `getUInt8()`: unused / padding byte
   - `getString()`: `name` (partyline display label)
   - `getBool()`: `b1`
   - `getUInt32()`: `vc` (version counter)
   - `getBool()`: `b2`

---

## 6. Section 2: Profiles (`radon::Profiles`)

Routine: `radon::Profiles::unpackDataFromSaved` → `Profiles::unpackDiffData`

### Byte Layout:
1. `getInt16()`: `remove_count`
2. `remove_count` × `[i16 id][u32 vc]`: tombstoned profile records
3. `getUInt8()`: `count` (number of profiles)
4. `count` × `Profile::unpack`:
   - `getString()`: `name` (profile name)
   - `BPConfig::unpack`: full beltpack configuration block (see Section 8 below)
   - `getBool()`: `b1`
   - `getBool()`: `b2`
   - `getUInt32()`: `u32`

---

## 7. Section 3: Beltpacks (`radon::RegisteredBPs`)

Routine: `radon::RegisteredBPs::unpackDataFromSaved`

### Byte Layout:
1. `getUInt16()`: `count` (registered beltpack count)
2. `count` × `RegisteredBPEntry::unpack`:
   - `u16 h0`: Beltpack assigned number (`bp_num` / BP ID)
   - `u16 h1`: Hardware / radio index
   - `u16 h2`: Registration state index
   - `u32 vc`: Version counter
   - `read(32)`: Beltpack AES-256 pairing key
   - `BPConfig::unpack`: active beltpack configuration (see Section 8 below)
   - 4 × `getUInt32()`: tail runtime / registration metadata
3. `getUInt16()`: `unregistered_count`
4. `unregistered_count` × `[u16 id][u32 vc]`

---

## 8. Common Struct: `radon::BPConfig`

Used identically inside both `Profile::unpack` and `RegisteredBPEntry::unpack`.
Vector sizes not present in stream are fixed by C++ constructor defaults:
- `N_KEYS = 7` (Keys 1–6 + Reply)
- `N_ROTARIES = 2`
- `N_EXTERNAL_KEYS = 4`

### Full Field Sequence:
1. `getInt16()`: `id`
2. `getString()`: `name` (User / beltpack label)
3. `getUInt16()`: `u16_20`
4. `getUInt8()`: `u8_24`
5. `AudioPortsList::unpack`:
   - `getUInt8()`: `n_ports`
   - `n_ports` × `AudioPortEntry`:
     - `AudioPortId port` (`u8 type`, `u16 id` if type != 0)
     - `i8 val`
     - `bool flag`
     - `u8 mask`
     - Popcount of `mask` × `getUInt8()`
6. **Keys**: fixed **7** × `BPKey::unpack` (Keys 1–6, then Key 7 = Reply):
   - `u8 function`: `BPKeyFunction` (0 None, 1 Talk, 2 Talk+AlwaysListen, 3 Talk&Listen, 4 Listen, … 9 Reply, etc.)
   - `u8 mode`: `BPKeyMode` (0 Momentary, 1 Latching, 2 Auto, 3 On-only, 4 Off-only)
   - `u8 priority`: `BPKeyPriority` (0 Standard, 1 High, 2 Low)
   - `u8 dest_flags`: destination flags
   - `u8 muted_key_press_action`: 0–2
   - `u8 double_press_mode`: 0–2
   - `AudioPortId target`: `[u8 type]` + (`[u16 id]` if type != 0)
   - `FunctionSpecificParameter`: only if `function == 7` (`[i8 a][u32 b]`)
7. `getUInt8()`: count × `SingleFunction::unpack` (Function List A)
   - `[u8 function][u8 b][AudioPortId target]` + (`[i8][u32]` if `function == 7`)
8. `getUInt8()`: count × `TriggerFunction::unpack`:
   - `[AudioPortId port]` + `SingleFunction::unpack`
9. `getUInt8()`: count × `SingleFunction::unpack` (List C)
10. `getUInt8()`: count × `SingleFunction::unpack` (List D)
11. `getUInt8()`: count × `SingleFunction::unpack` (List E)
12. Fixed **2** × `getUInt16()`: rotary settings
13. Fixed **4** × `ExternalBPKey::unpack`: `[u8 a][u16 id]`
14. `BPVolumeData::unpack`: fixed **17 raw bytes** (volume and master gain levels)
15. `getUInt8()`: `u8_d0`
16. `BPAudioFilters::unpack`: fixed **6 × `u8`** (HPF, LPF, and notch filters)
17. Fixed **11 × `u8` / `i8`**: miscellaneous single-byte beltpack preferences
18. `BPBrightness::unpack` × 2: each fixed **4 × `u8`** (display and LED brightness)
19. 2 × `getUInt8()`: display settings
20. `BPBluetooth::unpack`: `[u8 a][u8 b][i8 c]`
21. `BPSignalization::unpack`: `getUInt32()`
22. `getUInt16()`: `u16_160`
23. `BPQuickMenu::unpack`: `[u8 count][count raw bytes]`
24. `BPPriorityConfig::unpack`: `[u8 a][u8 count]` then `count` × `[u32 nodeId][u8 priority]`
25. `BPChangeRights::unpack`: `getUInt32()`
26. `VoxBase::unpack` × 2: each `[u8 a][i8 b][i8 c][u8 d][u16 e][u16 f][bool g]`
27. `getUInt8()`: `replyPartylineMode`
28. `ArtistBPConfig::unpack`:
    - `getString()`: artist config name
    - `VoxBase::unpack`: artist vox
    - `getUInt16()`: count × `[u16 key][i8 vol][bool mute]`
    - Fixed **7** × `ArtistBPKey::unpack`: `[getString name][6 x u8][u16][u8]`

---

## 9. Section 4: Antennas & Priority Nodes (`radon::priorityNodes::PriorityNodes`)

Routine: `radon::priorityNodes::PriorityNodes::unpackDataFromSaved` → `unpackAllData`

### Byte Layout:
1. `getInt16()`: `count` (number of priority nodes / antennas)
2. `count` × `(u32 node_id, PriorityNode)`:
   - `getUInt32()`: `node_id` (AES67 / radio Node ID, e.g. `0x10001`)
   - `PriorityNode::unpack`:
     - `getUInt8()`: `node_type`
     - `getInt16()`: `net_index`
     - `getString()`: `name` (antenna name)
     - `getString()`: `label` (antenna label)
     - `getUInt16()`: `term_count`
     - `term_count` × `getUInt16()`: assigned term IDs
     - `getUInt16()`: `profile_count`
     - `profile_count` × `getUInt16()`: profile IDs
     - `getUInt32()`: `timestamp`

---

## 10. Section 5: Audio Filters (`radon::AudioFilters`)

Routine: `radon::AudioFilters::unpackDataFromSaved` → `unpackAllData`

### Byte Layout:
1. `getUInt16()`: `count1` (version counter change list)
2. `count1` × `[u8 filter_id][u32 vc]`
3. `getUInt8()`: `count2` (custom audio filter list)
4. `count2` × `(u8 filter_id, AudioFilter)`:
   - `getUInt8()`: `filter_id`
   - `AudioFilter::unpack`:
     - `getUInt32()`: `vc`
     - `getString()`: `name`
     - `getUInt8()`: `filter_type`
     - `getUInt8()`: `section_count`
     - `section_count` × `AudioFilterSection::unpack` (12 bytes per section):
       - `getUInt8()`: `type` (filter curve type)
       - `getUInt16()`: `freq` (corner frequency clamped to 20..7999 Hz)
       - `read(8)`: `q` (IEEE-754 64-bit float Q-factor, 8 bytes)
       - `getInt8()`: `gain` (clamped to -24..+12 dB)

*(In current standalone `.bol` show files, `count1 = 0` and `count2 = 0`, consuming `00 00 00`.)*

---

## 11. Section 6: Audio Devices (`radon::IODeviceConfig`)

Routine: `radon::IODeviceConfig::unpackDataFromSaved` → `unpackAllData`

### Byte Layout:
1. `getUInt8()`: `count` (number of configured audio devices)
2. `count` × `(u8 config_id, SingleIODeviceConfig)`:
   - `getUInt8()`: `config_id` (`IODeviceConfigId`)
   - `SingleIODeviceConfig::unpack`:
     - `IODeviceConfigData::unpack`:
       - `getUInt8()`: `devtype` (`IO_DEVICE_TYPE`):
         - `1`: NSA-002A
         - `2`: PunQtum (Q210P)
         - `3`: NSA-003A … `10`: NSA-010C
       - `getString()`: `name1`
       - `getString()`: `name2`
       - `read(4)`: IP address / network field
       - `getUInt16()`: `u1` (port, byte-swapped)
       - `read(4)`: second IP field
       - `getUInt16()`: `u2` (port, byte-swapped)
       - `getUInt8()`: `chan_cnt`
       - `chan_cnt` × `IODeviceAudioChannelConfig::unpack` (fixed 8 bytes: `[i8][u8][i8][i8][u8][i8][u8][i8]`)
       - `getUInt8()`: `t1_cnt`
       - `t1_cnt` × `getUInt8()`: trigger input flags
       - `getUInt8()`: `t2_cnt`
       - `t2_cnt` × `getUInt8()`: trigger output flags
       - **Polymorphic Device Configuration Block**:
         - **If `devtype == 2` (PunQtum)**:
           - `u8 b1`
           - `u8 chan_cnt`
           - `chan_cnt` × `[4 bytes][getString name1][getString name2]`
           - `u8 ctrl1_cnt`
           - `ctrl1_cnt` × `[u8 b][getString name]`
           - `u8 ctrl2_cnt`
           - `ctrl2_cnt` × `[u8 b][getString name]`
         - **If `devtype in (3, 4, 5, 6, 7, 10)` (NSA with NsaConfigData)**:
           - `u8 flags`
           - `n_in` × `u8`: input channel modes
           - `n_out` × `u8`: output channel modes
           - `n_pl` × `u8`: partyline channel modes
           *(Counts: devtype 3 → 2 PL; 4 → 4 In; 5 → 1 Out; 6, 10 → 2 In, 2 Out; 7 → 4 In, 2 Out)*
         - **If `devtype == 1` (NSA-002A)**:
           - No trailing device-specific bytes
     - `IODeviceId::unpack`: `read(8)` (8-byte hardware identifier)
     - `getUInt32()`: `vc` (version counter)

---

## 12. Section 7: Audio Channels (`radon::AudioChannels`)

Routine: `radon::AudioChannels::unpackDataFromSaved` → `unpackAllData`

### Byte Layout:
1. `getInt16()`: `count1` (version counter change list)
2. `count1` × `[u8 a][u32 vc]`
3. `getInt16()`: `count2` (number of audio channels)
4. `count2` ×:
   - `AudioPortId port`: (`[u8 type]` + `[u16 id]` if `type != 0`)
   - `getUInt32()`: `vc`
   - `AudioChannel::unpack`:
     - `getUInt8()`: `first`
     - Fixed 7-byte header: `[i8][i8][i8][u8 f18][i8][u8 f24][i8]`
       *(f18 is the primary channel type, f24 is secondary)*
     - `getString()`: `name` (audio channel display name)
     - Fixed 4-byte header: `[u8][i8][i8][i8]`
     - `AudioPortsList::unpack`: assigned routing list
     - `getUInt8()`: count × `SingleFunction::unpack` (List A)
     - `getUInt8()`: count × `TriggerFunction::unpack`
     - `getUInt8()`: count × `SingleFunction::unpack` (List C)
     - `getUInt8()`: count × `SingleFunction::unpack` (List D)
     - `getUInt8()`: count × `SingleFunction::unpack` (List E)
     - `VoxBase::unpack`
     - `getBool()`: `flag`
     - **Conditional Filters & Limiters** (determined strictly by `f18` and `f24` values):
       - If `f18 == 10 or f18 in (18, 19)`: `[bool on][u16 v]` (Filter 1)
       - If `f18 in (18, 19)`: `[bool on][u16 v]` (Filter 2)
       - If `f24 in (18, 19)`: 2 × `[bool on][u16 v]` (Filters 3 & 4)
       - If `f18 == 10 or f18 in (18, 19)`: `[bool on][i8 a][u16 b][u16 c]` (Limiter 1)
       - If `f24 in (17, 18, 19)`: `[bool on][i8 a][u16 b][u16 c]` (Limiter 2)

---

## 13. Section 8: GPIO Triggers (`radon::TriggerConfig`)

Routine: `radon::TriggerConfig::unpackDataFromSaved` → `unpackAllData`

### Byte Layout:
1. `getInt16()`: `count1` (version counter change list)
2. `count1` × `[u8 id][u32 vc]`
3. `getInt16()`: `count2` (number of triggers)
4. `count2` ×:
   - `AudioPortId port`: (`[u8 type]` + `[u16 id]` if `type != 0`, types: 7 TriggerInput, 8 TriggerOutput, 9 TriggerVirtual)
   - `getUInt32()`: `vc`
   - `SingleTriggerConfig::unpack`:
     - `getUInt8()`: `io_device_config_id` (`IODeviceConfigId`: 0 if virtual/unassigned, or ID of NSA device)
     - `getUInt8()`: `trigger_pin_index` (0-indexed hardware pin / channel on that device, `0xff` if unassigned)
     - `getBool()`: `active` (trigger enabled state)
     - `getString()`: `name` (trigger display name, e.g. `'NSA1INTrigger 1'`, `'RADIO TRIGGER'`)
     - `getUInt8()`: `trigger_mode` (`TriggerMode`: 0 `normal`, 1 `forceOn`, 2 `forceOff`)

---

## 14. Firmware Enums (`libRadon.so` Ground Truth)

### `BPKeyFunction`:
| Value | Identifier | Description |
|---|---|---|
| 0 | `None` | Key unassigned / disabled |
| 1 | `Talk` | Talk to target |
| 2 | `Talk+AlwaysListen` | Talk with constant background listen |
| 3 | `Talk&Listen` | Talk and Listen simultaneously |
| 4 | `Listen` | Listen only |
| 5 | `Monitor` | Audio monitoring |
| 6 | `MonitorSelect` | Monitor channel selection |
| 7 | `NotificationBeep` | Audible alert / cue tone |
| 8 | `NotificationBeepSelect` | Cue tone selection |
| 9 | `Reply` | Dynamic reply to last caller |
| 10 | `MenuShortcut` | Jump to beltpack menu item |
| 11 | `Toggle` | Logic / state toggle |
| 12 | `MonitorTrigger` | Monitor GPI status |
| 13 | `SetTrigger` | Fire GPO trigger |
| 14 | `VolumeIncrease` | Bump volume |
| 15 | `VolumeDecrease` | Lower volume |
| 16 | `MuteMic` | Local mic mute |
| 17 | `Control` | System control |
| 18 | `ControlWithDestination` | Targeted system control |

### `BPKeyMode`:
| Value | Mode | Description |
|---|---|---|
| 0 | `Momentary` | Push-to-talk (active only while depressed) |
| 1 | `Latching` | Push-to-toggle (tap on, tap off) |
| 2 | `Auto` | Default: tap latches, hold is momentary |
| 3 | `On only` | Press activates only |
| 4 | `Off only` | Press deactivates only |

### `AUDIO_PORT_TYPE`:
| Value | Type | Target Meaning |
|---|---|---|
| 0 | `None` | None / disabled |
| 1 | `BP(P2P)` | Point-to-Point direct call to Beltpack ID |
| 2 | `PL` | Partyline Conference ID |
| 3 | `AudioChannelBiDir` | Bi-directional 4-Wire channel |
| 4 | `KeyParameter` | Parameterized key reference |
| 5 | `AudioChannelInput` | Line/audio input channel (Listen) |
| 6 | `AudioChannelOutput` | Line/audio output channel (Talk) |
| 7 | `TriggerInput` | GPI trigger input |
| 8 | `TriggerOutput` | GPO trigger output |
| 9 | `TriggerVirtual` | Virtual internal logic trigger |

### `IO_DEVICE_TYPE`:
| Value | Type | Description |
|---|---|---|
| 1 | `NSA-002A` | Riedel NSA-002A Network Stream Adapter (6-ch analog/GPIO) |
| 2 | `PunQtum` | PunQtum Q210P Speaker Station |
| 3 | `NSA-003A` | 2 Partyline Interface |
| 4 | `NSA-004A` | 4 Audio Input Interface |
| 5 | `NSA-005A` | 1 Audio Output Interface |
| 6 | `NSA-006A` | 2 In / 2 Out Interface |
| 7 | `NSA-007A` | 4 In / 2 Out Interface |
| 8 | `NSA-008A` | NSA Series 8 Interface |
| 9 | `NSA-009A` | NSA Series 9 Interface |
| 10 | `NSA-010C` | NSA-010C 2 In / 2 Out Interface |

### `TriggerMode`:
| Value | Mode | Behavior |
|---|---|---|
| 0 | `normal` | Follows input pin or logic signal state |
| 1 | `forceOn` | Overridden permanently ON / active |
| 2 | `forceOff` | Overridden permanently OFF / inactive |

---

## 15. Implementation & Verification Gate

The correctness criterion is:
$$\text{stream.position} == \text{section.end} \quad (\text{residual bytes} == 0)$$
for every section across all test files. Any deviation indicates an unhandled field or incorrect count.
All 9 sections in `bol_faithful.py` satisfy this exact-consumption gate on all 8 production `.bol` saves.
