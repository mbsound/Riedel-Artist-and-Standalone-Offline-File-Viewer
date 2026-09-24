# Riedel file format notes (handoff)

Working notes for continuing the Artist `.art` / Bolero `.bol` decoding work, written for a new session on a Windows PC with Riedel Director installed. Everything here was worked out from real show files and a static read of `Director 8.9.D2.exe`. Nothing was obtained by running Director.

**Rule for this project:** a value is only *confirmed* if it was read from Director, a live Bolero web UI, or a model name stored in the file itself. Recollections such as "that key should be latching" are not confirmation. Several answers given that way turned out to be guesses and had to be reverted.

---

## 1. Where things are

| Path | What |
|---|---|
| `web_extractor.html` | Browser converter. Source of truth for decoding logic. |
| `riedel_formats.py` | Shared Python decoders and the version whitelist (mirrors the web code). |
| `art_extractor.py`, `bol_extractor.py`, `bol_gui.py` | Python CLI and macOS app. Output must match the web converter exactly. |
| `tools/harness.js` | Runs the web converter headless in Node on sample files (needs `npm install pako@2.1.0 exceljs@4.4.0`). |
| `tools/director_disasm.py` | Static helpers for reading Director's executable (needs `pip install capstone`). |

### Sample files (gitignored; copy them to the new machine by hand)
Everything to transfer is collected in one folder, `Verified Real Artist Files/` (about 61 MB):

| Path inside the folder | What |
|---|---|
| `show-save-A.Art`, `show-save-B.Art`, `show-save-C.Art` | The trusted set. Real shows, Director 8.6.D1-29, schema `0x520`. |
| `Artist test files (not show files)/Artist CRAZY.Art` | Director 8.9.D2-14 test system (schema `0x580`). The only 8.9 sample; operator ground truth in §7. |
| `Artist test files (not show files)/test-save-D.Art` | Director 8.6. |
| `Bolero Standalone saves/*.bol` | The 8 Bolero Standalone NetConfig saves. |
| `Reference binaries/Director 8.9.D2.exe` | Director, for static reading (`tools/director_disasm.py`). |
| `Reference binaries/libRadon.so` | Bolero firmware library the `.bol` layout was read from (`CombinedNetConfig::packForSaving`). |

The `show-save-B.Art` in the project root is a **JSON export renamed to .Art**, not a binary. Use the copy in this folder.

### Regression check (run after every change)
```bash
V="Verified Real Artist Files"
node tools/harness.js web_extractor.html out/ "$V"/*.Art "$V/Artist test files (not show files)"/*.Art "$V/Bolero Standalone saves"/*.bol
```
Then compare `out/*.json` with `art_extractor.parse_art_file()` and `bol_extractor.parse_bol_file()`. Cards, nodes, ports, keys, conferences, warnings and notices must all be identical.

---

## 2. Bolero Standalone `.bol`

- **Container:** `[u16 checksum][u8 container version = 2][u32 BE inflated length][zlib payload]`.
- **Payload** (from `radon::CombinedNetConfig::packForSaving` in the Bolero firmware `libRadon.so`):
  - `u16 NetConfig version (6)`, `u8 section count (9)`
  - TimestampVC `(u32 saved-at, u32 node id)` at bytes 3–10
  - NetId (8 bytes) at 11–18, then a u32
  - Per section: TimestampVC (8 bytes), `u16 version`, `u32 BE length`, data. The walk ends exactly at the end of the payload.
- **Sections in order** (verified versions): network 10, partylines 2, profiles 17, beltpacks 19, antennas 1, unknown 1, audio devices 6, audio channels 6, GPIO 60000.
- **Approved fingerprint:** `2/6/10.2.17.19.1.1.6.6.60000`.

**Beltpacks**
- Each record starts with a 7-byte hardware ID `0c e4 e5 …`. The count of these equals the section's leading u16.
- The user name is `u8 len + text` at ID+42, followed by the `u16` beltpack ID.
- Keys follow the marker `02 00 00 00 01 00`. The byte before the marker is `01` or `00`, so it isn't matched.

