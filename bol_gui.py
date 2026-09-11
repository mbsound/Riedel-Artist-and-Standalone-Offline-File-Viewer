#!/usr/bin/env python3
import sys
import os
import subprocess
import glob
from pathlib import Path
from bol_extractor import parse_bol_file, export
from art_extractor import is_art_file, parse_art_file, export_to_excel as export_art_to_excel

def run_applescript(script):
    p = subprocess.Popen(["osascript", "-e", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = p.communicate()
    return out.strip(), p.returncode

def choose_files_dialog():
    script = '''
    try
        set chosenFiles to choose file with prompt "Select one or more Bolero (.bol) or Artist (.Art) save files to convert:" of type {"bol", "art", "public.data"} with multiple selections allowed
        set posixPaths to ""
        repeat with f in chosenFiles
            set posixPaths to posixPaths & POSIX path of f & linefeed
        end repeat
        return posixPaths
    on error
        return ""
    end try
    '''
    out, code = run_applescript(script)
    if not out:
        return []
    return [p for p in out.splitlines() if p.strip()]

def show_notification(title, message):
    script = f'display notification "{message}" with title "{title}"'
    run_applescript(script)

def show_alert(title, message):
    script = f'display alert "{title}" message "{message}" buttons {{"OK"}} default button "OK"'
    run_applescript(script)

def main():
    # If files were passed via drag-and-drop or command line args:
    files = sys.argv[1:]

    # If no files passed directly, prompt user with macOS Finder File Chooser
    if not files:
        files = choose_files_dialog()

    if not files:
        sys.exit(0)

    # Process files
    bol_results = []
    art_results = []
    generated_files = []
    failed = []

    for f in files:
        if not os.path.isfile(f):
            continue
        try:
            if is_art_file(f):
                r = parse_art_file(f)
                art_results.append(r)
                base_dir = os.path.dirname(f) or "."
                base_name = os.path.splitext(os.path.basename(f))[0]
                out_path = os.path.join(base_dir, f"{base_name}.xlsx")
                export_art_to_excel(r, out_path)
                generated_files.append(out_path)
            else:
                r = parse_bol_file(f)
                bol_results.append(r)
                base_dir = os.path.dirname(r["filepath"]) or "."
                base_name = os.path.splitext(r["filename"])[0]
                out_path = os.path.join(base_dir, f"{base_name}.xlsx")
                export([r], out_path)
                generated_files.append(out_path)
        except Exception as e:
            failed.append((f, str(e)))

    if not generated_files:
        if failed:
            show_alert("Extraction Error", f"Failed to parse chosen file(s):\n{failed[0][1]}")
        sys.exit(1)

    # If single file selected, save .xlsx and open it
    if len(generated_files) == 1:
        out_path = generated_files[0]
        show_notification("Extraction Complete", f"Saved: {os.path.basename(out_path)}")
        subprocess.call(["open", out_path])
    else:
        # Multiple files: create individual workbooks for each
        if len(bol_results) > 1:
            first_dir = os.path.dirname(bol_results[0]["filepath"]) or "."
            combined_path = os.path.join(first_dir, "bolero_combined_export.xlsx")
            export(bol_results, combined_path)
            generated_files.append(combined_path)

        first_dir = os.path.dirname(generated_files[0]) or "."
        show_notification("Extraction Complete", f"Successfully converted {len(generated_files)} files.")
        subprocess.call(["open", first_dir])

if __name__ == "__main__":
    main()
