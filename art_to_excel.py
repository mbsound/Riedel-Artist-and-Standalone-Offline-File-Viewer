#!/usr/bin/env python3
"""
Riedel Director .Art Configuration to Excel Exporter
====================================================
Transforms Riedel Director .Art save files into a complete, professional,
multi-sheet Excel workbook matching Director's layout, nomenclature, and exact
ground-truth decoded values.

Directly driven by artist_reader.py.
"""

import sys
import os
import glob
import pathlib
from collections import defaultdict

import artist_reader as A

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
except ImportError:
    print("ERROR: openpyxl is required. Run: pip install openpyxl")
    sys.exit(1)

# Color Palette
C = {
    'navy':        '1F3864',
    'blue':        '2E5FA3',
    'light_blue':  'D9E1F2',
    'teal':        '1B6B6B',
    'light_teal':  'D4EEEE',
    'slate':       '4A4A4A',
    'row_alt':     'F4F7FC',
    'row_white':   'FFFFFF',
    'green':       '1E6B1E',
    'light_green': 'E2EFDA',
    'amber':       'B25900',
    'light_amber': 'FFF2CC',
    'purple':      '5B3A8A',
    'light_purple':'E8E0F0',
    'border':      'D9D9D9',
}


def clean_val(v):
    if v is None:
        return ""
    return ILLEGAL_CHARACTERS_RE.sub("", str(v))


def fill(hex_c):
    return PatternFill(start_color=hex_c, end_color=hex_c, fill_type="solid")


def bdr(style="thin", color=C['border']):
    s = Side(style=style, color=color)
    return Border(left=s, right=s, top=s, bottom=s)


def title_banner(ws, title, subtitle, max_col=8):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max_col)
    c1 = ws.cell(row=1, column=1, value=clean_val(title))
    c1.font = Font(name="Calibri", size=13, bold=True, color="FFFFFF")
    c1.fill = fill(C['navy'])
    c1.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 28

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max_col)
    c2 = ws.cell(row=2, column=1, value=clean_val(subtitle))
    c2.font = Font(name="Calibri", size=9, italic=True, color="FFFFFF")
    c2.fill = fill(C['blue'])
    c2.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[2].height = 18


def header_row(ws, row_idx, headers, bg=C['slate'], fg="FFFFFF"):
    ws.row_dimensions[row_idx].height = 24
    for col_idx, h in enumerate(headers, 1):
        c = ws.cell(row=row_idx, column=col_idx, value=clean_val(h))
        c.font = Font(name="Calibri", size=10, bold=True, color=fg)
        c.fill = fill(bg)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = bdr()


def write_cell(ws, row_idx, col_idx, val, bg=None, fg="000000", bold=False, align="left", size=9):
    c = ws.cell(row=row_idx, column=col_idx, value=clean_val(val))
    c.font = Font(name="Calibri", size=size, bold=bold, color=fg)
    if bg:
        c.fill = fill(bg)
    c.alignment = Alignment(horizontal=align, vertical="center")
    c.border = bdr()
    return c


def auto_width(ws, extra=3, max_w=65):
    for col in ws.columns:
        ltr = get_column_letter(col[0].column)
        w = max((len(str(c.value or "")) for c in col), default=0)
        ws.column_dimensions[ltr].width = min(max(w + extra, 10), max_w)
    ws.views.sheetView[0].showGridLines = True


def format_command(cmd, byid):
    if not cmd:
        return 'Empty', '', ''
    cls = cmd.get('class', 0)
    prio = cmd.get('priority', '')
    if cls == 0x13:  # Call to Port
        target = byid.get(cmd.get('target'))
        name = target.get('port_str') or target.get('name') if target else f"Port ID {cmd.get('target')}"
        label = target.get('name', '') if target else ''
        return 'Call to Port', name, prio
    elif cls == 0x14:  # Listen to Port
        target = byid.get(cmd.get('target'))
        name = target.get('port_str') or target.get('name') if target else f"Port ID {cmd.get('target')}"
        label = target.get('name', '') if target else ''
        return 'Listen to Port', name, prio
    elif cls == 0x16:  # Conference
        conf = byid.get(cmd.get('conference'))
        name = conf.get('long_name') or conf.get('label') if conf else f"Conf ID {cmd.get('conference')}"
        return 'Conference', name, prio
    elif cls in (0x17, 0x12):  # Group
        grp = byid.get(cmd.get('group'))
        name = grp.get('long_name') or grp.get('label') if grp else f"Group ID {cmd.get('group')}"
        return 'Group', name, prio
    elif cls == 0x18:  # Reply
        return 'Reply', '<REPLY>', prio
    elif cls == 0x67:  # Call to IFB
        ifb = byid.get(cmd.get('ifb'))
        name = ifb.get('long_name') or ifb.get('label') if ifb else f"IFB ID {cmd.get('ifb')}"
        return 'Call to IFB', name, prio
    elif cls == 0x15:  # Route Audio
        src = byid.get(cmd.get('source'))
        dst = byid.get(cmd.get('dest'))
        src_name = src.get('name') if src else str(cmd.get('source'))
        dst_name = dst.get('name') if dst else str(cmd.get('dest'))
        return 'Route Audio', f"{src_name} -> {dst_name}", prio
    elif cls == 0x44:  # Logic
        log = byid.get(cmd.get('logic'))
        name = log.get('name') if log else cmd.get('cmd_name', '')
        return 'Logic', name or f"Logic ID {cmd.get('logic')}", prio
    elif cls == 0x70:  # Audio Patch
        return 'Audio Patch', cmd.get('cmd_name', 'Audio Patch'), prio
    else:
        return f"Cmd 0x{cls:02x}", cmd.get('cmd_name', ''), prio