**Profiles**
- Record: `[u8 len][name] 00 [u8 id] [u8 len][label] 00`, with ids strictly increasing.

**Antennas**
- Record: `u16 count`, then per antenna: `u32 id, u8, u16 net index, u8 len + name, u16, u8 n + n×u16, u16 m + m×u16, u32 timestamp`.
- Only named antennas are stored.

**Keys**
- Key token: `[type][sub][id][func][mode]`. Types: `02` partyline, `01` P2P (target is a beltpack ID), `05`/`06` audio.
- Mode byte: `0` = **Auto** (inferred: it's the unset value, the most common, and Auto is Bolero's default). `1` and `2` are Momentary and Latching in an **unconfirmed** order. `4` appears on some reply keys and is unknown.
- A `.bol` does not contain live RF or online state, nor net masters.

---

## 3. Artist `.art`

### 3.1 Header and version
- `FF FE FF 0E` + UTF-16LE `R2000 Cfg-File`, then `u32 LE schema` at `0x20`, then `u8 len + "Director version X.Y.Dn-B.hash"` at `0x24`.
- Version rules:
  - key-record type code: `0x4000` in 8.6, `0x5000` in 8.9;
  - 8.9 writes 4 extra bytes after each conference long name.

### 3.2 Object directory
Starts right after the version string:
- `u32 0, u32 1, u32 (0x1f5)`, then groups of `[u32 count][count × (u16 class, u16 0, u32 object id)]`.
- The class codes are Director's internal object classes, not hardware types. Known classes:

| Class | Object |
|---|---|
| `0x101` | COAX-108 card (operator) |
| `0x103` | AIO-108 card (operator) |
| `0x107` | MADI-108 card (operator) |
| `0x108` | card carrying trunk lines (VoIP?) |
| `0x102`, `0x109`, `0x10a` | classic cards, **unconfirmed** (old table said CAT5 / AES67 / Dante) |
| `0x10b` | AES67 card on 1024 frames |
| `0x10e` | MADI card on 1024 frames |
| `0x10f` | Dante card on 1024 frames |
| `0x10c` | unknown (appears in 1024 frame card lists) |
| `0x10d` | per-port settings object |
| `0x13` | key target: point-to-point |
| `0x14` | key target: audio / listen source |
| `0x15` | key target: call light / logic |
| `0x16` | key target: conference |
| `0x17` | key target: group |
| `0x18` | key target: reply |

### 3.3 Records
Almost every object record starts with `u32 type (0x4000 / 0x5000)` + `u32 system id`. The system id is detected per file as the most frequent u32 after a type code; never hard-code it (CRAZY is `b8 03 ff 52`, show is `e8 57 98 11`).

### 3.4 Master endpoint table and endpoint descriptors
- **Master table:** `u32 n`, then `n × (u32 type code, u32 object id)`, in the same order as the endpoint descriptors.
- **Descriptors** are found by the marker `09 00×9 01`. The name is length-prefixed just before it. After it come `u8 len + alias`, `u8 len + local name`, and so on.
- The local name holds Director's `slot.port` (e.g. `1.18`). Display names are often renamed.
- A split 4-wire port appears as two endpoints (`In.`/`Out.`) with the same `slot.port`.
- **AES67 stream** (Bolero beltpacks), just before the name: `fa 00×6 | 08 | mode | IPv4 LE | u16 RTP port | u16 stream # | 10 a4 00`. Mode 1 means the multicast address is set.

### 3.5 Endpoint type codes (type-code table in both code bases)
- **Confirmed:**
  - `0x401` / `0x402` 4-wire split In / Out, and `0x403` plain 4-wire (AIO): operator, CRAZY Node #3 card 9.
  - `0x405` DCP-1016E, `0x406` RCP-1012E, `0x407` RCP-1028E, `0x424` RCP-1112, `0x425` RCP-1128, `0x426` DCP-1116, `0x432` CCP-1116 (takes 2 ports): operator, CRAZY Node #1 card 1.
  - `0x428` VCP-1004 and `0x429` VCP-1012 (model names in the file); `0x440` Bolero beltpack; `0x443` DSP-2312 (port names say "2312").
