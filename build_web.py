import base64

def embed():
    with open('artist_reader.py', 'rb') as f: artist_b64 = base64.b64encode(f.read()).decode('utf-8')
    with open('bol_faithful.py', 'rb') as f: bol_b64 = base64.b64encode(f.read()).decode('utf-8')
    with open('art_to_excel.py', 'rb') as f: art_xls_b64 = base64.b64encode(f.read()).decode('utf-8')

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Riedel Configuration Web Exporter (Python Engine)</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/pyodide/v0.25.0/full/pyodide.js"></script>
    <style>
        body {{ background-color: #0f172a; color: #e2e8f0; font-family: ui-sans-serif, system-ui, sans-serif; }}
        .glass-panel {{ background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.1); }}
        th {{ position: sticky; top: 0; background: #1e293b; z-index: 10; }}
        .tab-active {{ border-bottom: 2px solid #3b82f6; color: #60a5fa; }}
        .tab-inactive {{ color: #94a3b8; cursor: pointer; }}
        .tab-inactive:hover {{ color: #cbd5e1; }}
        
        .loader {{ border: 3px solid #1e293b; border-top: 3px solid #3b82f6; border-radius: 50%; width: 16px; height: 16px; animation: spin 1s linear infinite; display: inline-block; vertical-align: middle; }}
        @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
    </style>
</head>
<body class="min-h-screen p-8">
    <div class="max-w-7xl mx-auto">
        <div class="flex items-center justify-between mb-8">
            <h1 class="text-3xl font-bold text-white tracking-tight">Riedel Configuration Exporter <span class="text-blue-400 text-sm align-top">v2.0 Python Engine</span></h1>
            <div id="status" class="text-sm font-medium text-slate-400">Loading Python Engine (Downloading Pyodide ~8MB)...</div>
        </div>

        <input type="file" id="fileInput" class="hidden" accept=".art,.Art,.bol">
        <div id="dropzone" class="glass-panel rounded-xl p-12 text-center border-dashed border-2 border-slate-600 transition-colors mb-8 cursor-pointer hover:bg-slate-800">
            <svg class="w-12 h-12 mx-auto text-slate-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path></svg>
            <p class="text-lg font-medium text-slate-200">Drag & Drop or <span class="text-blue-400 underline">Click Here</span> to select a .Art or .bol file</p>
            <p class="text-sm text-slate-400 mt-2">Parsed securely in your browser using WebAssembly.</p>
        </div>

        <div id="results" class="hidden">
            <div class="flex justify-between items-end gap-4 mb-6 border-b border-slate-700 pb-2">
                <div id="tabs" class="flex space-x-6 overflow-x-auto min-w-0">
                </div>
                <div class="flex gap-2 shrink-0">
                    <button id="btnExport" class="bg-blue-600 hover:bg-blue-500 text-white font-medium py-2 px-4 rounded-lg shadow transition-colors flex items-center">
                        <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-3 3m0 0l-3-3m3 3V4"></path></svg>
                        <span id="btnExportText">Download Excel</span>
                    </button>
                    <button id="btnJson" class="bg-slate-700 hover:bg-slate-600 text-white font-medium py-2 px-4 rounded-lg shadow transition-colors flex items-center">
                        <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-3 3m0 0l-3-3m3 3V4"></path></svg>
                        <span id="btnJsonText">Download JSON</span>
                    </button>
                </div>
            </div>
            <div id="tab-content" class="glass-panel rounded-xl overflow-hidden shadow-2xl">
            </div>
        </div>
    </div>

    <script>
        let pyodide = null;
        let engineReady = false;                          // true once openpyxl and the modules are loaded
        let currentFileData = null;
        let currentFileName = null;
        
        async function initPyodide() {{
            try {{
                pyodide = await loadPyodide();
                
                document.getElementById('status').innerText = "Loading Excel Engine (Downloading openpyxl)...";
                await pyodide.loadPackage("micropip");
                await pyodide.runPythonAsync(`
import micropip
await micropip.install('openpyxl')
import base64
with open('artist_reader.py', 'wb') as f: f.write(base64.b64decode("{artist_b64}"))
with open('bol_faithful.py', 'wb') as f: f.write(base64.b64decode("{bol_b64}"))
with open('art_to_excel.py', 'wb') as f: f.write(base64.b64decode("{art_xls_b64}"))
                `);
                
                await pyodide.runPythonAsync(`
import json
import artist_reader
import bol_faithful
import art_to_excel
import os

def _json_default(o):
    # raw byte fields (e.g. Bolero encryption keys) -> hex; anything else -> text
    return o.hex() if isinstance(o, (bytes, bytearray)) else str(o)

def _artist_view(data):
    # rows for the on-page tabs, built with the same reader helpers as the Excel workbook
    with open('temp.art', 'wb') as f: f.write(data)
    ctx = art_to_excel.Ctx('temp.art')
    try:
        system_name = artist_reader.net_general(ctx.net).get('System name', '')
    except Exception:
        system_name = ''
    # ports configured per frame (NOA is only the frame's ring allocation, and is 0 on e.g. Artist 1024 frames)
    per_node = {{}}
    for p in ctx.ports:
        if p.get('card') in ctx.byid:
            nid = artist_reader.port_card(p, ctx.byid).get('node')
            per_node[nid] = per_node.get(nid, 0) + 1
    frames = []
    for n in ctx.nodes:
        frames.append({{'address': n.get('node_address'), 'name': n.get('name') or '',
                        'model': artist_reader.NODE_TYPE_NAMES.get(n.get('node_type'), 'type %s' % n.get('node_type')),
                        'serial': n.get('serial_number') or '', 'ports': per_node.get(n['id'], 0),
                        'soa': n.get('soa') or None, 'noa': n.get('noa') or None}})
    # keys: one line per key with a label or a function (same numbering as the Excel Keys sheet)
    counts = ctx.key_counts_cache()
    by_holder = {{}}
    for k in ctx.keys:
        cmds = [ctx.byid[c] for c in k.get('commands') or [] if c in ctx.byid]
        if not cmds and not k.get('label'):
            continue                                  # empty key slot
        n, bank = art_to_excel.key_number(k['slot'], counts.get(k['holder'], 0))
        fns = ' | '.join('%s: %s' % (f, t) if t else f
                         for f, t, _ in (art_to_excel.describe_command(c, ctx) for c in cmds)) or '(no function)'
        tag = 'K%d' % n + ('' if bank == 1 else ' bank %d' % bank)
        label = (' "%s"' % k['label']) if k.get('label') else ''
        by_holder.setdefault(k['holder'], []).append((k['slot'], '%s%s [%s]: %s' % (tag, label, k.get('mode') or '', fns)))
    expansions = {{}}                                  # host panel id -> its expansion panels
    for e in ctx.recs:
        if ctx.reader.get(e['id']) == 'read_expansion' and e.get('host_panel') in ctx.byid:
            expansions.setdefault(e['host_panel'], []).append(e)

    def key_lines(holder_id):
        return [line for _, line in sorted(by_holder.get(holder_id, []))]

    ports, panels, bolero = [], [], []
    # same order as the Excel Ports sheet
    for p in sorted(ctx.ports, key=ctx.port_sort_key):
        try:
            ptype, node_bay = artist_reader.port_type(p, ctx.byid), artist_reader.port_node_bay(p, ctx.byid)
        except Exception:
            ptype, node_bay = artist_reader.PORT_TYPE_NAMES.get(p['class'], 'class 0x%x' % p['class']), ''
        ps = p.get('port_strings') or []
        base = {{'port': ps[1] if len(ps) > 1 else '', 'label': p.get('name') or '',
                 'long_name': p.get('port_str') or '', 'alias': p.get('alias') or '',
                 'subtitle': p.get('port_str2') or '', 'type': ptype, 'node_bay': node_bay}}
        ports.append(base)
        lines = key_lines(p['id'])
        n_keys = len(lines)
        for e in sorted(expansions.get(p['id'], []), key=lambda e: e.get('expansion_address') or 0):
            el = key_lines(e['id'])
            if el:
                model = (artist_reader.EXPANSION_NAMES.get(e['class']) or artist_reader.PORT_TYPE_NAMES.get(e['class'])
                         or 'Expansion panel')
                lines += ['%s #%s:' % (model, e.get('expansion_address', ''))] + ['  ' + l for l in el]
                n_keys += len(el)
        if p['class'] == 0x440:                       # Bolero wireless beltpack port
            om2 = p.get('output_media_2') or {{}}
            bolero.append(dict(base, user_id=om2.get('bolero_user_id'),
                               multicast=('%s:%s' % (om2['multicast'], om2.get('multicast_port', ''))
                                          if om2.get('multicast') else ''),
                               keys=chr(10).join(lines), key_count=n_keys))
        elif lines:                                   # a panel (or other key holder) with keys
            panels.append(dict(base, keys=chr(10).join(lines), key_count=n_keys))
    vfs = [{{'port': r['port'], 'label': r['label'], 'long_name': r['long_name'], 'type': r['type'],
             'always': chr(10).join(r['slots'].get('Always', [])), 'vox': chr(10).join(r['slots'].get('On VOX', [])),
             'on_call': chr(10).join(r['slots'].get('On Call', []))}} for r in art_to_excel.virtual_function_rows(ctx)]
    resources = [{{'category': cat, 'item': item, 'quantity': n}} for cat, item, n in art_to_excel.resource_counts(ctx)]
    return {{'system_name': system_name, 'frames': frames, 'ports': ports, 'panels': panels, 'bolero': bolero, 'vfs': vfs,
             'resources': resources,
             'panel_count': sum(r['quantity'] for r in resources if r['category'] == 'Panels'),
             'bolero_count': sum(r['quantity'] for r in resources if r['category'] == 'Bolero beltpacks'),
             'conferences': len(ctx.by_class[0x12]), 'records': len(ctx.recs)}}

# Bolero radio band, from the firmware (libRadon 3.4.1): isDectAntenna(node type 1), is2G4Antenna(node type 4),
# and TrimBPConfigHelper::bpTypeAndNodeTypeMatch (a DECT antenna takes beltpack types 0xce4/0xce7, a 2.4 GHz
# antenna takes 0xce8/0xcea). The beltpack type is RegisteredBPEntry +8 (h1; saves before v1.2 default to 0xce4).
BOL_BP_BAND = {{3300: '1.9 GHz', 3303: '1.9 GHz', 3304: '2.4 GHz', 3306: '2.4 GHz'}}
BOL_ANT_BAND = {{1: '1.9 GHz', 4: '2.4 GHz'}}
BOL_SYSTEM_MODE = {{0: 'Standalone (AES67)', 1: 'Standalone (Link)', 2: 'Artist'}}
BOL_TIME_SOURCE = {{0: 'Internal', 1: 'NTP', 2: 'PTP'}}
def _registration_text(rm):
    # RegistrationMode (JSON registrationMode): enabled when any of OTA / NFC / charger is on
    ways = [n for k, n in (('ota_enabled', 'OTA'), ('nfc_enabled', 'NFC'), ('charger_enabled', 'Charger')) if rm.get(k)]
    return ('Enabled: ' + ', '.join(ways) + ' (timeout %s)' % rm.get('timeout')) if ways else 'Disabled'

def _band_summary(bands):
    known = [b for b in bands if b]
    if not known:
        return ''
    n19, n24 = known.count('1.9 GHz'), known.count('2.4 GHz')
    lead = '1.9 GHz' if n19 >= n24 else '2.4 GHz'
    if n19 and n24:
        return '%s majority (1.9 GHz: %d, 2.4 GHz: %d)' % (lead, n19, n24)
    return 'All %s (%d)' % (lead, len(known))

def _bolero_view(parsed):
    # rows for the on-page tabs; the Excel workbook has the full detail
    net = parsed.get('network', {{}})
    pl, bpn, ch, tr = bol_faithful.build_name_maps(parsed)
    bps = parsed.get('beltpacks', {{}}).get('beltpacks', [])
    ants = parsed.get('antennas', {{}}).get('nodes', [])
    devs = parsed.get('audio_devices', {{}}).get('devices', [])
    chans = parsed.get('audio_channels', {{}}).get('channels', [])
    trigs = parsed.get('gpio', {{}}).get('triggers', [])
    profs = parsed.get('profiles', {{}}).get('profiles', [])
    dev_name = {{d['config_id']: d['name'] for d in devs}}
    prof_name = {{p['config']['id']: (p['name'] or p['config']['name']) for p in profs}}

    prio_on = {{}}
    for a in ants:
        for t in a['terms']:
            prio_on.setdefault(t, []).append(a['name'])

    def keys_text(cfg):
        out = []
        for i, k in enumerate(cfg.get('keys', [])):
            if k['function'] == 0:                       # unused key
                continue
            tgt = bol_faithful.resolve_target(k, pl, bpn, ch, tr)
            # key mode (Momentary / Latching / Auto) in brackets after the key
            # Standalone has 7 assignable keys; the 7th is only fixed to Reply in Artist-integrated mode
            out.append('%s [%s]: %s%s' % ('K%d' % (i + 1), k['mode_name'], k['function_name'],
                                          ' ' + tgt if tgt else ('' if k['function_name'] == 'Reply' else ' (no destination)')))
        return chr(10).join(out)                     # one key per line (shown with pre-line)

    beltpacks, pl_users = [], {{}}
    for e in bps:
        cfg = e['config']
        for k in cfg.get('keys', []):
            if k['target']['type'] == 2:
                pl_users.setdefault(k['target']['id'], set()).add(e['h0'])
        # 'User ID' is what the Bolero web GUI shows (BPConfig bpNumber); TermId (h0) is internal and 0-based
        beltpacks.append({{'id': cfg.get('bp_number'), 'name': cfg.get('name', ''), 'band': BOL_BP_BAND.get(e['h1'], ''),
                           'bp_type': e['h1'], 'ipei': e.get('ipei', ''),
                           'last_connected': bol_faithful.ts_text(e.get('last_connect_time')),
                           'keys': keys_text(cfg),
                           'profile': prof_name.get(cfg.get('id'), ''),
                           'priority_antennas': ', '.join(prio_on.get(e['h0'], []))}})

    # profiles: each beltpack stores the id of the profile it uses (BPConfig profileId)
    prof_prio = {{}}
    for a in ants:
        for pid in a['profiles']:
            prof_prio.setdefault(pid, []).append(a['name'])
    profiles = []
    for p in profs:
        pid = p['config']['id']
        users = [e['config'].get('name', '') for e in bps if e['config'].get('id') == pid]
        profiles.append({{'id': pid, 'name': p['name'] or p['config']['name'], 'bp_count': len(users),
                          'beltpacks': ', '.join(users), 'keys': keys_text(p['config']),
                          'priority_antennas': ', '.join(prof_prio.get(pid, []))}})

    antennas = []
    for a in ants:
        antennas.append({{'name': a['name'], 'label': a['label'],
                          'band': BOL_ANT_BAND.get(a['node_type'], 'Not an antenna (node type %d)' % a['node_type']),
                          'user_id': a['user_id'], 'node_id': '0x%x' % a['node_id'],
                          'priority_bps': ', '.join(bpn.get(t, '#%d' % t) for t in a['terms']),
                          'priority_profiles': ', '.join(prof_name.get(p, '#%d' % p) for p in a['profiles'])}})

    dev_by_id = {{d['config_id']: d for d in devs}}
    channels, pl_chans, talk_listen = [], {{}}, []
    bp_keys = bol_faithful.beltpack_keys_on_channels(parsed)
    for c in chans:
        cc = c['channel']
        d = dev_by_id.get(cc.get('device_config_id'), {{}})
        pls = [p['port']['id'] for p in cc.get('ports', []) if p['port']['type'] == 2]
        for p in pls:
            pl_chans.setdefault(p, []).append(cc.get('name', ''))
        # one row per connector side (a 4-Wire channel gives In and Out rows) so XLR 5 In / Out sit together
        mode = bol_faithful.channel_mode(cc, d)
        for conn1, direction1, dis, key in (bol_faithful.channel_side_rows(cc, d.get('devtype'))
                                            or [('No connector', '', False, (999, 9))]):
            channels.append({{'name': cc.get('name', ''), 'device': d.get('name', ''), 'connector': conn1,
                              'direction': direction1, 'status': 'Disabled' if dis else 'Enabled', 'mode': mode,
                              'partylines': ', '.join(pl.get(p, 'PL %s' % p) for p in pls),
                              'vox': bol_faithful.vox_text(cc.get('vox')), 'sort': (d.get('name', ''), key)}})
        conn, direction, key = bol_faithful.channel_connector_direction(cc, d.get('devtype'))
        rows, actions = bol_faithful.channel_talk_listen(cc, pl, bpn, ch, tr)
        rows = rows or [{{'destination': '(nothing assigned)', 'talk': '-', 'listen': '-', 'priority': ''}}]
        for i, r in enumerate(rows):
            talk_listen.append(dict(r, device=d.get('name', ''), connector=conn, direction=direction,
                                    sort=(d.get('name', ''), key, i), channel=cc.get('name', ''),
                                    actions='; '.join(actions) if i == 0 else '',
                                    bp_keys=bp_keys.get((c['port']['type'], c['port']['id']), '') if i == 0 else ''))

    devices = []
    for d in devs:
        # one line per connector pair: its mode and the channel(s) patched to it
        lines = []
        for pr in bol_faithful.connector_pairs(d):
            users = []
            for c in chans:
                cc = c['channel']
                if cc.get('device_config_id') != d['config_id']:
                    continue
                # a channel belongs to the pair its channelIndex points at; a side switched off on the device
                # is shown as disabled (a 4-Wire channel uses both sides and is named once)
                mine = [(sd, dis) for sd, n, dis in bol_faithful.channel_sides(cc) if n == pr['pair']]
                if mine:
                    any_off = any(dis for sd, dis in mine)
                    text = (', ' if any_off else ' + ').join(sd + (' disabled' if dis else '') for sd, dis in mine)
                    users.append('%s (%s)' % (cc.get('name', ''), text))
            label = ('XLR %d' if d['devtype'] == 1 else 'Channel %d') % pr['pair']
            lines.append('%s: %s%s' % (label, pr['mode_name'], ' - ' + ', '.join(users) if users else ''))
        if not lines:
            lines = ['No connectors set up on this device']
        devices.append({{'name': d['name'], 'type': d['devtype_name'], 'device_id': d['dev_id'],
                         'connectors': chr(10).join(lines),
                         'gpio': sum(1 for t in trigs if t.get('device_config_id') == d['config_id'])}})

    partylines = [{{'id': p['id'], 'name': p['name'], 'beltpacks': len(pl_users.get(p['id'], ())),
                    'channels': ', '.join(pl_chans.get(p['id'], []))}}
                  for p in parsed.get('partylines', {{}}).get('partylines', [])]

    flags = net.get('radio_flags', 0) or 0
    overview = [
        ['System', [
            ['Show name', net.get('show_name', '')],
            ['Network label', net.get('label', '')],
            ['System mode', BOL_SYSTEM_MODE.get(net.get('system_mode'), net.get('system_mode'))],
            ['Radio band (antennas with priority lists)',
             _band_summary([BOL_ANT_BAND.get(a['node_type']) for a in ants]) or 'None in this file (see Antenna Priority tab)'],
            ['Radio band (beltpacks)', _band_summary([b['band'] for b in beltpacks]) or 'No beltpacks'],
            ['Registration', _registration_text(net.get('registration_mode', {{}}))],
        ]],
        ['PINs & access', [
            ['Admin PIN (beltpack admin menu + web GUI Admin login)', bol_faithful.pin_text(net.get('admin_pin'))],
            ['OTA registration PIN', bol_faithful.pin_text(net.get('ota_pin'), net.get('admin_pin'))],
            ['Service PIN (6 digits, DECT region changes)', 'Not in show files - issued by Riedel support'],
            ['Note', bol_faithful.PIN_NOTE],
        ]],
        ['Contents', [
            ['Beltpacks', len(bps)], ['Antennas with priority lists', len(ants)], ['Audio devices', len(devs)],
            ['Audio channels', len(chans)], ['Partylines', len(pl)], ['Profiles', len(profs)],
            ['GPIO triggers', len(trigs)],
        ]],
        ['Radio & region', [
            ['DECT region', 'Set per device in the Service view - not saved in the show file'],
            ['Radio power (DECT)', bol_faithful.RADIO_POWER_NAMES.get(net.get('radio_power'), net.get('radio_power', ''))],
            ['Radio power (2.4 GHz)', bol_faithful.RADIO_POWER_NAMES.get(net.get('radio_power_2g4'), net.get('radio_power_2g4', ''))],
            ['High 2.4 GHz radio power', 'On' if flags >> 3 & 1 else 'Off'],
            ['Retransmit level', bol_faithful.RETRANSMIT_NAMES.get(net.get('radio_retransmission_limit'), net.get('radio_retransmission_limit', ''))],
            ['Frequency hopping mode (0-15)', net.get('frequency_hopping_mode', '')],
            ['Radio options on', bol_faithful.radio_flags_text(flags)],
        ]],
        ['Network & timing', [
            ['Audio multicast group', '.'.join(str(x) for x in net.get('audio_multicast_group', []))],
            ['Multicast TTL', net.get('multicast_ttl', '')],
            ['Time source', BOL_TIME_SOURCE.get(net.get('time_source'), net.get('time_source'))],
            ['PTP domain', net.get('ptp_domain', '')],
            ['DSCP (PTP / audio RTP / control)', ' / '.join(str(x) for x in net.get('dscp', []))],
        ]],
    ]
    channels = [dict((k, v) for k, v in r.items() if k != 'sort') for r in sorted(channels, key=lambda r: r['sort'])]
    return {{'show_name': net.get('show_name', ''), 'overview': overview, 'beltpacks': beltpacks, 'profiles': profiles,
             'antennas': antennas, 'devices': devices, 'channels': channels, 'partylines': partylines,
             'talk_listen': [dict((k, v) for k, v in r.items() if k != 'sort') for r in sorted(talk_listen, key=lambda r: r['sort'])],
             'gpio': [dict(g, enabled='Yes' if g['enabled'] else 'No', assigned=chr(10).join(g['assigned']) or '-',
                           timestamp=bol_faithful.ts_text(g['timestamp']))
                      for g in bol_faithful.gpio_chart(parsed)]}}

def _looks_like_bol(data, filename):
    # a .bol is a 7-byte header then a zlib stream (78 01), see bol_faithful.read_container
    return filename.lower().endswith('.bol') or data[7:9] == bytes([0x78, 0x01])

def _not_a_save(data, filename):
    # files that often sit next to the saves with the same name (Windows hides the extension)
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if data[:2] == b'PK':
        kind = 'an Excel workbook (.xlsx)' if ext in ('xlsx', 'xlsm', '') else 'a zip file (.%s)' % ext
        return ('this is %s, not a configuration save - probably an earlier export. Drop the original .bol or .Art '
                'file instead (in Explorer, View > Show > File name extensions tells them apart).' % kind)
    if data[:1] in (b'{{', b'['):
        return 'this is a JSON export, not a configuration save. Drop the original .bol or .Art file instead.'
    return None

def parse_file_for_ui(file_bytes, filename):
    data = bytes(file_bytes)
    wrong = _not_a_save(data, filename)
    if wrong:
        raise ValueError(wrong)
    if _looks_like_bol(data, filename):
        try:
            with open('temp.bol', 'wb') as f: f.write(data)
            parsed = bol_faithful.parse_file('temp.bol')
        except Exception as e:
            raise ValueError('not a readable Bolero .bol file (%s: %s)' % (type(e).__name__, str(e)[:120]))
        return json.dumps({{"type": "bolero", "view": _bolero_view(parsed)}}, default=_json_default)
    try:
        h, recs = artist_reader.parse_art(data)
    except Exception as e:
        raise ValueError('not a readable Artist .Art or Bolero .bol file (%s: %s)' % (type(e).__name__, str(e)[:120]))
    return json.dumps({{"type": "artist", "header": h, "view": _artist_view(data)}}, default=_json_default)

def generate_json_text(file_bytes, filename):
    data = bytes(file_bytes)
    if _looks_like_bol(data, filename):
        with open('temp.bol', 'wb') as f: f.write(data)
        return bol_faithful.to_json_text(bol_faithful.parse_file('temp.bol'), filename)
    return art_to_excel.art_to_json_text(data, filename)

def generate_excel_blob(file_bytes, filename):
    data = bytes(file_bytes)
    out_name = "out.xlsx"
    if os.path.exists(out_name): os.remove(out_name)
    if _looks_like_bol(data, filename):
        with open('temp.bol', 'wb') as f: f.write(data)
        bol_faithful.export_to_excel('temp.bol', out_name)
    else:
        with open('temp.art', 'wb') as f: f.write(data)
        art_to_excel.export_art_to_excel('temp.art', out_name)
    with open(out_name, 'rb') as f:
        return f.read()
                `);
                document.getElementById('status').innerHTML = '<span class="text-emerald-400 flex items-center"><svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg> Engine & Excel Export Ready</span>';
                engineReady = true;
                if (pendingFile) {{ const f = pendingFile; pendingFile = null; handleFile(f); }}
            }} catch (err) {{
                document.getElementById('status').innerText = "Engine Load Failed: " + err;
                console.error(err);
            }}
        }}

        initPyodide();

        const dropzone = document.getElementById('dropzone');
        const fileInput = document.getElementById('fileInput');
        
        dropzone.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', (e) => {{
            if (e.target.files.length) handleFile(e.target.files[0]);
            fileInput.value = '';                         // picking the same file again still fires 'change'
        }});

        // The whole window accepts a drop (not only the box), so a file can be dropped while the results are on
        // screen. A counter keeps the highlight steady while the pointer crosses child elements.
        let dragDepth = 0;
        const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes('Files');
        const setHighlight = (on) => ['border-blue-500', 'bg-slate-800'].forEach(c => dropzone.classList.toggle(c, on));
        window.addEventListener('dragenter', (e) => {{ if (hasFiles(e)) {{ e.preventDefault(); dragDepth++; setHighlight(true); }} }});
        window.addEventListener('dragover', (e) => {{ e.preventDefault(); if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'; }});
        window.addEventListener('dragleave', () => {{ if (--dragDepth <= 0) {{ dragDepth = 0; setHighlight(false); }} }});
        window.addEventListener('drop', (e) => {{
            e.preventDefault();
            dragDepth = 0; setHighlight(false);
            const files = e.dataTransfer?.files;
            if (files && files.length) {{
                handleFile(files[0]);
            }} else {{
                // e.g. a file inside a zip, or an email attachment: the browser is given no file to read
                setStatus("Nothing to open: save the file to a folder first, then drop it (or click the box to pick it).", true);
            }}
        }});

        function setStatus(text, isError) {{
            const s = document.getElementById('status');
            s.innerText = text;
            s.classList.toggle('text-red-400', !!isError);
        }}

        let pendingFile = null;                           // a file dropped before the engine finished loading

        async function handleFile(file) {{
            if (!file) return;
            if (!pyodide || !engineReady) {{
                pendingFile = file;
                setStatus(`Loading engine... ${{file.name}} will open when it is ready.`);
                return;
            }}

            setStatus(`Parsing ${{file.name}}...`);
            const buffer = await file.arrayBuffer();
            const uint8 = new Uint8Array(buffer);
            
            currentFileData = uint8;
            currentFileName = file.name;
            
            try {{
                // the name goes in as data, so quotes or backslashes in a file name can't break the call
                pyodide.globals.set("current_file_bytes", uint8);
                pyodide.globals.set("current_file_name", file.name);
                const jsonStr = pyodide.runPython(`parse_file_for_ui(current_file_bytes, current_file_name)`);
                const result = JSON.parse(jsonStr);
                renderResults(result, file.name);
                setStatus(`Loaded ${{file.name}}`);
            }} catch(err) {{
                const msg = String(err).trim().split('\\n').pop().replace(/^\\w+Error: /, '');   // last line of a Python traceback
                setStatus(`Could not read ${{file.name}}: ${{msg}}`, true);
                console.error(err);
            }}
        }}

        document.getElementById('btnExport').addEventListener('click', async () => {{
            if (!pyodide || !currentFileData) return;
            const btnText = document.getElementById('btnExportText');
            btnText.innerHTML = '<span class="loader mr-2"></span> Generating...';
            document.getElementById('btnExport').disabled = true;
            
            try {{
                // Yield thread to UI
                await new Promise(r => setTimeout(r, 50));
                
                pyodide.globals.set("current_file_bytes", currentFileData);
                pyodide.globals.set("current_file_name", currentFileName);
                const pyBytes = pyodide.runPython(`generate_excel_blob(current_file_bytes, current_file_name)`);
                const xlsxUint8 = pyBytes.toJs();
                pyBytes.destroy();
                
                const blob = new Blob([xlsxUint8], {{ type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }});
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = currentFileName + '.xlsx';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }} catch (err) {{
                alert("Failed to generate Excel file: " + err);
                console.error(err);
            }} finally {{
                btnText.innerText = 'Download Excel';
                document.getElementById('btnExport').disabled = false;
            }}
        }});

        // Download JSON: the same document as `export_tool.py --format json` (every decoded field)
        document.getElementById('btnJson').addEventListener('click', async () => {{
            if (!pyodide || !currentFileData) return;
            const btn = document.getElementById('btnJson'), btnText = document.getElementById('btnJsonText');
            btnText.innerHTML = '<span class="loader mr-2"></span> Generating...';
            btn.disabled = true;
            try {{
                await new Promise(r => setTimeout(r, 50));
                pyodide.globals.set("current_file_bytes", currentFileData);
                pyodide.globals.set("current_file_name", currentFileName);
                const text = pyodide.runPython(`generate_json_text(current_file_bytes, current_file_name)`);
                const blob = new Blob([text], {{ type: 'application/json' }});
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = currentFileName.replace(/\\.[^.]*$/, '') + '.json';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }} catch (err) {{
                const msg = String(err).trim().split('\\n').pop();
                setStatus(`Could not export JSON: ${{msg}}`, true);
                console.error(err);
            }} finally {{
                btnText.innerText = 'Download JSON';
                btn.disabled = false;
            }}
        }});

        function renderResults(res, filename) {{
            document.getElementById('results').classList.remove('hidden');
            const tabsDiv = document.getElementById('tabs');
            const contentDiv = document.getElementById('tab-content');
            tabsDiv.innerHTML = '';
            contentDiv.innerHTML = '';
            
            const tabs = [];
            
                const esc = (x) => String(x ?? '').replace(/[&<>"]/g, c => ({{'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}})[c]);
                // Sortable table: click a heading for ascending, again for descending, a third time for the original
                // order (as listed in the file / Excel). Natural order, so '1.10' follows '1.9' and 'Bay 10' follows 'Bay 2';
                // blank cells always go last. Ties keep the original order (Array.sort is stable).
                const collator = new Intl.Collator(undefined, {{ numeric: true, sensitivity: 'base' }});
                const sortableTable = (tab, rows, cols) => {{
                    const s = tab.sort || {{ key: null, dir: 0 }};
                    let shown = rows;
                    if (s.key) {{
                        const blank = x => x === null || x === undefined || x === '';
                        shown = [...rows].sort((a, b) => {{
                            const x = a[s.key], y = b[s.key];
                            if (blank(x) || blank(y)) return blank(x) - blank(y);
                            const c = (typeof x === 'number' && typeof y === 'number') ? x - y : collator.compare(String(x), String(y));
                            return c * s.dir;
                        }});
                    }}
                    const arrow = c => s.key === c.key ? (s.dir > 0 ? ' ▲' : ' ▼') : '<span class="opacity-30"> ↕</span>';
                    return `
                        <div class="overflow-x-auto max-h-[600px]"><table class="w-full text-left text-sm whitespace-nowrap">
                            <thead class="text-xs uppercase bg-slate-800 text-slate-300">
                                <tr>${{cols.map(c => `<th class="px-4 py-3 cursor-pointer select-none hover:text-white${{s.key === c.key ? ' text-blue-300' : ''}}" title="Sort by ${{esc(c.label)}}" onclick="window.sortBy('${{c.key}}')">${{esc(c.label)}}${{arrow(c)}}</th>`).join('')}}</tr>
                            </thead>
                            <tbody>
                                ${{shown.map(r => `<tr class="border-b border-slate-700 hover:bg-slate-800/50">${{cols.map(c => `<td class="px-4 py-3 ${{c.wrap ? 'whitespace-pre-line min-w-[18rem] ' : ''}}${{c.cls || ''}}">${{esc(c.fmt ? c.fmt(r[c.key]) : r[c.key])}}</td>`).join('')}}</tr>`).join('')}}
                            </tbody>
                        </table></div>`;
                }};

            if (res.type === 'artist') {{
                const v = res.view;

                tabs.push({{
                    name: 'Summary',
                    render: () => `<div class="p-6">
                        <h2 class="text-xl font-bold mb-4 text-white">System: ${{esc(v.system_name || filename)}}</h2>
                        <div class="grid grid-cols-2 gap-4">
                            <div class="glass-panel p-4 rounded"><p class="text-slate-400 text-sm">Director Version</p><p class="text-lg">${{esc(res.header.creator)}}</p></div>
                            <div class="glass-panel p-4 rounded"><p class="text-slate-400 text-sm">File Format Version</p><p class="text-lg font-mono">0x${{res.header.version.toString(16)}}</p></div>
                            <div class="glass-panel p-4 rounded"><p class="text-slate-400 text-sm">Frames</p><p class="text-lg">${{v.frames.length}}</p></div>
                            <div class="glass-panel p-4 rounded"><p class="text-slate-400 text-sm">Ports</p><p class="text-lg">${{v.ports.length}}</p></div>
                            <div class="glass-panel p-4 rounded"><p class="text-slate-400 text-sm">Conferences</p><p class="text-lg">${{v.conferences}}</p></div>
                            <div class="glass-panel p-4 rounded"><p class="text-slate-400 text-sm">Records</p><p class="text-lg">${{v.records}}</p></div>
                            <div class="glass-panel p-4 rounded"><p class="text-slate-400 text-sm">Panels</p><p class="text-lg">${{v.panel_count}}</p></div>
                            <div class="glass-panel p-4 rounded"><p class="text-slate-400 text-sm">Bolero</p><p class="text-lg">${{v.bolero_count}}</p></div>
                        </div>
                        <p class="text-slate-400 text-sm mt-4">Download the Excel workbook for every sheet (keys, functions, conferences, IFBs, logic, users, all records).</p>
                    </div>`
                }});

                const resTab = {{ name: 'Resources' }};
                resTab.render = () => `<p class="px-6 pt-4 pb-2 text-sm text-slate-400">How many of each frame, controller, power supply, card, panel, expansion panel, beltpack and port type the file contains. Artist 1024 frames store no power supplies.</p>` +
                    sortableTable(resTab, v.resources, [
                        {{ key: 'category', label: 'Category', cls: 'text-blue-300' }},
                        {{ key: 'item', label: 'Item', cls: 'font-medium text-white' }},
                        {{ key: 'quantity', label: 'Quantity', cls: 'font-bold text-emerald-400' }},
                    ]);
                tabs.push(resTab);

                const hasSerial = v.frames.some(n => n.serial);
                const frameCols = [
                    {{ key: 'address', label: 'Node #' }},
                    {{ key: 'name', label: 'Name', cls: 'font-medium text-white' }},
                    {{ key: 'model', label: 'Model', cls: 'font-medium text-blue-300' }},
                    ...(hasSerial ? [{{ key: 'serial', label: 'Serial', cls: 'font-mono text-slate-400', fmt: x => x || '-' }}] : []),
                    {{ key: 'ports', label: 'Ports', cls: 'font-bold text-emerald-400' }},
                    {{ key: 'soa', label: 'Ring Start (SOA)', cls: 'text-slate-400' }},
                    {{ key: 'noa', label: 'Ring Allocation (NOA)', cls: 'text-slate-400' }},
                ];
                const framesTab = {{ name: `Frames (${{v.frames.length}})` }};
                framesTab.render = () => sortableTable(framesTab, v.frames, frameCols);
                tabs.push(framesTab);

                const portCols = [
                    {{ key: 'port', label: 'Port', cls: 'font-mono text-slate-400' }},
                    {{ key: 'label', label: 'Label', cls: 'font-medium text-white' }},
                    {{ key: 'long_name', label: 'Long Name', cls: 'text-white' }},
                    {{ key: 'alias', label: 'Alias', cls: 'text-slate-300' }},
                    {{ key: 'subtitle', label: 'Subtitle', cls: 'text-slate-300' }},
                    {{ key: 'type', label: 'Type', cls: 'font-medium text-blue-300' }},
                    {{ key: 'node_bay', label: 'Node-Bay', cls: 'text-slate-400' }},
                ];
                const portsTab = {{ name: `Ports (${{v.ports.length}})` }};
                portsTab.render = () => sortableTable(portsTab, v.ports, portCols);
                tabs.push(portsTab);

                const panelsTab = {{ name: `Panels (${{v.panels.length}})` }};
                panelsTab.render = () => v.panels.length ? sortableTable(panelsTab, v.panels, [
                    {{ key: 'port', label: 'Port', cls: 'font-mono text-slate-400' }},
                    {{ key: 'label', label: 'Label', cls: 'font-medium text-white' }},
                    {{ key: 'long_name', label: 'Long Name', cls: 'text-white' }},
                    {{ key: 'alias', label: 'Alias', cls: 'text-slate-300' }},
                    {{ key: 'type', label: 'Panel', cls: 'font-medium text-blue-300' }},
                    {{ key: 'node_bay', label: 'Node-Bay', cls: 'text-slate-400' }},
                    {{ key: 'key_count', label: 'Keys used', cls: 'font-bold text-emerald-400' }},
                    {{ key: 'keys', label: 'Keys [mode]', cls: 'text-slate-300', wrap: true }},
                ]) : `<p class="p-6 text-slate-400">No panels with keys in this file.</p>`;
                tabs.push(panelsTab);

                const boleroTab = {{ name: `Bolero (${{v.bolero.length}})` }};
                boleroTab.render = () => v.bolero.length ? sortableTable(boleroTab, v.bolero, [
                    {{ key: 'port', label: 'Port', cls: 'font-mono text-slate-400' }},
                    {{ key: 'user_id', label: 'User ID', cls: 'font-mono text-slate-300' }},
                    {{ key: 'label', label: 'Label', cls: 'font-medium text-white' }},
                    {{ key: 'long_name', label: 'Long Name', cls: 'text-white' }},
                    {{ key: 'alias', label: 'Alias', cls: 'text-slate-300' }},
                    {{ key: 'subtitle', label: 'Subtitle', cls: 'text-slate-300' }},
                    {{ key: 'multicast', label: 'Multicast', cls: 'font-mono text-slate-400' }},
                    {{ key: 'node_bay', label: 'Node-Bay', cls: 'text-slate-400' }},
                    {{ key: 'keys', label: 'Keys [mode]', cls: 'text-slate-300', wrap: true }},
                ]) : `<p class="p-6 text-slate-400">No Bolero beltpack ports in this file.</p>`;
                tabs.push(boleroTab);

                const vfTab = {{ name: `Virtual Functions (${{v.vfs.length}})` }};
                vfTab.render = () => `<p class="px-6 pt-4 pb-2 text-sm text-slate-400">Functions that act without a key press: Always, On VOX (when the port's VOX opens), On Call (when the port is called).</p>` +
                    (v.vfs.length ? sortableTable(vfTab, v.vfs, [
                    {{ key: 'port', label: 'Port', cls: 'font-mono text-slate-400' }},
                    {{ key: 'label', label: 'Label', cls: 'font-medium text-white' }},
                    {{ key: 'long_name', label: 'Long Name', cls: 'text-white' }},
                    {{ key: 'type', label: 'Type', cls: 'text-blue-300' }},
                    {{ key: 'always', label: 'Always', cls: 'text-emerald-400', wrap: true }},
                    {{ key: 'vox', label: 'On VOX', cls: 'text-emerald-400', wrap: true }},
                    {{ key: 'on_call', label: 'On Call', cls: 'text-emerald-400', wrap: true }},
                ]) : `<p class="p-6 text-slate-400">No virtual functions in this file.</p>`);
                tabs.push(vfTab);
            }} else {{
                // Bolero: an overview, then one sortable table per kind of thing in the save
                const v = res.view;
                tabs.push({{
                    name: 'Network',
                    render: () => `<div class="p-6">
                        <h2 class="text-xl font-bold mb-4 text-white">Bolero Network: ${{esc(v.show_name || filename)}}</h2>
                        <div class="grid md:grid-cols-2 gap-4">
                            ${{v.overview.map(([title, items]) => `<div class="glass-panel p-4 rounded">
                                <p class="text-xs uppercase tracking-wide text-slate-400 mb-2">${{esc(title)}}</p>
                                <table class="w-full text-sm">${{items.map(([k, val]) => `<tr>
                                    <td class="py-1 pr-4 text-slate-400 align-top">${{esc(k)}}</td>
                                    <td class="py-1 text-white">${{esc(val === '' || val === null ? '-' : val)}}</td></tr>`).join('')}}</table>
                            </div>`).join('')}}
                        </div>
                        <p class="text-slate-400 text-sm mt-4">Download the Excel workbook for the full detail (every key, profile and GPIO trigger).</p>
                    </div>`
                }});

                const table = (label, rows, cols, note) => {{
                    const t = {{ name: `${{label}} (${{rows.length}})` }};
                    const intro = note ? `<p class="px-6 pt-4 pb-2 text-sm text-slate-400">${{note}}</p>` : '';
                    t.render = () => intro + (rows.length ? sortableTable(t, rows, cols) : `<p class="p-6 text-slate-400">No ${{label.toLowerCase()}} in this file.</p>`);
                    tabs.push(t);
                }};
                table('Beltpacks', v.beltpacks, [
                    {{ key: 'id', label: 'User ID', cls: 'font-mono text-slate-400' }},
                    {{ key: 'name', label: 'Name', cls: 'font-medium text-white' }},
                    {{ key: 'band', label: 'Band', cls: 'text-blue-300' }},
                    {{ key: 'ipei', label: 'IPEI', cls: 'font-mono text-slate-300' }},
                    {{ key: 'profile', label: 'Profile', cls: 'text-slate-300' }},
                    {{ key: 'keys', label: 'Keys [mode]', cls: 'text-slate-300', wrap: true }},
                    {{ key: 'priority_antennas', label: 'Priority on antennas', cls: 'text-slate-300', wrap: true }},
                ]);
                table('Profiles', v.profiles, [
                    {{ key: 'id', label: 'ID', cls: 'font-mono text-slate-400' }},
                    {{ key: 'name', label: 'Name', cls: 'font-medium text-white' }},
                    {{ key: 'bp_count', label: 'Beltpacks', cls: 'font-bold text-emerald-400' }},
                    {{ key: 'beltpacks', label: 'Used by', cls: 'text-slate-300', wrap: true }},
                    {{ key: 'keys', label: 'Keys [mode]', cls: 'text-slate-300', wrap: true }},
                    {{ key: 'priority_antennas', label: 'Priority on antennas', cls: 'text-slate-300', wrap: true }},
                ]);
                table('Antenna Priority', v.antennas, [
                    {{ key: 'name', label: 'Name', cls: 'font-medium text-white' }},
                    {{ key: 'label', label: 'Label', cls: 'text-slate-300' }},
                    {{ key: 'band', label: 'Band', cls: 'text-blue-300' }},
                    {{ key: 'user_id', label: 'User ID' }},
                    {{ key: 'node_id', label: 'Antenna ID', cls: 'font-mono text-slate-400' }},
                    {{ key: 'priority_bps', label: 'Priority beltpacks', cls: 'text-slate-300', wrap: true }},
                    {{ key: 'priority_profiles', label: 'Priority profiles', cls: 'text-slate-300', wrap: true }},
                ], 'A .bol save does not list the antennas themselves (the system finds them on the network). It only keeps antennas that have priority beltpacks or profiles set; the firmware drops an antenna from this list when its last priority entry is removed.');
                table('Devices', v.devices, [
                    {{ key: 'name', label: 'Name', cls: 'font-medium text-white' }},
                    {{ key: 'type', label: 'Type', cls: 'text-blue-300' }},
                    {{ key: 'device_id', label: 'Device ID', cls: 'font-mono text-slate-400' }},
                    {{ key: 'connectors', label: 'Connectors (mode - channels)', cls: 'text-slate-300', wrap: true }},
                    {{ key: 'gpio', label: 'GPIO triggers' }},
                ]);
                table('Audio Channels', v.channels, [
                    {{ key: 'device', label: 'Device', cls: 'text-blue-300' }},
                    {{ key: 'connector', label: 'Connector', cls: 'text-white' }},
                    {{ key: 'direction', label: 'In / Out', cls: 'font-medium text-white' }},
                    {{ key: 'status', label: 'Status', cls: 'text-slate-300' }},
                    {{ key: 'name', label: 'Channel', cls: 'font-medium text-white' }},
                    {{ key: 'mode', label: 'Mode', cls: 'text-slate-300' }},
                    {{ key: 'partylines', label: 'Partylines', cls: 'text-slate-300', wrap: true }},
                    {{ key: 'vox', label: 'VOX', cls: 'text-slate-400', wrap: true }},
                ]);
                // Talk = the channel's input goes to the destination; Listen = the destination comes out of it
                table('Talk / Listen', v.talk_listen, [
                    {{ key: 'device', label: 'Device', cls: 'text-blue-300' }},
                    {{ key: 'connector', label: 'Connector', cls: 'text-white' }},
                    {{ key: 'direction', label: 'In / Out', cls: 'text-slate-300' }},
                    {{ key: 'channel', label: 'Channel', cls: 'font-medium text-white' }},
                    {{ key: 'destination', label: 'Destination', cls: 'text-white' }},
                    {{ key: 'talk', label: 'Talk (input to it)', cls: 'text-emerald-400' }},
                    {{ key: 'listen', label: 'Listen (output from it)', cls: 'text-amber-300' }},
                    {{ key: 'priority', label: 'Priority', cls: 'text-slate-400' }},
                    {{ key: 'actions', label: 'Other actions', cls: 'text-slate-300', wrap: true }},
                    {{ key: 'bp_keys', label: 'Beltpack keys on it', cls: 'text-slate-300', wrap: true }},
                ]);
                table('GPIO', v.gpio, [
                    {{ key: 'device', label: 'Device', cls: 'text-blue-300' }},
                    {{ key: 'kind', label: 'GPI / GPO', cls: 'font-medium text-white' }},
                    {{ key: 'pin', label: 'Pin' }},
                    {{ key: 'enabled', label: 'Enabled', cls: 'text-slate-300' }},
                    {{ key: 'name', label: 'Name', cls: 'text-white' }},
                    {{ key: 'mode', label: 'Mode', cls: 'text-slate-400' }},
                    {{ key: 'assigned', label: 'Assigned functions', cls: 'text-emerald-400', wrap: true }},
                ], 'GPI = trigger input: its functions run while the input is active. GPO = trigger output: switched by Set Trigger functions on keys and audio channels.');
                table('Partylines', v.partylines, [
                    {{ key: 'id', label: 'ID', cls: 'font-mono text-slate-400' }},
                    {{ key: 'name', label: 'Name', cls: 'font-medium text-white' }},
                    {{ key: 'beltpacks', label: 'Beltpacks with a key on it', cls: 'font-bold text-emerald-400' }},
                    {{ key: 'channels', label: 'Audio channels', cls: 'text-slate-300', wrap: true }},
                ]);
            }}

            let currentTab = 0;
            const renderTabs = () => {{
                tabsDiv.innerHTML = tabs.map((t, i) => `
                    <div class="px-4 py-3 text-sm font-medium whitespace-nowrap transition-colors ${{i === currentTab ? 'tab-active' : 'tab-inactive'}}" onclick="window.switchTab(${{i}})">
                        ${{t.name}}
                    </div>
                `).join('');
                contentDiv.innerHTML = tabs[currentTab].render();
            }};
            
            window.switchTab = (idx) => {{ currentTab = idx; renderTabs(); }};
            // heading click on the current tab: ascending -> descending -> original order; kept per tab
            window.sortBy = (key) => {{
                const t = tabs[currentTab], s = t.sort || {{ key: null, dir: 0 }};
                t.sort = s.key !== key ? {{ key, dir: 1 }} : (s.dir > 0 ? {{ key, dir: -1 }} : {{ key: null, dir: 0 }});
                const scroller = contentDiv.querySelector('.overflow-x-auto'), left = scroller ? scroller.scrollLeft : 0;
                contentDiv.innerHTML = t.render();
                const again = contentDiv.querySelector('.overflow-x-auto');
                if (again) {{ again.scrollLeft = left; again.scrollTop = 0; }}
            }};
            renderTabs();
        }}
    </script>
</body>
</html>
"""
    with open('web_extractor_v2.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("Built web_extractor_v2.html with working Excel Blob (.toJs())")

if __name__ == '__main__':
    embed()