# ── Sheet 1: Summary ─────────────────────────────────────────────────────────
def build_summary_sheet(wb, h, recs, byid, filepath):
    ws = wb.create_sheet(title="Summary")
    net = next((r for r in recs if r['class'] == 2), {})
    net_gen = A.net_general(net)
    sys_name = net_gen.get('System name') or pathlib.Path(filepath).stem
    director_ver = h.get('creator', 'Unknown')
    schema_hex = f"0x{h.get('version', 0):03x}"

    title_banner(ws, f"Artist Matrix System Summary: {sys_name}",
                 f"{director_ver}  |  File: {pathlib.Path(filepath).name}", max_col=4)

    headers = ["Category", "Parameter / System Item", "Decoded Value", "Technical Description"]
    header_row(ws, 4, headers, bg=C['navy'])

    nodes = [r for r in recs if r['class'] == 3]
    ports = [r for r in recs if r['class'] in A.PORT_TYPE_NAMES]
    keys = [r for r in recs if r['class'] == 9]
    keys_configured = [k for k in keys if k.get('commands')]
    confs = [r for r in recs if r['class'] == 0x012]
    groups = [r for r in recs if r['class'] == 0x011]
    ifbs = [r for r in recs if r['class'] == 0x066]
    patches = [r for r in recs if r['class'] == 0x019]
    users = [r for r in recs if r['class'] == 0x023]
    boleros = [p for p in ports if p['class'] == 0x440]
    panels = [p for p in ports if p['class'] not in (0x440, 0x401, 0x402, 0x403, 0x438, 0x439, 0x441, 0x442, 0x445, 0x502, 0x508, 0x513, 0x514, 0x515)]
    ties = [p for p in ports if p['class'] in (0x401, 0x402, 0x403, 0x438, 0x439, 0x441, 0x442)]
    trunks = [p for p in ports if p['class'] in (0x445, 0x502, 0x508)]
    expansions = [r for r in recs if r['class'] in A.EXPANSION_SLOTS or r['class'] == 0x507]

    rows = [
        ("System Metadata", "Director Software Release", director_ver, "Exact Riedel Director binary release"),
        ("System Metadata", "System Name", sys_name, "Configured matrix system name in CPhysNet"),
        ("System Metadata", "Net Number", net_gen.get('Net number', 0), "Inter-matrix network identification number"),
        ("System Metadata", "Archive Schema Revision", schema_hex, "Director save serialization schema version"),
        ("Network Topology", "Matrix Nodes (Frames)", len(nodes), "Independent hardware frames in network"),
        ("Network Topology", "Fibre Links (CPhysLWL)", len([r for r in recs if r['class'] == 5]), "Dual-ring inter-frame optical connections"),
        ("Matrix Endpoints", "Total Physical & Virtual Ports", len(ports), "Total matrix ports across all frames & cards"),
        ("Matrix Endpoints", "Hardware Keypanels (Master Stations)", len(panels), "Physical SmartPanels and master stations"),
        ("Matrix Endpoints", "Expansion Panels (Modules)", len(expansions), "Hardware extension modules linked to keypanels"),
        ("Matrix Endpoints", "Bolero Wireless Beltpacks", len(boleros), "Active Bolero DECT wireless beltpack endpoints"),
        ("Matrix Endpoints", "Audio Tie Lines & 4-Wires", len(ties), "Analogue and digital audio matrix tie lines"),
        ("Matrix Endpoints", "Digital IP Trunks & VoIP", len(trunks), "AES67 trunklines, VoIP connections, and SIP accounts"),
        ("Panel Keys", "Total Physical Keys Allocated", len(keys), "Individual key objects allocated in matrix"),
        ("Panel Keys", "Configured Active Keys", len(keys_configured), "Keys assigned with active Talk/Listen commands"),
        ("Production Audio", "Conferences (Partylines)", len(confs), "Conferences / multi-user partyline channels"),
        ("Production Audio", "Talk Groups", len(groups), "One-to-many directed talkgroups"),
        ("Production Audio", "IFB Foldback Channels", len(ifbs), "Broadcast interruptible foldback channels"),
        ("Production Audio", "Audio Patches (DSP Matrices)", len(patches), "Per-panel mixing matrices and filter chains"),
        ("Control & Automation", "GPIO Input Channels", len([r for r in recs if r['class'] == 0x00c]), "Hardware opto-isolated GPI inputs"),
        ("Control & Automation", "GPIO Output Channels", len([r for r in recs if r['class'] == 0x00d]), "Hardware relay output GPI channels"),
        ("Control & Automation", "Logic Functions & Lines", len([r for r in recs if r['class'] in (0x00a, 0x00b, 0x005)]), "Internal matrix logic sources, gates & lines"),
        ("Security & Access", "User Accounts", len(users), "Configured administrator & operator accounts"),
    ]

    for r_idx, (cat, param, val, desc) in enumerate(rows, 5):
        bg = C['row_alt'] if r_idx % 2 == 0 else C['row_white']
        ws.row_dimensions[r_idx].height = 20
        write_cell(ws, r_idx, 1, cat, bg=bg, bold=True)
        write_cell(ws, r_idx, 2, param, bg=bg)
        write_cell(ws, r_idx, 3, val, bg=bg, bold=True, align="center")
        write_cell(ws, r_idx, 4, desc, bg=bg)

    auto_width(ws)


