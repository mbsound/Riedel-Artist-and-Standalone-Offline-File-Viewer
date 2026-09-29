# Riedel Intercom Configuration Extractor

Converts **Riedel Artist** configuration saves (`.Art`, from Director) and **Bolero Standalone** saves (`.bol`) into Excel workbooks and JSON.

The Artist side is decoded from Director 8.9's own save and load code (see `docs/HANDOFF.md` and the comments in `artist_reader.py`). Every field the file stores has a name, or is marked as reserved or unused by Director.

---

## Tools

| File | What it does |
|---|---|
| `artist_reader.py` | Reads an `.Art` file into records with named fields, and has helpers that give values in Director's wording (ports, system settings, markers, audio patches, alarms, …). |
| `art_to_excel.py` | Artist workbook, built only from `artist_reader.py`. |
| `bol_faithful.py` | Reads a `.bol` file (all nine sections, each checked for exact byte consumption) and writes its workbook. |
| `export_tool.py` | One command line for both formats: Excel and/or JSON, a validation-only mode, and an Artist ↔ Bolero beltpack cross-check. |
| `build_web.py` | Builds `web_extractor_v2.html`: a browser page that runs the same Python modules through Pyodide. |
| `tools/` | Reverse-engineering helpers used to decode Director (Ghidra scripts, dialog/DDX maps, RTTI and property-name tools, port checks against Director's CSV export). |

## Usage

```
python export_tool.py <file or folder> [--format excel|json|all] [--out-dir DIR]
python export_tool.py <folder> --correlate        # match Bolero beltpacks between .Art and .bol saves
python export_tool.py <folder> --validate-only    # parse everything, write nothing
python art_to_excel.py [-o OUTPUT] FILE.Art ...   # Artist only; -h for help
```

Outputs are written next to the input unless `--out-dir` / `-o` is given.

JSON (`--format json`, or **Download JSON** on the web page) holds every decoded field: for `.Art`, the header, counts and all records; for `.bol`, every section with its named fields (raw byte values such as encryption keys as hex). The command line and the web page write the same document.

## Artist workbook (`art_to_excel.py`)

| Sheet | Contents |
|---|---|
| Summary | File, Director version, format version, record counts by type, count of objects changed in the last session |
| System | Director's system settings: general, panel defaults, call and key defaults, port settings, VoIP defaults, monitor defaults, trunking / Stage addresses, "allow more" options, setups |
| Key Light Colours | How a panel key lights up in each key state (Director's Marker definition table): priority, how long it stays lit, colours per panel series. Usually factory values. |
| Nodes, Fibre Links | Frames: address, ID, type, serial number, SOA / NOA, controllers, power supplies, error and relay alarm masks, logic destinations; the fibre links between them |
| Cards | One row per card, controller (CPU, or the two NICs on Artist 1024) and power supply, with its role; bay, model, name, port count, SIC port groups, allocated ports, network and sync settings (media IPs, DHCP, SIP port, DSCP, IGMP, speed, PTP, NMOS, DNS, Bolero discovery), device UUID |
| Ports | The columns of Director's Ports grid (checked with `tools/check_ports_csv.py`), media interface, phone book, scroll lists, type-specific settings (VoIP / SIP account, Bolero multicast, AES67 streams, panel UI), and panel settings for ports with keys |
| Keys | One row per panel, Bolero beltpack and expansion panel, with Label / Mode / Function columns for every key (bank 2 keys after bank 1) |
| Key Details | One row per key with all its options: subtitle, latching timeout, colours, monitoring, muted-key action, functions and details |
| Virtual Functions | Per panel and beltpack: the functions that act without a key press, under Always / On VOX / On Call |
| Functions | Every function (command) record: where it is assigned, target, priority, options |
| Conferences, Groups, IFBs | Members (with talk / listen / 2nd channel per conference member), colours, trunking, IFB endpoints, dim level, sidetone |
| Scroll Lists | Every entry: function, label, key mode, latching timeout, keypad shortcut |
| Audio Patches | Active crosspoints and muted outputs per panel |
| Logic & GPIO | Logic sources, destinations, gates, clocks, lines; GPIO inputs and outputs |
| Users | Accounts, passwords (courtesy lock-outs, shown in plain text), permissions |
| Other Objects | Phone books, shortlists, events, scheduled tasks, NSA and VoIP devices |
| All Records | Every record and every decoded field (JSON), so nothing is lost |

Rows highlighted in yellow are objects created or changed in the editing session that produced the save. Director marks every edited object and clears the marks on each load and save.

## Bolero workbook (`bol_faithful.py`)

Summary, Network, Partylines, Audio Channels, Profiles, Beltpacks, Antennas, Audio Devices, GPIO Triggers.

## Documentation

- `docs/HANDOFF.md`: decoding status, methods and the Director functions each field comes from.
- Research material derived from Riedel software (Director dialog / property / class-code extracts, decompiled
  Bolero firmware, Director exports) is not part of the repository. The tools in `tools/` and
  `docs/firmware_decomp/` regenerate it locally from your own copies of Director and the Bolero firmware.

## License

MIT, see [LICENSE](LICENSE).
