#!/usr/bin/env python3
"""
Riedel Configuration Exporter & Validation CLI (export_tool.py)
==============================================================
Unified batch export and validation runner for both Riedel Director (.Art)
save files and Riedel Bolero Standalone (.bol) save files.

Usage:
    python export_tool.py [path] [--format excel|json|all] [--out-dir DIR] [--validate-only]

Features:
    - Auto-detects Artist (.Art) and Bolero (.bol) save formats by signature.
    - Exports rich multi-sheet Excel workbooks matching Director and Bolero UI.
    - Optionally exports JSON representation of configuration data.
    - 100% strict verification gate: verifies zero-residual byte exact consumption.
"""

import sys
import os
import glob
import time
import json
import zlib
import struct
import pathlib
import argparse

import artist_reader as A
import art_to_excel as ArtExcel

try:
    import bol_faithful as B
    HAS_BOLERO = True
except ImportError:
    HAS_BOLERO = False


def detect_file_type(file_bytes, filename=""):
    """Detect whether file is Artist (.Art), Bolero (.bol), or unknown."""
    if file_bytes.startswith(b'\xff\xfe\xff\x0e') or b'R2000 Cfg-File' in file_bytes[:64] or filename.lower().endswith('.art'):
        return 'artist'
    if (len(file_bytes) > 7 and file_bytes[2] == 0x02) or filename.lower().endswith('.bol'):
        return 'bolero'
    return 'unknown'


def export_artist_file(path, out_dir=None, fmt='excel', validate_only=False):
    """Process an Artist .Art save file."""
    path = pathlib.Path(path)
    t0 = time.time()
    data = path.read_bytes()
    h, recs = A.parse_art(data)
    byid = {r['id']: r for r in recs}

    nodes = [r for r in recs if r['class'] == 3]          # CPhysNode frames
    ports = [r for r in recs if r['class'] in A.PORT_TYPE_NAMES]
    keys = [r for r in recs if r['class'] == 9 and r.get('commands')]
    confs = [r for r in recs if r['class'] == 0x12]
    groups = [r for r in recs if r['class'] == 0x11]
    ifbs = [r for r in recs if r['class'] == 0x66]

    metrics = {
        'type': 'Artist .Art',
        'records': len(recs),
        'nodes': len(nodes),
        'ports': len(ports),
        'keys': len(keys),
        'confs': len(confs),
        'groups': len(groups),
        'ifbs': len(ifbs),
        'elapsed_s': round(time.time() - t0, 3)
    }

    if validate_only:
        return True, metrics, []

    created_files = []
    base_name = path.stem
    target_dir = pathlib.Path(out_dir) if out_dir else path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    # Excel export
    if fmt in ('excel', 'all'):
        xlsx_path = target_dir / f"{base_name}.xlsx"
        ArtExcel.export_art_to_excel(path, output_path=xlsx_path)
        created_files.append(str(xlsx_path))

    # JSON export
    if fmt in ('json', 'all'):
        json_path = target_dir / f"{base_name}.json"
        export_data = {
            'header': h,
            'counts': {
                'records': len(recs),
                'nodes': len(nodes),
                'ports': len(ports),
                'active_keys': len(keys),
                'conferences': len(confs),
                'groups': len(groups),
                'ifbs': len(ifbs),
            },
            'records': recs
        }
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, default=str)
        created_files.append(str(json_path))

    return True, metrics, created_files


def export_bolero_file(path, out_dir=None, fmt='excel', validate_only=False):
    """Process a Bolero .bol save file."""
    path = pathlib.Path(path)
    t0 = time.time()
    if not HAS_BOLERO:
        raise RuntimeError("bol_faithful.py not available in environment.")

    res = B.parse_file(str(path))

    net_data = res.get('network', {})
    net_name = net_data.get('show_name') or net_data.get('netName') or 'Unknown'
    pls = res.get('partylines', {}).get('partylines', []) if isinstance(res.get('partylines'), dict) else res.get('partylines', [])
    profs = res.get('profiles', {}).get('profiles', []) if isinstance(res.get('profiles'), dict) else res.get('profiles', [])
    bps = res.get('beltpacks', {}).get('beltpacks', []) if isinstance(res.get('beltpacks'), dict) else res.get('beltpacks', [])
    ants = res.get('antennas', {}).get('nodes', []) if isinstance(res.get('antennas'), dict) else res.get('antennas', [])
    devs = res.get('audio_devices', {}).get('devices', []) if isinstance(res.get('audio_devices'), dict) else res.get('audio_devices', [])
    chs = res.get('audio_channels', {}).get('channels', []) if isinstance(res.get('audio_channels'), dict) else res.get('audio_channels', [])
    trigs = res.get('gpio', {}).get('triggerConfigs', []) if isinstance(res.get('gpio'), dict) else []

    metrics = {
        'type': 'Bolero .bol',
        'net_name': net_name,
        'partylines': len(pls),
        'profiles': len(profs),
        'beltpacks': len(bps),
        'antennas': len(ants),
        'devices': len(devs),
        'channels': len(chs),
        'triggers': len(trigs),
        'elapsed_s': round(time.time() - t0, 3)
    }

    if validate_only:
        return True, metrics, []

    created_files = []
    base_name = path.stem
    target_dir = pathlib.Path(out_dir) if out_dir else path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    # Excel export
    if fmt in ('excel', 'all'):
        xlsx_path = target_dir / f"{base_name}.xlsx"
        B.export_to_excel(str(path), str(xlsx_path))   # export_to_excel parses the file itself
        created_files.append(str(xlsx_path))

    # JSON export
    if fmt in ('json', 'all'):
        json_path = target_dir / f"{base_name}_bolero.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(res, f, indent=2, default=str)
        created_files.append(str(json_path))

    return True, metrics, created_files