# ── Sheet 2: System Settings ───────────────────────────────────────────────────
def build_system_settings_sheet(wb, h, recs, byid):
    ws = wb.create_sheet(title="System Settings")
    net = next((r for r in recs if r['class'] == 2), {})
    if not net:
        return
    net_gen = A.net_general(net)
    net_call = A.net_call_key_defaults(net)
    net_port = A.net_port_settings(net)
    net_mon = A.net_monitor_defaults(net)

    title_banner(ws, "System-Wide Defaults & CPhysNet Configuration",
                 f"System: {net_gen.get('System name', '')}  |  Net Number: {net_gen.get('Net number', '')}", max_col=4)

    headers = ["Setting Category", "Parameter Name", "Configured Value", "Scope / Details"]
    header_row(ws, 4, headers, bg=C['navy'])

    settings_rows = [
        # General & Trunking
        ("General", "System Name", net_gen.get('System name'), "System name identifier"),
        ("General", "Net Number", net_gen.get('Net number'), "Inter-matrix network address"),
        ("General", "Default Trunk Address: Port", net_gen.get('Default Trunking Address: Port'), "Default trunk address for ports"),
        ("General", "Default Trunk Address: Group", net_gen.get('Default Trunking Address: Group'), "Default trunk address for groups"),
        ("General", "Default Trunk Address: Conference", net_gen.get('Default Trunking Address: Conference'), "Default trunk address for conferences"),
        ("General", "Default Trunk Address: Trunkline", net_gen.get('Default Trunking Address: Trunkline'), "Default trunk address for trunklines"),
        # Monitor Defaults (Dialog 703)
        ("Monitor Defaults", "Monitor Keystate", net_mon.get('Monitor Keystate'), "Keystate monitoring default (Dialog 703)"),
        ("Monitor Defaults", "Monitor Call to Port", net_mon.get('Monitor Call to Port'), "Call to port monitoring default (Dialog 703)"),
        ("Monitor Defaults", "Monitor Call to IFB", net_mon.get('Monitor Call to IFB'), "Call to IFB monitoring default (Dialog 703)"),
        # Color Defaults (Dialog 729)
        ("Color Defaults", "Define Colors Automatically", "Enabled" if net_gen.get('Define colors automatically') else "Disabled", "Dialog 729 CheckBox 1879"),
        *[( "Color Defaults", f"Function Color: {fn_name}", net_gen.get(f"Function color: {fn_name}", "None"), "Dialog 729 Palette Assignment")
          for fn_name in A.FUNCTION_COLOR_ORDER],
        # AES67 Defaults (Dialog 676)
        ("AES67 Defaults", "PTP Domain", net_gen.get('AES67: PTP Domain'), "IEEE 1588 PTP Domain number"),
        ("AES67 Defaults", "PTP Mode", net_gen.get('AES67: PTP Mode'), "PTP distribution mode (multicast / hybrid)"),
        ("AES67 Defaults", "DSCP / DiffServ", net_gen.get('AES67: DSCP'), "QoS Differentiated Services Code Point"),
        ("AES67 Defaults", "Payload Type", net_gen.get('AES67: Payload Type'), "RTP Payload Type number"),
        ("AES67 Defaults", "SSRC Identifier", net_gen.get('AES67: SSRC'), "Synchronization Source identifier"),
        ("AES67 Defaults", "Timestamp Offset", net_gen.get('AES67: Time Stamp Offset'), "PTP timestamp offset"),
        ("AES67 Defaults", "SIP Port (Ports, Artist 32/64/128)", net_gen.get('AES67: SIP TCP/UDP port (ports, Artist-32/64/128)'), "Standard SIP TCP/UDP port"),
        ("AES67 Defaults", "SIP Port (Clients)", net_gen.get('AES67: SIP TCP/UDP port (clients)'), "Client SIP TCP/UDP port"),
        ("AES67 Defaults", "TCP Port on Artist-1024", net_gen.get('AES67: TCP port on Artist-1024'), "Artist-1024 management port"),
        ("AES67 Defaults", "Audio Bit Depth", net_gen.get('AES67: Bit Depth'), "Encoding bit depth (e.g. L24)"),
        ("AES67 Defaults", "Packet Time", net_gen.get('AES67: Packet Time'), "AES67 audio transmission packet time"),
        ("AES67 Defaults", "Default Connection Method", net_gen.get('AES67: Default Connection Method'), "Connection negotiation protocol"),
        # Call Defaults (Dialog 208)
        ("Call Defaults", "Call to Port: Call Priority", net_call.get('Call to Port: Call Prio'), "Default priority for port calls"),
        ("Call Defaults", "Call to Port: Duplex", net_call.get('Call to Port: Duplex'), "Duplex calling mode"),
        ("Call Defaults", "Reply: Call Priority", net_call.get('Reply: Call Prio'), "Priority for Reply key"),
        ("Call Defaults", "Reply: Calls from Conference", net_call.get('Reply: Calls from Conf'), "Allow reply to conference calls"),
        ("Call Defaults", "Reply: Duplex", net_call.get('Reply: Duplex'), "Reply duplex mode"),
        ("Call Defaults", "Call to Conference: Call Priority", net_call.get('Call to Conference: Call Prio'), "Default conference call priority"),
        ("Call Defaults", "Call to Group: Call Priority", net_call.get('Call to Group: Call Prio'), "Default group call priority"),
        ("Call Defaults", "Listen to Port: Call Priority", net_call.get('Listen to Port: Call Prio'), "Default listen priority"),
        ("Call Defaults", "Route Audio: Call Priority", net_call.get('Route Audio: Call Prio'), "Default audio routing priority"),
        # Key Defaults (Dialog 207)
        ("Key Defaults", "Default Key Mode", net_call.get('Key Mode'), "Standard key operation mode"),
        ("Key Defaults", "Latching Timeout", net_call.get('Latching Timeout'), "Default key latching timeout"),
        ("Key Defaults", "Activate Speaker Dim", "Yes" if net_call.get('Activate Speaker Dim') else "No", "Dim speaker when key is pressed"),
        ("Key Defaults", "Restore Volume Level", "Yes" if net_call.get('Restore volume level') else "No", "Restore previous volume level"),
        ("Key Defaults", "Restart Latching Timer", "Yes" if net_call.get('Restart Latching timer') else "No", "Reset timer on key tap"),
        ("Key Defaults", "Action When Muted Key Pressed", net_call.get('Action when muted key is pressed'), "Behavior when pressing muted key"),
        # Port Settings & Security (Dialog 209)
        ("Port Settings", "Dim Lower Prios for Standard", net_port.get('Dim lower Prios for "Standard"'), "Dim attenuation for standard priority"),
        ("Port Settings", "Character Set", net_port.get('Character Set'), "Display text character encoding"),
        ("Port Settings", "Inactive Keybanks Locked", "Yes" if net_port.get('Inactive Keybanks are locked') else "No", "Lock inactive banks"),
        ("Port Settings", "Live View Password", net_port.get('Live View Password') or "None (Unlocked)", "Director courtesy lock password"),
        ("Port Settings", "Panel Setup PIN", net_port.get('Panel PIN') or "None (Unlocked)", "Panel local setup lock PIN"),
        ("Port Settings", "Bolero Multicast Range", f"{net_port.get('Bolero Multicast IP: from', '')} - {net_port.get('to', '')}", "Dynamic Bolero multicast pool"),
    ]

    for r_idx, (cat, param, val, desc) in enumerate(settings_rows, 5):
        bg = C['row_alt'] if r_idx % 2 == 0 else C['row_white']
        ws.row_dimensions[r_idx].height = 20
        write_cell(ws, r_idx, 1, cat, bg=bg, bold=True)
        write_cell(ws, r_idx, 2, param, bg=bg)
        write_cell(ws, r_idx, 3, val, bg=bg, bold=True, align="center" if "Port" in param or "Mode" in param else "left")
        write_cell(ws, r_idx, 4, desc, bg=bg)

    auto_width(ws)


# ── Sheet 3: Nodes & Topology ─────────────────────────────────────────────────
def build_nodes_sheet(wb, h, recs, byid):
    ws = wb.create_sheet(title="Nodes & Topology")
    nodes = [r for r in recs if r['class'] == 3]
    lwls = [r for r in recs if r['class'] == 5]

    title_banner(ws, "Artist Mainframe Nodes & Optical Fibre Ring Topology",
                 f"Total Frames: {len(nodes)}  |  Total Fibre Links: {len(lwls)}", max_col=10)

    headers = ["#", "Node Name", "Node #", "Node ID", "Chassis Model", "Ring SOA", "Allocated Ports (NOA)", "Controller A", "Controller B", "PSU Configuration"]
    header_row(ws, 4, headers, bg=C['teal'])

    for r_idx, n in enumerate(nodes, 5):
        bg = C['row_alt'] if r_idx % 2 == 0 else C['row_white']
        ws.row_dimensions[r_idx].height = 20
        model = A.NODE_TYPE_NAMES.get(n.get('node_type', 0), 'Unknown Chassis')
        ctrl_a = byid.get(n['controllers'][0]) if n.get('controllers') and n['controllers'][0] else None
        ctrl_b = byid.get(n['controllers'][1]) if n.get('controllers') and len(n['controllers']) > 1 and n['controllers'][1] else None
        psu_1 = byid.get(n['power_supplies'][0]) if n.get('power_supplies') and n['power_supplies'][0] else None
        psu_2 = byid.get(n['power_supplies'][1]) if n.get('power_supplies') and len(n['power_supplies']) > 1 and n['power_supplies'][1] else None
        psu_text = "Dual Redundant" if (psu_1 and psu_2) else ("Single PSU" if psu_1 else "None Fitted")

        write_cell(ws, r_idx, 1, r_idx - 4, bg=bg, align="center")
        write_cell(ws, r_idx, 2, n.get('name', ''), bg=bg, bold=True)
        write_cell(ws, r_idx, 3, n.get('node_address', ''), bg=bg, align="center")
        write_cell(ws, r_idx, 4, n.get('node_id', ''), bg=bg, align="center")
        write_cell(ws, r_idx, 5, model, bg=bg)
        write_cell(ws, r_idx, 6, n.get('soa', 0), bg=bg, align="center")
        write_cell(ws, r_idx, 7, n.get('noa', 0), bg=bg, align="center", bold=True)
        write_cell(ws, r_idx, 8, A.card_model(ctrl_a, n) if ctrl_a else "Empty", bg=bg)
        write_cell(ws, r_idx, 9, A.card_model(ctrl_b, n) if ctrl_b else "Empty", bg=bg)
        write_cell(ws, r_idx, 10, psu_text, bg=bg)

    # Secondary table: Fibre Links
    start_lwl = len(nodes) + 7
    ws.merge_cells(start_row=start_lwl - 1, start_column=1, end_row=start_lwl - 1, end_column=6)
    c_sub = ws.cell(row=start_lwl - 1, column=1, value="Optical Fibre Ring Links (CPhysLWL)")
    c_sub.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    c_sub.fill = fill(C['slate'])
    c_sub.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[start_lwl - 1].height = 22

    lwl_headers = ["Link #", "Local Node", "Local Address", "Remote Node", "Remote Address", "Fibre Channel Pairs"]
    header_row(ws, start_lwl, lwl_headers, bg=C['slate'])

    for r_idx, l in enumerate(lwls, start_lwl + 1):
        bg = C['row_alt'] if r_idx % 2 == 0 else C['row_white']
        ws.row_dimensions[r_idx].height = 20
        na = byid.get(l.get('node_a'))
        nb = byid.get(l.get('node_b'))
        write_cell(ws, r_idx, 1, r_idx - start_lwl, bg=bg, align="center")
        write_cell(ws, r_idx, 2, na.get('name') if na else "Unknown", bg=bg, bold=True)
        write_cell(ws, r_idx, 3, na.get('node_address') if na else "", bg=bg, align="center")
        write_cell(ws, r_idx, 4, nb.get('name') if nb else "Unknown", bg=bg, bold=True)
        write_cell(ws, r_idx, 5, nb.get('node_address') if nb else "", bg=bg, align="center")
        write_cell(ws, r_idx, 6, len(l.get('lwl_pairs', [])), bg=bg, align="center")

    auto_width(ws)