- **Likely:** `0x505` = 32-key panel (ports named "1232", 64 key slots) and `0x506` = 16-key panel ("1216", 32 slots). CRAZY uses them at Node #1 ports 2.1 / 2.2, Node #3 4.1 / 4.2 / 10.8 / 11.3, and Node #6 Bay 1 and Bay 9.
- **Everything else** in the table is marked "(unconfirmed)".
- A panel stores **2 key slots per key**, so the key count = slots ÷ 2, read from the file.

### 3.6 Keys
One record per key slot:
```
u32 type, u32 system id, u32 previous owner, 00, u8 slot, u8 len + label,
u32 flags, 00, u16 has-assignment, [u32 assignment id], u32 owner,
u8 len + long name, u16 value
```
The next record's header repeats the owner. The owner is the endpoint object id.
- **Target type** comes from the assignment object's directory class (§3.2).
- **Bolero beltpacks:** slots 0–5 are keys 1–6, slot 6 is Reply.
- **Flags** hold talk / listen and mode; they are **not decoded**. Two readings both fit the (guessed) answers: bit `0x02` or bit `0x4000` = latching. Decoding needs Director readings.

### 3.7 Conferences, trunks, groups
- **Conference / trunk / DYNACONF record:**
  ```
  type, system id, u32 1, 00, u8 len + label, u8 len + alias,
  u32 n, n × member ids, …, u32 kind, 00, u8 len + long name, [4 bytes in 8.9]
  ```
  `kind` low byte: `0x08` conference, `0x09` trunk line, `0x18` DYNACONF.
- **Group record:** same header but **no alias byte**, then `u32 n` and the members, with the long name followed by `ff ff`.
  - Verified: show save A's `a person` group contains exactly his panel and his beltpack.
  - A group key is always a one-way Talk (operator).

### 3.8 Frames (nodes)
- **Frame record** ends with `[u32 model code][u8 len + name][type][system id][ring id]`.
  - Model code: `3` Artist 32, `4` Artist 64, `5` Artist 128, `9` Artist 1024 (all confirmed).
  - The name is stored as-is (e.g. `<prefix> Node #12`).
- **Frame object ids:** the ring object stores `[ring id][u32 n][n × frame id]`, in frame-record order.
- **Card list:** the bytes just before a frame's name list that frame's card objects, in bay order, **skipping empty bays**.
  - Each classic card's bay comes from its own port records, `[type][system id][card id][00][u32][00][u8 len + alias]`. The aliases name the ports on that card: default `P.9.2` gives the bay directly; custom aliases are matched to endpoints.
  - Cards without ports fill gaps only when unambiguous.
- **1024 cards:** `[type][system id][card id][00][u32 slot][u32 frame id][u8][u8 len + name]`. Network cards follow 13 bytes on with `IPv4 / mask / gateway` (LE), and a second (redundant) block 21 bytes after that. Bay = slot + 1.
  - Each card's records list the endpoint ids on it, which places those endpoints on their frame.
- **Node number:** not decoded. Each frame record has a field `ff ff 7f 2d 00000000 NN NN 01` with NN = 2, 3, 4, 7 for CRAZY Node #1, #2, #3, #6, 12 for `<prefix> Node #12`, and 20 for `<Artist 1024 frame>`. It's unclear whether NN is the node ID.
- **Unassigned:** about 53–57 endpoints in the big show files still can't be placed on a frame.

---

## 4. Director 8.9.D2 findings (static read)

- PE32, image base `0x400000`, MSVC with RTTI (e.g. `.?AVCPhysPanel@@`, `CPhysNode`, `CPortTrunkingSetupPP`) and embedded source paths (`...\Director\PhysGroup.cpp`, `PhysIFB.cpp`, `IFBDocument.cpp`).
- **Hardware-type → name function** at VA `0x9dffe0` (ecx = code), with jump tables at `0x9e01e4`, `0x9e0314` and `0x9e032c`:

| Code | Name | Code | Name |
|---|---|---|---|
| `0x2` | CPU-128F | `0x16` | MADI-108 G2 |
| `0x3` | CPU-128HP | `0x18` | PSU-32 G2 |
| `0x4` | CPU-128S | `0x19` | PSU-64 G2 |
| `0x5` | COAX-108 | `0x1a` | PSU-128 G2 |
| `0x6` | AIO-108 | `0x1b` | PSU-32+16 |
| `0x7` | CAT5-108 / AES-108 | `0x1c` | PSU-32+80 |
| `0x8` | AES-108 | `0x20` | VoIP-108-G2 |
| `0x9` | GPI-116 | `0x21` | VoIP-108-G2 RP |
| `0xa` / `0xb` | CPU-128SD1 / RC | `0x22`–`0x28` | Connect IPx8 / IPx2 variants |
| `0xc` / `0xd` | CPU-128S G2 / RC | `0x33` | AES67-108-G2 |
| `0xe` | CPU-128F G2 | `0x34` | AES67-108-G2 RP |
| `0xf` / `0x10` | CPU-128F G2 rear cards | `0x35` | DANTE-108 G2 |
| `0x13` | MFR-32 | `0x36` | DANTE-108 RP |
| `0x14` | MFR-64 | `0x65` | NIC-200 |
| `0x15` | MFR-128 | `0x66`–`0x6c` | 2xx cards |
| `0x100` | UIC-128 | `0x106` | UIC-128-II |
| `0x101` | PSU-1024 | `0x1000`– | Performer (CPU-032, MFR-32-16/-80, COAX-008, AIO-008/-009, CAT5-008, AES-008, relay cards, VoIP-008-G2) |
| `0x102` | Artist-1024 Frame | | |
| `0x103` | FAN-1024 | | |

- **These hardware codes were not found in the `.art` files.** The files use the object classes from §3.2 instead. The operator reported CPU-128F G2 in Bays A/B and PSU-32 G2 ×2 for CRAZY Node #1, but those values haven't been located in the file yet.
- Panel model strings exist in UTF-16, e.g. `RCP-1012E (12 Key LED-Panel 19" 1RU)`, `DCP-1016E …`, `RSP-1216HL …`, `DSP-1216HL …`.
- **Director has two features useful as ground truth:**
  1. List views can copy tables as **CSV** ("The following table is in 'comma-separated values' format…").
  2. A built-in **XML-RPC** automation interface (server and method registration strings). Test whether it answers queries while a configuration is open offline.
- The references to the `R2000 Cfg-File` string (VA `0x10bd620`) are at file offsets `0x700ec9` / `0x700eee`. That's the loader entry point to trace if needed.

---

## 5. Next steps on the Windows PC (in priority order)

1. **Get Director's view of CRAZY and the verified files.** Open each file and copy the Ports, Panels, Expansions, Cards / Nodes, Trunks and IFB lists as CSV, then diff them against our JSON output.
2. **Try the XML-RPC interface** against an offline configuration. If it works, script a full dump; that becomes the oracle.
3. **One-change test saves** to decode fields by diffing:
   - Key function and mode (Artist key flags) on one panel: every talk / listen / talk & listen × momentary / latching / auto combination, with labels named after the setting.
   - Expansion panels: a host plus expansions with IDs out of port order, to find the expansion link and ID field (not found yet; expansions don't store their host's object id).
   - Node ID: change one frame's node ID and diff, to identify the NN field.
   - CPU / PSU per frame, trunk phone numbers, IFB settings, conference talker / listener flags.
4. **Confirm the unconfirmed type-table entries and card classes** from Director's lists (CRAZY Node #3 cards 8 / 11 / 12 / 13 and the `0x505` / `0x506` ports).
5. **After each confirmed fact:** update both `web_extractor.html` and `riedel_formats.py` / `art_extractor.py`, re-run the regression check, and commit.