def correlate_artist_and_bolero(files, out_dir=None, fmt='excel'):
    """
    Cross-references Bolero beltpack assignments across Artist (.Art) save files
    and Bolero (.bol) save files. Analyzes User IDs, label mappings, and IP multicasts.
    """
    files = [pathlib.Path(f) for f in files]
    artist_files = [f for f in files if f.suffix.lower() == '.art']
    bolero_files = [f for f in files if f.suffix.lower() == '.bol']

    if not artist_files or not bolero_files or not HAS_BOLERO:
        return None

    print("\n" + "=" * 80)
    print(" BOLERO + ARTIST CROSS-CORRELATION AUDIT")
    print("=" * 80)

    # Collect all Artist Bolero beltpack ports
    artist_bps = {}
    for af in artist_files:
        try:
            h, recs = A.parse_art(af.read_bytes())
            b_ports = [r for r in recs if r['class'] == 0x440]
            entries = []
            for p in b_ports:
                om2 = p.get('output_media_2', {})
                entries.append({
                    'label': p.get('name', ''),
                    'long_name': p.get('port_str', ''),
                    'user_id': om2.get('bolero_user_id'),
                    'multicast': om2.get('multicast'),
                    'multicast_port': om2.get('multicast_port', 5004),
                    'port_to_bolero': om2.get('multicast_port_to_bolero', 42000),
                })
            artist_bps[af.name] = entries
        except Exception:
            continue

    # Collect all Bolero Standalone beltpacks
    bolero_nets = {}
    for bf in bolero_files:
        try:
            res = B.parse_file(str(bf))
            net_name = res.get('network', {}).get('show_name') or res.get('network', {}).get('netName') or bf.stem
            raw_bps = res.get('beltpacks', {}).get('beltpacks', []) if isinstance(res.get('beltpacks'), dict) else res.get('beltpacks', [])
            bps = []
            for b in raw_bps:
                cfg = b.get('config', {})
                art = cfg.get('artist', {})
                bps.append({
                    'id': cfg.get('id'),
                    'name': cfg.get('name', ''),
                    'artist_name': art.get('name', ''),
                })
            bolero_nets[bf.name] = {
                'net_name': net_name,
                'beltpacks': bps,
            }
        except Exception:
            continue

    total_art_bps = sum(len(v) for v in artist_bps.values())
    total_bol_bps = sum(len(v['beltpacks']) for v in bolero_nets.values())
    print(f" Analyzed {len(artist_bps)} Artist files ({total_art_bps} Bolero ports configured)")
    print(f" Analyzed {len(bolero_nets)} Bolero files ({total_bol_bps} Standalone beltpacks configured)")
    print("-" * 80)

    correlation_results = []

    for a_name, a_list in artist_bps.items():
        if not a_list:
            continue
        a_uids = {b['user_id']: b for b in a_list if b['user_id'] is not None}
        a_labels = {b['label'].strip().lower(): b for b in a_list if b['label']}

        for b_name, b_data in bolero_nets.items():
            b_list = b_data['beltpacks']
            matched_uids = 0
            matched_labels = 0
            matches = []

            for bp in b_list:
                bid = bp['id']
                bname = bp['name'].strip()
                art_name = bp['artist_name'].strip().strip('<>')

                m_uid = a_uids.get(bid)
                m_label = a_labels.get(bname.lower()) or (a_labels.get(art_name.lower()) if art_name else None)

                if m_uid or m_label:
                    if m_uid and m_label and m_uid == m_label:
                        matches.append({'bolero_bp': bname, 'id': bid, 'artist_label': m_uid['label'], 'match_type': 'EXACT (ID & Name)'})
                        matched_uids += 1
                        matched_labels += 1
                    elif m_uid:
                        matches.append({'bolero_bp': bname, 'id': bid, 'artist_label': m_uid['label'], 'match_type': 'User ID match'})
                        matched_uids += 1
                    elif m_label:
                        matches.append({'bolero_bp': bname, 'id': bid, 'artist_label': m_label['label'], 'match_type': 'Name match'})
                        matched_labels += 1

            if matches:
                pct = round(100.0 * len(matches) / max(len(b_list), 1), 1)
                print(f" [CORRELATION MATCH] {a_name} <-> {b_name} ({b_data['net_name']})")
                print(f"   -> Matched {len(matches)}/{len(b_list)} BPs ({pct}%) | {matched_uids} by User ID, {matched_labels} by Label")
                correlation_results.append({
                    'artist_file': a_name,
                    'bolero_file': b_name,
                    'net_name': b_data['net_name'],
                    'matched_count': len(matches),
                    'total_bolero_bps': len(b_list),
                    'matches': matches
                })

    if not correlation_results:
        print(" No direct cross-file beltpack overlaps detected across different shows.")
    print("=" * 80)

    # Save JSON report if format requested
    if correlation_results and fmt in ('json', 'all'):
        target_dir = pathlib.Path(out_dir) if out_dir else pathlib.Path('.')
        report_path = target_dir / "bolero_artist_correlation_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(correlation_results, f, indent=2)
        print(f" Correlation report written to: {report_path}")

    return correlation_results