# ── Sheet 4: Cards & Slots ────────────────────────────────────────────────────
def build_cards_sheet(wb, h, recs, byid):
    ws = wb.create_sheet(title="Cards & Slots")
    nodes = [r for r in recs if r['class'] == 3]

    title_banner(ws, "Hardware Interface Cards & Chassis Bay Slots",
                 "Per-slot card models, sub-bay allocations, network interfaces, and clock sync", max_col=11)

    headers = ["#", "Node / Frame", "Bay #", "Sub-Bay", "Card Model", "Card Name", "Class Code", "Start Port", "Allocated Ports", "Network / Interface Settings", "Sync / Audio Format"]
    header_row(ws, 4, headers, bg=C['teal'])

    card_rows = []
    for n in nodes:
        for bay_idx, cid in enumerate(n.get('slots', []), 1):
            if cid and cid in byid:
                card = byid[cid]
                card_rows.append((n, bay_idx, card))

    for r_idx, (node, bay, c) in enumerate(card_rows, 5):
        bg = C['row_alt'] if r_idx % 2 == 0 else C['row_white']
        ws.row_dimensions[r_idx].height = 20
        model = A.card_model(c, node)
        sub_bay = c.get('sub_bay', '—')
        start_p = c.get('start_port', '—')
        alloc_p = c.get('allocated_ports', '—')

        # Network / Interface Settings string
        net_info = []
        sync_info = []
        if 'ip' in c and c['ip']:
            ip_str = '.'.join(str(x) for x in c['ip'].to_bytes(4, 'big'))
            net_info.append(f"IP: {ip_str}")
        if 'media' in c:
            m_list = c['media'] if isinstance(c['media'], list) else [c['media']]
            for m_idx, m in enumerate(m_list, 1):
                if isinstance(m, dict) and m.get('ip'):
                    m_ip = '.'.join(str(x) for x in (m['ip'] & 0xffffffff).to_bytes(4, 'big'))
                    net_info.append(f"Media {m_idx} IP: {m_ip}")
        if 'interface_details' in c:
            for idx, idet in enumerate(c['interface_details'], 1):
                net_info.append(f"Media {idx}: {idet.get('assigned_ports', 0)} ports")
                if idet.get('sync_mode'):
                    sync_info.append(f"Media {idx}: {idet['sync_mode']}")
        if c.get('class') == 0x107:  # Classic MADI
            net_info.append(f"Up: {c.get('up_interface')}, Down: {c.get('down_interface')}")
            sync_info.append(f"Frame: {c.get('frame_length')} ch, Block: {c.get('channel_block')}")
        if c.get('dante_name'):
            net_info.append(f"Dante: {c['dante_name']}")

        write_cell(ws, r_idx, 1, r_idx - 4, bg=bg, align="center")
        write_cell(ws, r_idx, 2, node.get('name', ''), bg=bg, bold=True)
        write_cell(ws, r_idx, 3, f"Bay {bay}", bg=bg, align="center")
        write_cell(ws, r_idx, 4, sub_bay, bg=bg, align="center")
        write_cell(ws, r_idx, 5, model, bg=bg, bold=True)
        write_cell(ws, r_idx, 6, c.get('name', ''), bg=bg)
        write_cell(ws, r_idx, 7, f"0x{c['class']:03x}", bg=bg, align="center")
        write_cell(ws, r_idx, 8, start_p, bg=bg, align="center")
        write_cell(ws, r_idx, 9, alloc_p, bg=bg, align="center", bold=True)
        write_cell(ws, r_idx, 10, ' | '.join(net_info) if net_info else "—", bg=bg)
        write_cell(ws, r_idx, 11, ' | '.join(sync_info) if sync_info else "—", bg=bg)

    auto_width(ws)


