# Bolero Standalone Configuration Extractor

A specialized extraction tool for **Bolero Standalone** backup save files (`.bol`). Converts uncompressed binary configuration dumps into structured, color-coded Microsoft Excel (`.xlsx`) workbooks.

Developed for intercom engineers, production crews, and audio systems technicians to quickly audit, document, and cross-reference Bolero show configurations.

---

## Available Formats & Distribution

### 1. Standalone Native macOS Application (`.app`)
**Zero dependencies required.** Built specifically for macOS.
- **Download:** Download `Bolero-File-Extractor-macOS.zip` directly from this repository (or run `pyinstaller "Bolero File Extractor.spec"` to build from source).
- **How to use:**
  1. Unzip and double-click `Bolero File Extractor.app`.
  2. A native macOS file dialog appears asking you to choose one or more `.bol` files (or drag & drop `.bol` files directly onto the app icon).
  3. The app parses the file, generates the `.xlsx` right next to your `.bol` file, and automatically opens it in Microsoft Excel.

### 2. Browser-Based Web Extractor (`web_extractor.html`)
**Zero install, runs on any platform (Mac, Windows, Linux, iPad).**
- **Location:** `web_extractor.html`
- **How to use:**
  1. Double-click `web_extractor.html` to open it in any modern browser (Safari, Chrome, Firefox, Edge).
  2. Drag and drop any `.bol` file(s) into the browser window.
  3. Decompression and binary decoding run 100% locally in client-side JavaScript. Click **Download Excel (.xlsx)** to save. No server uploads; 100% private.

### 3. Python CLI Script (`bol_extractor.py`)
For headless batch processing, pipelines, and terminal workflows.
- **Requirements:** Python 3.9+ (`openpyxl`)
- **Usage:**
  ```bash
  # Convert a single file:
  python3 bol_extractor.py -s "show_backup.bol"

  # Batch convert all .bol files in current folder into individual Excel files:
  python3 bol_extractor.py -s *.bol

  # Combine all .bol files into a single multi-tab workbook:
  python3 bol_extractor.py -o bolero_export.xlsx
  ```

---

## Extracted Excel Workbook Structure

Every generated workbook contains six dedicated tabs:

1. **`Summary`**: Project metadata, file size, conference count, profile count, registered beltpack totals, active antennas, and NSA hardware devices.
2. **`Key Map`**: Complete 27-column layout displaying every registered beltpack in the master inventory with:
   - **RF Status**: `Online` (active in live DECT session cache) vs. `Offline` (persistent inventory unit powered down).
   - **Hardware Device Serial Number**: E.g., `68:fe:0e:2a`.
   - **Keys 1 through 6 & Key 7 (REPLY)**: Dedicated columns for **Target / Conference**, **Function** (`Talk`, `Listen`, `Talk & Listen`, `Talk-Always Listen`), and **Action Mode** (`Auto`, `Momentary`, `Latching`).
   - **Visual Color Coding**: Conferences (Soft Blue), Audio/NSA Talk (Amber), Audio/NSA Listen (Sage Green), P2P (Lavender), Dynamic Reply (Cool Grey).
3. **`Profiles`**: Complete 23-column key mapping layout for all system profiles with assigned beltpack cross-references.
4. **`Antennas`**: Active radio transceivers with Network Space Sync ID, Designated Primary and Secondary Master Antenna IDs, Net Indices, Hardware Serials, and Radio Master Priorities (`Normal / Auto`).
5. **`Conferences`**: Full partyline matrix showing cross-references for which profiles, beltpacks, and audio channels are attached to each conference.
6. **`Audio Device/NSA`**: NSA hardware channel routing detailing physical channels (Channels 1–6 across NSA 1 & NSA 2), interface types (`4-Wire` vs `4-Wire Split Input/Output`), attached conferences, and GPIO/Triggers.

---

## License & Attribution
This project is open-source and licensed under the [MIT License](LICENSE).

Designed for Bolero Standalone environments. Parsed from uncompressed binary structures without third-party vendor proprietary libraries.
