# Riedel Intercom Configuration Extractor
### Bolero Standalone & Riedel Artist Matrix Configuration Extractor

A universal, standalone extraction tool for **Riedel Artist Matrix** configuration dumps (`.art` / `.Art`) and **Bolero Standalone** backup save files (`.bol`). Converts uncompressed binary configuration dumps into structured, professionally formatted, color-coded Microsoft Excel (`.xlsx`) workbooks and comprehensive machine-readable JSON (`.json`) files.

Designed for intercom engineers, communications leads, broadcast sound engineers, and audio systems technicians to instantly audit, document, print, cross-reference, and programmatically query intercom show configurations.

---

## Supported Hardware & File Formats

### Riedel Artist Matrix Systems (`.art`, `.Art`)
Full parsing and decoding support for single-frame and multi-node fiber ring topology networks across all Artist mainframe models:
- **Artist 32**: Mainframe systems, AIO-108 analog 4-wire client cards, RIF radio interfaces, and GPIO-116 relay keying.
- **Artist 64**: Mainframe systems, AES67 audio cards, MADI digital cards, Dante cards, and VoIP trunk cards.
- **Artist 128**: Dual-controller redundant systems with multi-card bays and tie-lines.
- **Artist 1024**: Next-generation high-density intercom routing cores (UIC, SMPTE 2110-30 / AES67 multi-bay streams).
- **Physical Keypanels & Beltpacks**: RSP-1232HL (32-key), RSP-1216HL (16-key), DSP-2312 (12-key), RSP-2318 (18-key), and Bolero Wireless Beltpacks (6-key with OLED display).

### Bolero Standalone Systems (`.bol`)
Native zlib payload decompression and structure decoding for standalone antenna-based wireless systems:
- Registered beltpacks, persistent offline inventories, and active RF sessions.
- System profiles, antenna network spaces (sync masters/redundancies), partyline conferences, NSA-002A audio interfaces, and Punqtum audio endpoints.

---

## File Version Detection & Approved Versions (Web Converter)

Every file is fingerprinted before it is parsed, and the result is shown on the file card, in the Excel **Summary** sheet, and in the JSON `format_info` object.

| Format | Where the version lives | Fingerprint |
|---|---|---|
| Artist `.art` | Header: UTF-16LE `R2000 Cfg-File`, u32 schema revision at `0x20`, then a length-prefixed `Director version X.Y.Dn-B.hash` string | Director build + schema revision (e.g. `8.9.D2-14` / `0x580`) |
| Bolero `.bol` | Container byte at offset 2, then inside the zlib payload a u16 NetConfig version and a u16 version per section (network, partylines, profiles, beltpacks, antennas, …) | `container/netconfig/section versions` (e.g. `2/6/10.2.17.19.1.1.6.6.60000`) |

- **Approved** fingerprints are listed in `APPROVED_VERSIONS` in `web_extractor.html` and `riedel_formats.py` (keep the two in sync). Only builds that have been checked against real files are on the list.
- **Unapproved** files still parse, with the nearest older rule set from `ARTIST_RULE_PROFILES`. They are marked **Unverified** with a warning that the output might not be trusted: on the file card, in the Excel Summary sheet, in the JSON, in the CLI output and as a macOS app alert. Bolero warnings name the section whose version changed.
- **Non-configuration files** (for example a JSON export renamed to `.art`) are rejected instead of being parsed into empty sheets.
- **To approve a new version:** load a real file, spot-check each sheet against Director or the Bolero web UI, then add its fingerprint to `APPROVED_VERSIONS` in both files.

Known version differences between Director 8.6 and 8.9: key-assignment records use type code `0x4000` in 8.6 and `0x5000` in 8.9, and 8.9 writes 4 extra bytes after each conference long name. Everything else decoded so far uses the same layout in both.

### What is decoded from the file, and what is not yet

The parsers read these structures directly, with no show-specific values:

| | Decoded | Not decoded yet (shown as "Not decoded", "—" or "inferred") |
|---|---|---|
| **Bolero** | Show name, partylines, profiles and their keys, beltpacks (hardware ID, user, beltpack ID, keys), P2P targets, named antennas, audio devices and channels, GPIO triggers, save date and network ID | Live RF / online status (a save file does not contain it), net masters |
| **Artist** | Director version and schema, endpoints (name, alias, slot.port, type), panel and beltpack key labels, long names and target type (conference, point-to-point, group, reply), conferences with member endpoints, dynamic conferences, trunk lines, Bolero AES67 multicast address and RTP port, frame model (code 3 = Artist 32, 9 = Artist 1024; 4 and 5 unconfirmed) | Multicast addresses of Dante / AES67 tie ports (the file references their flows by UUID), key talk/listen function and mode (auto/latching/momentary), conference talker/listener split, groups (talk groups), IFBs, node numbers (read from frame names), node assignment when the port name does not include the node, controllers, PSUs, licences; card models are inferred from port types |

---

## Available Distributions