# ── Sheet 5: Ports ─────────────────────────────────────────────────────────────
def build_ports_sheet(wb, h, recs, byid):
    ws = wb.create_sheet(title="Ports")
    ports = [r for r in recs if r['class'] in A.PORT_TYPE_NAMES]
    # Sort by port number or node-bay
    sorted_ports = sorted(ports, key=lambda p: (p.get('port_number', 0), p.get('port_index', 0)))

    title_banner(ws, "Artist Digital Matrix Ports Grid",
                 f"Total Configured Ports: {len(ports)}  |  1:1 Replica of Riedel Director Ports Table", max_col=15)

    headers = [
        "Port #", "Local 8-char Label", "Long Name", "Alias", "Subtitle",
        "Port Type", "Node-Bay", "Architecture", "Input Gain", "Output Gain",
        "Room Code", "Room Mode", "2nd Channel", "Keypad Shortcut", "Streaming / Network IP"
    ]
    header_row(ws, 4, headers, bg=C['navy'])

    arch_names = {0: 'SIC AES67', 1: 'Classic Card', 2: 'Virtual / Connection'}

    for r_idx, p in enumerate(sorted_ports, 5):
        bg = C['row_alt'] if r_idx % 2 == 0 else C['row_white']
        ws.row_dimensions[r_idx].height = 20

        p_num = p['port_strings'][1] if p.get('port_strings') and len(p['port_strings']) > 1 else str(p.get('port_number', ''))
        p_type = A.port_type(p, byid)
        node_bay = A.port_node_bay(p, byid)
        arch = arch_names.get(p.get('port_architecture'), '')
        in_gain = f"{p['input_gain_db']:+.1f} dB" if 'input_gain_db' in p else "0.0 dB"
        out_gain = f"{p['output_gain_db']:+.1f} dB" if 'output_gain_db' in p else "0.0 dB"
        room = ('Room ' if p.get('room_code') else '') + A.room_code_label(p.get('room_code', 0))
        shortcut = str(p['keypad_shortcut']) if p.get('keypad_shortcut') is not None else ""

        # Streaming / IP details
        stream_info = []
        om2 = p.get('output_media_2')
        if om2 and om2.get('multicast'):
            stream_info.append(f"Bolero Mcast: {om2['multicast']}:{om2.get('multicast_port', 5004)}")
            if om2.get('bolero_user_id'):
                stream_info.append(f"User: {om2['bolero_user_id']}")
        sip = p.get('port_d0c2c0')
        if sip:
            sip_parts = []
            if sip.get('remote_host'):
                sip_parts.append(f"SIP Host: {sip['remote_host']}")
            if sip.get('local_sip_id'):
                sip_parts.append(f"Local: {sip['local_sip_id']}")
            if sip.get('remote_sip_id'):
                sip_parts.append(f"Remote: {sip['remote_sip_id']}")
            if sip.get('audio_codec'):
                sip_parts.append(f"Codec: {sip['audio_codec']}")
            if sip_parts:
                stream_info.append(' | '.join(sip_parts))
        if p.get('input_channel') is not None and p.get('output_channel') is not None:
            stream_info.append(f"NSA Ch: {p['input_channel']}/{p['output_channel']}")
        elif p.get('input_channel') is not None:
            stream_info.append(f"NSA In Ch: {p['input_channel']}")
        elif p.get('output_channel') is not None:
            stream_info.append(f"NSA Out Ch: {p['output_channel']}")

        write_cell(ws, r_idx, 1, p_num, bg=bg, bold=True, align="center")
        write_cell(ws, r_idx, 2, p.get('name', ''), bg=bg, bold=True)
        write_cell(ws, r_idx, 3, p.get('port_str', ''), bg=bg)
        write_cell(ws, r_idx, 4, p.get('alias', ''), bg=bg)
        write_cell(ws, r_idx, 5, p.get('port_str2', ''), bg=bg)
        write_cell(ws, r_idx, 6, p_type, bg=bg, bold=True)
        write_cell(ws, r_idx, 7, node_bay, bg=bg)
        write_cell(ws, r_idx, 8, arch, bg=bg, align="center")
        write_cell(ws, r_idx, 9, in_gain, bg=bg, align="center")
        write_cell(ws, r_idx, 10, out_gain, bg=bg, align="center")
        write_cell(ws, r_idx, 11, room, bg=bg, align="center")
        write_cell(ws, r_idx, 12, p.get('room_mode', ''), bg=bg, align="center")
        write_cell(ws, r_idx, 13, "Yes" if p.get('second_audio_channel') else "No", bg=bg, align="center")
        write_cell(ws, r_idx, 14, shortcut, bg=bg, align="center")
        write_cell(ws, r_idx, 15, ' | '.join(stream_info) if stream_info else "—", bg=bg)

    auto_width(ws)


# ── Sheet 6: Panels & Keys ────────────────────────────────────────────────────
def build_panels_keys_sheet(wb, h, recs, byid):
    ws = wb.create_sheet(title="Panels & Keys")
    keys = [r for r in recs if r['class'] == 9 and r.get('commands')]

    # Sort keys by holder and slot
    sorted_keys = sorted(keys, key=lambda k: (k.get('holder', 0), k.get('slot', 0)))

    title_banner(ws, "Hardware SmartPanels, Beltpacks & Active Key Assignments",
                 f"Total Active Configured Keys: {len(sorted_keys)}", max_col=14)

    headers = [
        "Station / Panel Name", "Port #", "Station Model", "Key Slot", "Key Label",
        "Key Subtitle", "Group Color", "Text Color", "Key Mode", "Latching Timeout",
        "Primary Function", "Target Destination", "Priority", "Stacked Secondary Function"
    ]
    header_row(ws, 4, headers, bg=C['teal'])

    for r_idx, k in enumerate(sorted_keys, 5):
        bg = C['row_alt'] if r_idx % 2 == 0 else C['row_white']
        ws.row_dimensions[r_idx].height = 20

        holder = byid.get(k.get('holder'))
        panel_name = "Unknown Station"
        port_num = ""
        panel_model = "Unknown Model"

        if holder:
            if holder['class'] in A.PORT_TYPE_NAMES:
                panel_name = holder.get('port_str') or holder.get('name', '')
                port_num = holder['port_strings'][1] if holder.get('port_strings') and len(holder['port_strings']) > 1 else ''
                panel_model = A.port_type(holder, byid)
            elif holder['class'] in A.EXPANSION_SLOTS or holder['class'] == 0x507:
                host = byid.get(holder.get('host_panel'))
                host_name = host.get('port_str') or host.get('name', '') if host else 'Host'
                port_num = host['port_strings'][1] if host and host.get('port_strings') and len(host['port_strings']) > 1 else ''
                panel_name = f"{host_name} (Exp #{holder.get('expansion_address', 0) + 1})"
                panel_model = "Expansion Module"

        cmds = [byid.get(cid) for cid in k.get('commands', []) if cid in byid]
        fn1, target1, prio1 = format_command(cmds[0], byid) if len(cmds) > 0 else ('Empty', '', '')
        fn2, target2, prio2 = format_command(cmds[1], byid) if len(cmds) > 1 else ('', '', '')
        sec_str = f"{fn2}: {target2}" if fn2 else "—"

        slot_num = k.get('slot', 0) + 1
        timeout_str = A.LATCHING_TIMEOUTS[k['latching_timeout']] if k.get('latching_timeout', 0) < len(A.LATCHING_TIMEOUTS) else str(k.get('latching_timeout', ''))
        grp_c = A.swatch_color_name(k.get('group_colour'))
        txt_c = f"#{k['text_colour'].upper()}" if k.get('text_colour') else "Default"

        write_cell(ws, r_idx, 1, panel_name, bg=bg, bold=True)
        write_cell(ws, r_idx, 2, port_num, bg=bg, align="center")
        write_cell(ws, r_idx, 3, panel_model, bg=bg)
        write_cell(ws, r_idx, 4, f"Key {slot_num}", bg=bg, align="center", bold=True)
        write_cell(ws, r_idx, 5, k.get('label', ''), bg=bg, bold=True)
        write_cell(ws, r_idx, 6, k.get('subtitle', ''), bg=bg)
        write_cell(ws, r_idx, 7, grp_c, bg=bg, align="center")
        write_cell(ws, r_idx, 8, txt_c, bg=bg, align="center")
        write_cell(ws, r_idx, 9, k.get('mode', 'Momentary'), bg=bg, align="center")
        write_cell(ws, r_idx, 10, timeout_str, bg=bg, align="center")
        write_cell(ws, r_idx, 11, fn1, bg=bg, bold=True)
        write_cell(ws, r_idx, 12, target1, bg=bg)
        write_cell(ws, r_idx, 13, prio1, bg=bg, align="center")
        write_cell(ws, r_idx, 14, sec_str, bg=bg)

    auto_width(ws)