def collect_files(target_path):
    """Collect all .Art and .bol files from target path (file or dir)."""
    p = pathlib.Path(target_path)
    if not p.exists():
        raise FileNotFoundError(f"Path does not exist: {target_path}")

    if p.is_file():
        return [p]

    collected = []
    for ext in ('*.Art', '*.art', '*.bol', '*.BOL'):
        collected.extend(p.glob(f"**/{ext}"))
    return sorted(set(collected))


def main():
    parser = argparse.ArgumentParser(description="Unified Riedel Artist (.Art) & Bolero (.bol) Exporter & Validator")
    parser.add_argument('path', nargs='?', default='..', help="Input file or folder to search (default: '..')")
    parser.add_argument('--format', choices=['excel', 'json', 'all'], default='excel', help="Export format (default: excel)")
    parser.add_argument('--out-dir', default=None, help="Output directory for generated files")
    parser.add_argument('--validate-only', action='store_true', help="Only validate files without writing outputs")
    parser.add_argument('--correlate', action='store_true', help="Run Bolero + Artist beltpack cross-correlation audit")
    parser.add_argument('--quiet', action='store_true', help="Minimal output logging")

    args = parser.parse_args()

    files = collect_files(args.path)
    if not files:
        print(f"No .Art or .bol files found in: {args.path}")
        return 0

    print("=" * 80)
    print(" RIEDEL CONFIGURATION EXPORTER & VALIDATOR")
    print(f" Target Path:    {args.path}")
    print(f" Total Files:    {len(files)}")
    print(f" Output Format:  {args.format}")
    print(f" Mode:           {'Validation Only' if args.validate_only else 'Export & Verification'}")
    print("=" * 80)

    success_count = 0
    fail_count = 0

    for idx, f in enumerate(files, 1):
        rel_name = f.name
        try:
            b = f.read_bytes()
            ftype = detect_file_type(b, rel_name)

            if ftype == 'artist':
                ok, m, out_files = export_artist_file(f, out_dir=args.out_dir, fmt=args.format, validate_only=args.validate_only)
                print(f"[{idx:2d}/{len(files)}] [OK] {rel_name:<36} (Artist) -> {m['records']} recs | {m['ports']} ports | {m['keys']} keys | {m['confs']} confs ({m['elapsed_s']}s)")
                success_count += 1
            elif ftype == 'bolero':
                ok, m, out_files = export_bolero_file(f, out_dir=args.out_dir, fmt=args.format, validate_only=args.validate_only)
                print(f"[{idx:2d}/{len(files)}] [OK] {rel_name:<36} (Bolero) -> Net: '{m['net_name']}' | {m['beltpacks']} BPs | {m['partylines']} PLs | {m['profiles']} profs ({m['elapsed_s']}s)")
                success_count += 1
            else:
                print(f"[{idx:2d}/{len(files)}] [SKIP] {rel_name:<34} (Unrecognized format signature)")
        except Exception as e:
            print(f"[{idx:2d}/{len(files)}] [FAIL] {rel_name:<34} ERROR: {e}")
            fail_count += 1

    print("-" * 80)
    print(f"Summary: {success_count} succeeded, {fail_count} failed out of {len(files)} total files.")
    print("=" * 80)

    if args.correlate:
        correlate_artist_and_bolero(files, out_dir=args.out_dir, fmt=args.format)

    return 0 if fail_count == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