### 1. Standalone Native macOS Application (`.app`)
Zero dependencies required. Built as a universal macOS application bundle.
- **Download:** Unzip `Bolero-File-Extractor-macOS.zip` directly from this repository (or compile from source using `pyinstaller "Bolero File Extractor.spec"`).
- **Usage:**
  1. Double-click `Bolero File Extractor.app`.
  2. Select any `.bol` or `.art` configuration file(s) via the native macOS file selector, or drag and drop files onto the application icon.
  3. The application automatically detects the file type, extracts all parameters, creates matching `.xlsx` and optional `.json` files in the file's folder, and opens the workbook in your spreadsheet viewer.

### 2. Browser-Based Web Converter (`web_extractor.html`)
Zero installation required. Runs directly in any web browser on macOS, Windows, Linux, or iPadOS.
- **Location:** `web_extractor.html`
- **Usage:**
  1. Open `web_extractor.html` in Safari, Chrome, Edge, or Firefox.
  2. Drag and drop any `.bol` or `.art` file(s) into the browser window.
  3. All binary decoding, zlib inflation, and spreadsheet generation execute 100% client-side via JavaScript. No data is sent over the internet or uploaded to any external server.
  4. Click **Download Excel (.xlsx)** or **Download JSON (.json)** on any file card to save individual configurations.
  5. When multiple files are processed, use **Download Combined Excel (.xlsx)** or **Download All JSON (.json)** to download complete batch archives.

### 3. Python CLI Tools (`art_extractor.py`, `bol_extractor.py`, `bol_gui.py`)
For headless server environments, automated show deployments, and terminal pipelines.
- **Requirements:** Python 3.9+ with `openpyxl`
- **Usage:**
  ```bash
  # Convert a Riedel Artist Matrix file to Excel and JSON:
  python3 art_extractor.py "show_backup.art" --json

  # Convert a Bolero Standalone backup file to Excel and JSON:
  python3 bol_extractor.py -s "backup_config.bol" --json

  # Process both formats interchangeably via GUI / script:
  python3 bol_gui.py "show_file.art" "show_file.bol"
  ```

---

## Extracted Excel Workbook Structures

### Riedel Artist (`.art`) Workbook Structure
Every generated Artist workbook contains up to 12 specialized sheets (see the table above for which fields are decoded):

1. **Summary**: Frame metadata, Director software build, system signature, ring topology, and equipment inventory tallies.
2. **Nodes & Topology**: Master node, breakout frames, routing cores, control IP addresses, subnets, gateways, service IPs, and fiber ring loop status.
3. **Cards & Slots**: Physical hardware inventory detailing slot assignments, card types (AES67, Dante, MADI, AIO, GPIO), primary/secondary IP addressing, and network gateways.
4. **IP Trunks**: System VoIP digital trunks, short IDs, target remote IP destinations, and transmission protocols.
5. **Bolero**: Master wireless beltpack table (IDs 1 through 80+), multicast IP addresses, matrix ports, assigned users, and 6 physical keys plus reply key with targets, functions, and action modes.
6. **Panels & Bolero**: Master 55-column keypanel overview covering RSP-1232HL, RSP-1216HL, DSP-2312, and beltpack endpoints. Includes slot/port, device name, hardware type, IP address, display label, assigned user, and 16 individual key blocks (Target, Function, Action Mode).
7. **Ports**: Comprehensive matrix port roster detailing every Node, Card, Slot, Port Number, Status (`Enabled` vs `Spare / Inactive`), Port Name, Signal Type, 4-Wire Audio Mode, and Connected Conference(s) / IFB Routing.
8. **Conferences**: Clear distinction between Groups (1-to-many multi-destination talk paths with explicit destination port rosters) and Conferences (many-to-many partylines with talker and listener endpoint lists).
9. **IFB Routing**: Complete IFB foldback matrix with all 8 operational routing parameters: IFB Name, Input Port, Mix-Minus Return Port, Output Port, Dim Level (dB), Channel Number, Key Label, and Input/Output Gains.
10. **Logic & Flashes**: Logic functions, visual call signals, and GPI triggers.
11. **Users & Access**: System operator accounts, user profile names, and administrative permission levels.
12. **Name Overwrites**: Active custom display aliases mapped against original internal system names.

### Bolero Standalone (`.bol`) Workbook Structure
Every generated Bolero Standalone workbook contains 6 specialized sheets:

1. **Summary**: Show name, conference totals, profile counts, registered beltpack totals, active transceiver counts, and network interface interfaces.
2. **Key Map**: Master beltpack table (27 columns) detailing RF status (`Online` vs `Offline`), device serial numbers, and Keys 1 through 6 plus Key 7 (`<REPLY>`) with visual color-coded functional blocks.
3. **Profiles**: System profile templates with assigned key definitions and attached beltpack listings.
4. **Antennas**: Transceiver hardware serial numbers, network space sync IDs, master antenna designations, and radio priorities.
5. **Conferences**: Partyline conference matrix with cross-referenced member profiles, beltpacks, and audio interfaces.
6. **Audio Devices**: Physical channel routing across NSA-002A interfaces and Punqtum stations, interface types (4-Wire vs 4-Wire Split), attached conferences, and GPIO triggers.

---

## License & Attribution
This project is open-source and licensed under the [MIT License](LICENSE).
Built for Riedel intercom environments without proprietary third-party dependencies.