# ── Sheet 7: Conferences ──────────────────────────────────────────────────────
def build_conferences_sheet(wb, h, recs, byid):
    ws = wb.create_sheet(title="Conferences")
    confs = [r for r in recs if r['class'] == 0x012]
    sorted_confs = sorted(confs, key=lambda c: c.get('label', ''))

    title_banner(ws, "Production Conferences & Partylines",
                 f"Total Conferences: {len(confs)}  |  Multi-user matrix partyline channels", max_col=10)

    headers = ["#", "Conference Label", "Long Name", "Alias", "Color", "Trunk Enabled", "DynaConf", "Keypad Shortcut", "Member Count", "Configured Member Ports"]
    header_row(ws, 4, headers, bg=C['navy'])

    for r_idx, c in enumerate(sorted_confs, 5):
        bg = C['row_alt'] if r_idx % 2 == 0 else C['row_white']
        ws.row_dimensions[r_idx].height = 20

        member_ports = []
        for mid in c.get('members', []):
            m = byid.get(mid)
            if m:
                p_num = m['port_strings'][1] if m.get('port_strings') and len(m['port_strings']) > 1 else ''
                p_lbl = m.get('name', '')
                member_ports.append(f"{p_lbl} ({p_num})" if p_num else p_lbl)

        color_str = A.swatch_color_name(c.get('colour'))

        write_cell(ws, r_idx, 1, r_idx - 4, bg=bg, align="center")
        write_cell(ws, r_idx, 2, c.get('label', ''), bg=bg, bold=True)
        write_cell(ws, r_idx, 3, c.get('long_name', ''), bg=bg)
        write_cell(ws, r_idx, 4, c.get('alias', ''), bg=bg)
        write_cell(ws, r_idx, 5, color_str, bg=bg, align="center")
        write_cell(ws, r_idx, 6, "Yes" if c.get('trunk_enabled') else "No", bg=bg, align="center")
        write_cell(ws, r_idx, 7, "Yes" if c.get('dynaconf') else "No", bg=bg, align="center")
        write_cell(ws, r_idx, 8, c.get('keypad_shortcut', '') if c.get('keypad_shortcut') != 65535 else "", bg=bg, align="center")
        write_cell(ws, r_idx, 9, len(member_ports), bg=bg, align="center", bold=True)
        write_cell(ws, r_idx, 10, ', '.join(member_ports) if member_ports else "—", bg=bg)

    auto_width(ws)


# ── Sheet 8: Groups ───────────────────────────────────────────────────────────
def build_groups_sheet(wb, h, recs, byid):
    ws = wb.create_sheet(title="Groups")
    groups = [r for r in recs if r['class'] == 0x011]
    sorted_groups = sorted(groups, key=lambda g: g.get('label', ''))

    title_banner(ws, "Directed Talkgroups",
                 f"Total Groups: {len(groups)}  |  One-to-many broadcast channels", max_col=8)

    headers = ["#", "Group Label", "Long Name", "Color", "Keypad Shortcut", "Member Count", "Trunk Address", "Member Ports List"]
    header_row(ws, 4, headers, bg=C['amber'])

    for r_idx, g in enumerate(sorted_groups, 5):
        bg = C['row_alt'] if r_idx % 2 == 0 else C['row_white']
        ws.row_dimensions[r_idx].height = 20

        member_ports = []
        for mid in g.get('members', []):
            m = byid.get(mid)
            if m:
                p_num = m['port_strings'][1] if m.get('port_strings') and len(m['port_strings']) > 1 else ''
                p_lbl = m.get('name', '')
                member_ports.append(f"{p_lbl} ({p_num})" if p_num else p_lbl)

        color_str = A.swatch_color_name(g.get('colour'))

        write_cell(ws, r_idx, 1, r_idx - 4, bg=bg, align="center")
        write_cell(ws, r_idx, 2, g.get('label', ''), bg=bg, bold=True)
        write_cell(ws, r_idx, 3, g.get('long_name', ''), bg=bg)
        write_cell(ws, r_idx, 4, color_str, bg=bg, align="center")
        write_cell(ws, r_idx, 5, g.get('keypad_shortcut', '') if g.get('keypad_shortcut') != 65535 else "", bg=bg, align="center")
        write_cell(ws, r_idx, 6, len(member_ports), bg=bg, align="center", bold=True)
        write_cell(ws, r_idx, 7, g.get('trunk_address', 0), bg=bg, align="center")
        write_cell(ws, r_idx, 8, ', '.join(member_ports) if member_ports else "—", bg=bg)

    auto_width(ws)


# ── Sheet 9: IFB Routing ──────────────────────────────────────────────────────
def build_ifb_sheet(wb, h, recs, byid):
    ws = wb.create_sheet(title="IFB Routing")
    ifbs = [r for r in recs if r['class'] == 0x066]
    sorted_ifbs = sorted(ifbs, key=lambda i: i.get('ifb_number', 0))

    title_banner(ws, "Interruptible Foldback (IFB) Channels",
                 f"Total IFB Channels: {len(ifbs)}  |  Broadcast mix-minus and foldback audio routing", max_col=8)

    headers = ["IFB #", "IFB Label", "Long Name", "Dim Level", "Trunk Enabled", "Input Endpoint", "Mix-Minus Endpoint", "Output Endpoint"]
    header_row(ws, 4, headers, bg=C['purple'])

    def endpoint_name(ep):
        if not ep:
            return "—"
        role = ep.get('role', '')
        t = ep.get('type')
        if t == 1:
            p = byid.get(ep.get('port'))
            if p:
                p_num = p['port_strings'][1] if p.get('port_strings') and len(p['port_strings']) > 1 else ''
                return f"{p.get('name', '')} (Port {p_num})" if p_num else p.get('name', '')
            return f"Port ID {ep.get('port')}"
        elif t == 2:
            grp = byid.get(ep.get('group'))
            return f"Group: {grp.get('name', '')}" if grp else f"Group ID {ep.get('group')}"
        elif t == 4:
            return f"Trunk {ep.get('a')}:{ep.get('b')}"
        return "—"

    for r_idx, i in enumerate(sorted_ifbs, 5):
        bg = C['row_alt'] if r_idx % 2 == 0 else C['row_white']
        ws.row_dimensions[r_idx].height = 20

        write_cell(ws, r_idx, 1, i.get('ifb_number', r_idx - 4), bg=bg, align="center", bold=True)
        write_cell(ws, r_idx, 2, i.get('label', ''), bg=bg, bold=True)
        write_cell(ws, r_idx, 3, i.get('long_name', ''), bg=bg)
        write_cell(ws, r_idx, 4, i.get('dim_db', '0 dB'), bg=bg, align="center")
        write_cell(ws, r_idx, 5, "Yes" if i.get('is_trunk_enabled') else "No", bg=bg, align="center")
        write_cell(ws, r_idx, 6, endpoint_name(i.get('input')), bg=bg)
        write_cell(ws, r_idx, 7, endpoint_name(i.get('mix_minus')), bg=bg)
        write_cell(ws, r_idx, 8, endpoint_name(i.get('output')), bg=bg)

    auto_width(ws)


# ── Sheet 10: Audio Patch ─────────────────────────────────────────────────────
def build_audiopatch_sheet(wb, h, recs, byid):
    ws = wb.create_sheet(title="Audio Patch")
    patches = [r for r in recs if r['class'] == 0x019]

    title_banner(ws, "Audio Patch DSP Mixing & Filtering Matrices",
                 f"Total Audio Patches: {len(patches)}  |  Per-port mixing matrices and filter chains", max_col=7)

    headers = ["#", "Panel / Port Name", "Patch Name", "Operating Mode", "Active Unmuted Crosspoints", "Muted Output Amps", "DSP Filters"]
    header_row(ws, 4, headers, bg=C['slate'])

    for r_idx, p in enumerate(patches, 5):
        bg = C['row_alt'] if r_idx % 2 == 0 else C['row_white']
        ws.row_dimensions[r_idx].height = 20

        panel = byid.get(p.get('panel'))
        panel_name = panel.get('port_str') or panel.get('name') if panel else f"Panel ID {p.get('panel')}"
        mode_str = p.get('patch_mode_name', 'Speaker mode')
        routes, muted_outs = A.audiopatch_routes(p)

        dsp_info = []
        for e in p.get('elements', []):
            if e['kind'] == 'bandpass':
                txt = A.audiopatch_element_text(e)
                dsp_info.append(f"Bandpass: {txt}")
            elif e['kind'] == 'lim_comp':
                txt = A.audiopatch_element_text(e)
                dsp_info.append(f"Dynamics: {txt}")

        write_cell(ws, r_idx, 1, r_idx - 4, bg=bg, align="center")
        write_cell(ws, r_idx, 2, panel_name, bg=bg, bold=True)
        write_cell(ws, r_idx, 3, p.get('name', ''), bg=bg)
        write_cell(ws, r_idx, 4, mode_str, bg=bg, align="center")
        write_cell(ws, r_idx, 5, ', '.join(routes[:6]) + (f" (+{len(routes)-6} more)" if len(routes) > 6 else "") if routes else "None", bg=bg)
        write_cell(ws, r_idx, 6, ', '.join(muted_outs) if muted_outs else "None", bg=bg)
        write_cell(ws, r_idx, 7, ' | '.join(dsp_info) if dsp_info else "Standard", bg=bg)

    auto_width(ws)


# ── Sheet 11: Logic & GPIO ────────────────────────────────────────────────────
def build_logic_gpio_sheet(wb, h, recs, byid):
    ws = wb.create_sheet(title="Logic & GPIO")
    gin = [r for r in recs if r['class'] == 0x00c]
    gout = [r for r in recs if r['class'] == 0x00d]
    lsrc = [r for r in recs if r['class'] == 0x00a]
    ldst = [r for r in recs if r['class'] == 0x00b]
    lline = [r for r in recs if r['class'] == 0x005]

    title_banner(ws, "Hardware GPIO Channels & Internal Matrix Logic",
                 f"GPIO In: {len(gin)}  |  GPIO Out: {len(gout)}  |  Logic Gates: {len(lsrc)+len(ldst)}  |  Logic Lines: {len(lline)}", max_col=7)

    headers = ["#", "Type", "Channel / Pin #", "Label / Name", "Inverted / NC", "Channel Selection / Off-Delay", "Host Device"]
    header_row(ws, 4, headers, bg=C['teal'])

    row_count = 5
    # GPIO Inputs
    for g in gin:
        bg = C['row_alt'] if row_count % 2 == 0 else C['row_white']
        ws.row_dimensions[row_count].height = 20
        p = byid.get(g.get('panel'))
        p_name = p.get('name') if p else f"Panel {g.get('panel')}"
        write_cell(ws, row_count, 1, row_count - 4, bg=bg, align="center")
        write_cell(ws, row_count, 2, "GPIO In", bg=bg, bold=True)
        write_cell(ws, row_count, 3, f"In {g.get('gpio_index', 0) + 1}", bg=bg, align="center")
        write_cell(ws, row_count, 4, g.get('name', ''), bg=bg)
        write_cell(ws, row_count, 5, "Inverted" if g.get('inverted') else "Normal", bg=bg, align="center")
        write_cell(ws, row_count, 6, "—", bg=bg, align="center")
        write_cell(ws, row_count, 7, p_name, bg=bg)
        row_count += 1

    # GPIO Outputs
    for g in gout:
        bg = C['row_alt'] if row_count % 2 == 0 else C['row_white']
        ws.row_dimensions[row_count].height = 20
        p = byid.get(g.get('panel'))
        p_name = p.get('name') if p else f"Panel {g.get('panel')}"
        nc_str = "NC" if g.get('normally_closed') else "NO"
        off_del = f"Off-Delay: {g.get('off_delay')} ms" if g.get('off_delay') else "None"
        write_cell(ws, row_count, 1, row_count - 4, bg=bg, align="center")
        write_cell(ws, row_count, 2, "GPIO Out", bg=bg, bold=True)
        write_cell(ws, row_count, 3, f"Out {g.get('gpio_index', 0) + 1}", bg=bg, align="center")
        write_cell(ws, row_count, 4, g.get('name', ''), bg=bg)
        write_cell(ws, row_count, 5, f"{'Inverted, ' if g.get('inverted') else ''}{nc_str}", bg=bg, align="center")
        write_cell(ws, row_count, 6, off_del, bg=bg, align="center")
        write_cell(ws, row_count, 7, p_name, bg=bg)
        row_count += 1

    # Logic Lines
    for l in lline:
        bg = C['row_alt'] if row_count % 2 == 0 else C['row_white']
        ws.row_dimensions[row_count].height = 20
        write_cell(ws, row_count, 1, row_count - 4, bg=bg, align="center")
        write_cell(ws, row_count, 2, "Logic Line", bg=bg, bold=True)
        write_cell(ws, row_count, 3, f"Pin {l.get('from_pin')} -> Pin {l.get('to_pin')}", bg=bg, align="center")
        write_cell(ws, row_count, 4, l.get('name', ''), bg=bg)
        write_cell(ws, row_count, 5, "Connected", bg=bg, align="center")
        write_cell(ws, row_count, 6, "Internal Logic Bus", bg=bg, align="center")
        write_cell(ws, row_count, 7, "Matrix Core", bg=bg)
        row_count += 1

    auto_width(ws)


# ── Sheet 12: IP Trunks ───────────────────────────────────────────────────────
def build_trunks_sheet(wb, h, recs, byid):
    ws = wb.create_sheet(title="IP Trunks")
    ports = [r for r in recs if r['class'] in A.PORT_TYPE_NAMES]
    trunks = [p for p in ports if p['class'] in (0x445, 0x502, 0x508) or p.get('trunk_address')]

    title_banner(ws, "Inter-Matrix Digital IP Trunk Lines & VoIP",
                 f"Total IP Trunks & Connections: {len(trunks)}", max_col=10)

    headers = ["#", "Port #", "Trunk Line Name", "Short ID", "Trunk Type", "Local SIP ID", "Remote Host / IP", "Remote SIP ID", "Trunk Net Address", "Audio Codec / Parameters"]
    header_row(ws, 4, headers, bg=C['teal'])

    for r_idx, t in enumerate(trunks, 5):
        bg = C['row_alt'] if r_idx % 2 == 0 else C['row_white']
        ws.row_dimensions[r_idx].height = 20

        p_num = t['port_strings'][1] if t.get('port_strings') and len(t['port_strings']) > 1 else str(t.get('port_number', ''))
        sip = t.get('port_d0c2c0') or {}
        local_id = sip.get('local_sip_id', '—') or '—'
        remote_ip = sip.get('remote_host', '—') or '—'
        remote_sip = sip.get('remote_sip_id', '—') or '—'
        codec = sip.get('audio_codec', 'Standard')

        write_cell(ws, r_idx, 1, r_idx - 4, bg=bg, align="center")
        write_cell(ws, r_idx, 2, p_num, bg=bg, align="center")
        write_cell(ws, r_idx, 3, t.get('port_str') or t.get('name', ''), bg=bg, bold=True)
        write_cell(ws, r_idx, 4, t.get('name', ''), bg=bg, align="center")
        write_cell(ws, r_idx, 5, A.port_type(t, byid), bg=bg, bold=True)
        write_cell(ws, r_idx, 6, local_id, bg=bg, align="center")
        write_cell(ws, r_idx, 7, remote_ip, bg=bg, align="center")
        write_cell(ws, r_idx, 8, remote_sip, bg=bg, align="center")
        write_cell(ws, r_idx, 9, t.get('trunk_address', 0), bg=bg, align="center")
        write_cell(ws, r_idx, 10, codec, bg=bg)

    auto_width(ws)


# ── Sheet 13: Users & Access ──────────────────────────────────────────────────
def build_users_sheet(wb, h, recs, byid):
    ws = wb.create_sheet(title="Users & Access")
    users = [r for r in recs if r['class'] == 0x023]

    title_banner(ws, "Director System Operator Accounts & Security Profiles",
                 f"Total Registered Accounts: {len(users)}", max_col=7)

    headers = ["#", "Username", "Full Name", "Account Role", "Rights Mask", "Courtesy Lock PIN / Password", "Decoded Permissions"]
    header_row(ws, 4, headers, bg=C['navy'])

    for r_idx, u in enumerate(users, 5):
        bg = C['row_alt'] if r_idx % 2 == 0 else C['row_white']
        ws.row_dimensions[r_idx].height = 20
        role = "User Account Manager" if u.get('user_manager') else "Standard User"
        pwd = u.get('password') or "None (Unlocked)"
        perms = ', '.join(u.get('permissions', [])) or "Standard Rights"

        write_cell(ws, r_idx, 1, r_idx - 4, bg=bg, align="center")
        write_cell(ws, r_idx, 2, u.get('name', ''), bg=bg, bold=True)
        write_cell(ws, r_idx, 3, u.get('full_name', ''), bg=bg)
        write_cell(ws, r_idx, 4, role, bg=bg, bold=True, align="center")
        write_cell(ws, r_idx, 5, f"0x{u.get('rights', 0):08x}", bg=bg, align="center")
        write_cell(ws, r_idx, 6, pwd, bg=bg, align="center")
        write_cell(ws, r_idx, 7, perms, bg=bg)

    auto_width(ws)


# ── Sheet 14: Scheduler & Events ──────────────────────────────────────────────
def build_scheduler_sheet(wb, h, recs, byid):
    ws = wb.create_sheet(title="Scheduler")
    tasks = [r for r in recs if r['class'] == 0x05a]
    events = [r for r in recs if r['class'] == 0x05d]

    title_banner(ws, "Automated Scheduler Tasks & Triggered Events",
                 f"Scheduler Tasks: {len(tasks)}  |  Matrix Events: {len(events)}", max_col=8)

    headers = ["#", "Task Name", "Scheduled Time", "Day of Week", "Day of Month", "Month", "Year", "Linked Event Name"]
    header_row(ws, 4, headers, bg=C['slate'])

    if not tasks:
        ws.row_dimensions[5].height = 20
        write_cell(ws, 5, 1, "—", align="center")
        write_cell(ws, 5, 2, "No automated scheduler tasks defined in this file", bold=True)
        for c in range(3, 9):
            write_cell(ws, 5, c, "—", align="center")
    else:
        for r_idx, t in enumerate(tasks, 5):
            bg = C['row_alt'] if r_idx % 2 == 0 else C['row_white']
            ws.row_dimensions[r_idx].height = 20
            t_time = f"{t.get('hour', 0):02d}:{t.get('minute', 0):02d}:{t.get('second', 0):02d}"
            ev = byid.get(t.get('event_id'))
            ev_name = ev.get('name') if ev else f"Event ID {t.get('event_id')}"

            write_cell(ws, r_idx, 1, r_idx - 4, bg=bg, align="center")
            write_cell(ws, r_idx, 2, t.get('name', ''), bg=bg, bold=True)
            write_cell(ws, r_idx, 3, t_time, bg=bg, align="center")
            write_cell(ws, r_idx, 4, str(t.get('day_of_week', '*')), bg=bg, align="center")
            write_cell(ws, r_idx, 5, str(t.get('day', '*')), bg=bg, align="center")
            write_cell(ws, r_idx, 6, str(t.get('month', '*')), bg=bg, align="center")
            write_cell(ws, r_idx, 7, str(t.get('year', '*')), bg=bg, align="center")
            write_cell(ws, r_idx, 8, ev_name, bg=bg)

    auto_width(ws)


# ── Main Export Function ──────────────────────────────────────────────────────
def export_art_to_excel(art_file_path, output_path=None):
    """
    Parses an Artist .Art save file using artist_reader and exports a complete,
    ground-truth multi-sheet Excel workbook.
    """
    path = pathlib.Path(art_file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {art_file_path}")

    data = path.read_bytes()
    h, recs = A.parse_art(data)
    byid = {r['id']: r for r in recs}

    if output_path is None:
        output_path = path.with_suffix('.xlsx')
    else:
        output_path = pathlib.Path(output_path)

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # Remove default blank sheet

    # Build all sheets in order
    build_summary_sheet(wb, h, recs, byid, path)
    build_system_settings_sheet(wb, h, recs, byid)
    build_nodes_sheet(wb, h, recs, byid)
    build_cards_sheet(wb, h, recs, byid)
    build_ports_sheet(wb, h, recs, byid)
    build_panels_keys_sheet(wb, h, recs, byid)
    build_conferences_sheet(wb, h, recs, byid)
    build_groups_sheet(wb, h, recs, byid)
    build_ifb_sheet(wb, h, recs, byid)
    build_audiopatch_sheet(wb, h, recs, byid)
    build_logic_gpio_sheet(wb, h, recs, byid)
    build_trunks_sheet(wb, h, recs, byid)
    build_users_sheet(wb, h, recs, byid)
    build_scheduler_sheet(wb, h, recs, byid)

    wb.save(output_path)
    print(f"Successfully generated: {output_path}")
    return output_path


if __name__ == '__main__':
    out_opt = None
    args = []
    skip = False
    for i, a in enumerate(sys.argv[1:], 1):
        if skip:
            skip = False
            continue
        if a == '-o':
            skip = True
            if i < len(sys.argv):
                out_opt = sys.argv[i + 1]
        elif not a.startswith('-'):
            args.append(a)

    if not args:
        # Default: process all .Art files in parent and current directory
        files = glob.glob('../*.Art') + glob.glob('../**/*.Art', recursive=True)
        for f in files:
            try:
                export_art_to_excel(f)
            except Exception as e:
                print(f"Error converting {f}: {e}")
    else:
        for f in args:
            export_art_to_excel(f, out_opt)
