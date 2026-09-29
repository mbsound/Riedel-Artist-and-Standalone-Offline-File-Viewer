#!/usr/bin/env python3
"""
Artist .Art -> Excel workbook, built only from artist_reader.py's decoded fields and helpers.

Every column comes from a named field or helper in artist_reader.py, each of which cites the Director code
it was decoded from. Nothing is guessed here: where the reader marks a value as reserved or unconfirmed, the
sheet says so. The last sheet, "All Records", lists every decoded field of every record, so values without a
dedicated column are still in the workbook.

Usage: python art_to_excel.py [-o OUTPUT] [FILE.Art ...]
"""
import glob
import json
import os
import pathlib
import sys
from collections import Counter, defaultdict

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import artist_reader as A

# ── styling ──────────────────────────────────────────────────────────────────────────────────────────
HDR_FILL = PatternFill('solid', fgColor='1F3864')
HDR_FONT = Font(bold=True, color='FFFFFF')
TITLE_FONT = Font(bold=True, size=14)
NOTE_FONT = Font(italic=True, color='555555')
CHANGED_FILL = PatternFill('solid', fgColor='FFF2CC')
MAX_CELL = 32000                                   # Excel's cell limit is 32767 characters


def _cell(v):
    if v is None:
        return ''
    if isinstance(v, bool):
        return 'Yes' if v else 'No'
    if isinstance(v, (list, tuple, dict)):
        v = json.dumps(v, default=str, ensure_ascii=False)
    if isinstance(v, str):
        v = ILLEGAL_CHARACTERS_RE.sub('', v)             # control characters Excel rejects
    if isinstance(v, str) and len(v) > MAX_CELL:
        v = v[:MAX_CELL] + ' …(truncated)'
    return v


def write_table(wb, title, headers, rows, note=None, changed_col=None, widths=None):
    """One sheet: title, optional note, header row, data rows; frozen header, filter, sensible widths."""
    ws = wb.create_sheet(title)
    ws.cell(1, 1, title).font = TITLE_FONT
    first = 3
    if note:
        ws.cell(2, 1, note).font = NOTE_FONT
    for c, h in enumerate(headers, 1):
        cell = ws.cell(first, c, h)
        cell.fill, cell.font = HDR_FILL, HDR_FONT
        cell.alignment = Alignment(wrap_text=True, vertical='top')
    for r, row in enumerate(rows, first + 1):
        for c, v in enumerate(row, 1):
            cell = ws.cell(r, c, _cell(v))
            cell.alignment = Alignment(vertical='top', wrap_text=isinstance(v, str) and len(v) > 60)
        if changed_col is not None and row[changed_col] is True:
            for c in range(1, len(headers) + 1):
                ws.cell(r, c).fill = CHANGED_FILL
    ws.freeze_panes = ws.cell(first + 1, 1)
    if rows:
        ws.auto_filter.ref = '%s%d:%s%d' % ('A', first, get_column_letter(len(headers)), first + len(rows))
    for c, h in enumerate(headers, 1):
        vals = [len(str(_cell(row[c - 1]))) for row in rows[:500]] + [len(h)]
        w = (widths or {}).get(h) or min(max(vals) + 2, 60)
        ws.column_dimensions[get_column_letter(c)].width = max(w, 8)
    return ws


# ── lookups ──────────────────────────────────────────────────────────────────────────────────────────
NO_REF = (None, 0, 0xffffffff, -1)

# Command class -> function name (Director's own names: RTTI CPhysCmd* classes and their descriptions)
CMD_NAMES = {
    0x0a: 'Route Audio', 0x13: 'Call to Port', 0x14: 'Listen to Port', 0x15: 'GPIO', 0x16: 'Call to Conference',
    0x17: 'Call to Group', 0x18: 'Reply', 0x25: 'Select Audiopatch', 0x26: 'Remote Key', 0x30: 'Edit Conference',
    0x31: 'Control Audiopatch', 0x32: 'Edit IFB', 0x33: 'Dim Speaker', 0x34: 'Dim Level', 0x35: 'Beep',
    0x36: 'Telephone Dial / Hang up', 0x44: 'Logic', 0x49: 'Telephone Keypad', 0x4d: 'Kill Mic',
    0x4e: 'Auto-Listen Off', 0x4f: 'Set Input/Output Gain', 0x5e: 'Sidetone', 0x5f: 'Send String',
    0x67: 'Call to IFB', 0x6b: 'Hot Mic', 0x503: 'Clone Output Port',
}

# Named command fields shown in the details column (booleans only when set)
CMD_DETAIL_KEYS = [
    'trunkcall_priority', 'monitoring', 'isolate', 'isolate_self', 'autolisten_from_dest', 'beep_dest_on_call',
    'allow_set_in_out_gain', 'duplex_call', 'disable_crosspoint_volume', 'allow_telephone_call',
    'allow_fixed_number', 'fixed_number', 'allow_phonebook', 'allow_dialpad', 'talk', 'listen',
    'use_second_channel', 'use_2nd_channel', 'allow_selecting_conf', 'allow_changing_dest_conf',
    'show_incoming_marker', 'disable_dest_volume_adjust', 'reply_from_conference', 'reply_duplex_call',
    'reply_scroll', 'source_uses_2nd_channel', 'dest_uses_2nd_channel', 'disable_crosspoint_vol_adjust',
    'dim_speaker_by', 'dim_value', 'press_key', 'press_key_lever_up', 'lock_key', 'set_signaling_marker',
    'signaling_marker', 'set_key_text', 'signal_text', 'key_function', 'dial_function', 'keypad_function',
    'keypad_text', 'gain_mode', 'enable_speaker_mode', 'enable_headset_mode', 'applies_to_2nd_channel',
    'norm_sidetone_level', 'send_text', 'output_to_clone_second_channel', 'cloned_output_second_channel',
    'ifb_mode',
]


class Ctx:
    """Parsed file plus the lookups every sheet needs."""

    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.header, self.recs = A.parse_art(self.path.read_bytes())
        self.byid = {r['id']: r for r in self.recs}
        self.by_class = defaultdict(list)
        for r in self.recs:
            self.by_class[r['class']].append(r)
        self.reader = {r['id']: A.READERS[r['class']].__name__ for r in self.recs}
        self.ports = [r for r in self.recs if r['class'] in A.PORT_TYPE_NAMES]
        self.cards = [r for r in self.recs if self.reader[r['id']].startswith('read_card')]
        self.nodes = self.by_class[3]
        self.net = (self.by_class[2] or [{}])[0]
        self.keys = [r for r in self.recs if self.reader[r['id']] == 'read_key']
        self.cmd_owner = {}                          # command id -> text of where it lives
        for k in self.keys:
            for c in k.get('commands') or []:
                self.cmd_owner[c] = self.key_place(k)
        for v in self.by_class[0x24]:
            for c in v.get('commands') or []:
                self.cmd_owner[c] = 'Virtual function %s on %s' % (v.get('vf_slot'), self.name(v.get('panel')))
        for d in self.by_class[0x41]:
            for c in d.get('commands') or []:
                self.cmd_owner[c] = 'Logic destination %s' % d.get('name', '')
        for s in self.by_class[0x10]:
            for i, e in enumerate(s.get('entries') or [], 1):
                self.cmd_owner[e['command']] = 'Scroll list %s entry %d' % (s.get('name', ''), i)

    def port_sort_key(self, p):
        """Frame name, bay, then Director's Port # (numbered per card; '1.10' sorts after '1.9')."""
        card = A.port_card(p, self.byid) if p.get('card') in self.byid else {}
        ps = p.get('port_strings') or []
        num = ps[1] if len(ps) > 1 else ''
        return (str(self.name(card.get('node'))) if card else '', card.get('slot') or 0, card.get('sub_bay') or 0,
                [(0, int(t), '') if t.isdigit() else (1, 0, t) for t in num.split('.')], p['id'])

    # names
    def port_label(self, p):
        num = (p.get('port_strings') or ['', ''])[1] if len(p.get('port_strings') or []) > 1 else ''
        return ('%s %s' % (num, p.get('port_str') or p.get('name') or '')).strip()

    def name(self, oid, what='object'):
        """Readable name for any object id."""
        if oid in NO_REF:
            return ''
        o = self.byid.get(oid)
        if o is None:
            return '(%s id %d not in file)' % (what, oid)
        if o['class'] in A.PORT_TYPE_NAMES:
            return self.port_label(o)
        if o['class'] in A.EXPANSION_SLOTS:
            return self.expansion_label(o)
        for k in ('long_name', 'name', 'label'):
            if o.get(k):
                return o[k]
        return '%s %d' % (o.get('category', 'object'), oid)

    def expansion_label(self, e):
        model = A.EXPANSION_NAMES.get(e['class']) or A.PORT_TYPE_NAMES.get(e['class']) or 'Expansion'
        return '%s: %s #%s' % (self.name(e.get('host_panel')) or 'expansion', model, e.get('expansion_address', ''))

    def key_counts(self):
        n = Counter(k['holder'] for k in self.keys)
        return n

    def key_place(self, k):
        n = self.key_counts_cache().get(k['holder'], 0)
        key_no, bank = key_number(k['slot'], n)
        return '%s, key %d%s' % (self.name(k['holder']), key_no, '' if bank == 1 else ' (bank %d)' % bank)

    _kc = None

    def key_counts_cache(self):
        if self._kc is None:
            self._kc = self.key_counts()
        return self._kc


def key_number(slot, slots_on_holder):
    """Stored slot -> (key number, bank). Panels store two slots per key (key count = slots / 2, matching every
    confirmed panel); the lower half holds bank 1. The bank split is inferred from usage, not from Director."""
    half = slots_on_holder // 2 if slots_on_holder >= 2 else slots_on_holder
    if half <= 0:
        return slot + 1, 1
    return slot % half + 1, 1 + slot // half


def describe_command(cmd, ctx):
    """(function, target, details) for one command record, from its decoded fields."""
    cls = cmd['class']
    fn = CMD_NAMES.get(cls, 'Command class 0x%x' % cls)
    g = cmd.get
    port = lambda k: ctx.name(g(k)) or '(no destination)'
    if cls in (0x13, 0x14):
        if g('target') in NO_REF and (g('trunk_name') or g('trunk_port_address')):
            target = 'Trunk: %s (net %s, port %s)' % (g('trunk_name', ''), g('trunk_net_address'), g('trunk_port_address'))
        else:
            target = port('target')
    elif cls == 0x16:
        target = ctx.name(g('conference'), 'conference')
    elif cls == 0x17:
        target = ctx.name(g('target_group', g('group')), 'group')
    elif cls == 0x67:
        target = ctx.name(g('ifb'), 'IFB')
    elif cls == 0x0a:
        target = '%s -> %s' % (port('source'), port('destination'))
    elif cls == 0x34:
        target = '%s -> %s' % (port('source'), port('destination'))
    elif cls == 0x503:
        target = '%s -> %s' % (port('source'), port('dest'))
    elif cls == 0x15:
        target = ctx.name(g('gpio'), 'GPIO')
    elif cls == 0x44:
        target = ctx.name(g('logic'), 'logic destination')
    elif cls == 0x25:
        target = ctx.name(g('audiopatch'), 'audio patch')
    elif cls == 0x26:
        k = ctx.byid.get(g('target_key'))
        target = ctx.key_place(k) if k and k.get('holder') is not None else ctx.name(g('target_key'), 'key')
    elif cls in (0x31, 0x33, 0x35, 0x4f, 0x6b):
        target = port('target')
    elif cls == 0x18:
        target = '(reply to last caller)'
    else:
        target = ''
    details = []
    for k in CMD_DETAIL_KEYS:
        v = g(k)
        if v is None or v is False or v == '':
            continue
        details.append(k.replace('_', ' ') if v is True else '%s: %s' % (k.replace('_', ' '), v))
    if g('created_by') not in NO_REF:
        details.append('created by: %s' % ctx.name(g('created_by')))
    return fn, target, '; '.join(details)


def ip(v):
    if v in (None, ''):
        return ''
    if isinstance(v, str):
        return v
    return '.'.join(str(b) for b in (v & 0xffffffff).to_bytes(4, 'big'))


# ── sheets ───────────────────────────────────────────────────────────────────────────────────────────
def sheet_summary(wb, ctx):
    ws = wb.active
    ws.title = 'Summary'
    ws.cell(1, 1, 'Artist configuration: %s' % ctx.path.name).font = TITLE_FONT
    h = ctx.header
    rows = [
        ('File', ctx.path.name),
        ('Saved by', h.get('creator', '')),
        ('File format version', '0x%x' % h.get('version', 0)),
        ('Records', len(ctx.recs)),
        ('Objects created or changed in the session that produced this save', sum(1 for r in ctx.recs if r.get('changed_last_session'))),
        ('Panels', sum(n for cat, _, n in resource_counts(ctx) if cat == 'Panels')),
        ('Bolero beltpacks', sum(n for cat, _, n in resource_counts(ctx) if cat == 'Bolero beltpacks')),
        ('', ''),
        ('Record type', 'Count'),
    ]
    rows += sorted(Counter(r.get('category', '?') for r in ctx.recs).items(), key=lambda kv: -kv[1])
    for r, (a, b) in enumerate(rows, 3):
        ws.cell(r, 1, a)
        ws.cell(r, 2, _cell(b))
        if a in ('Record type',):
            ws.cell(r, 1).font = ws.cell(r, 2).font = Font(bold=True)
    ws.cell(len(rows) + 5, 1, 'Rows highlighted in yellow on the other sheets were created or changed in the session '
                              'that produced this save (Director marks every edited object and clears the mark on '
                              'each load and save).').font = NOTE_FONT
    ws.column_dimensions['A'].width = 70
    ws.column_dimensions['B'].width = 40


def sheet_system(wb, ctx):
    net = ctx.net
    rows = []
    sections = [('General', A.net_general), ('Panel defaults', A.net_panel_defaults),
                ('Call and key defaults', A.net_call_key_defaults), ('Port settings', A.net_port_settings),
                ('VoIP defaults', A.net_voip_defaults), ('Monitor defaults', A.net_monitor_defaults)]
    for title, fn in sections:
        try:
            vals = fn(net)
        except Exception as e:                       # a helper that cannot read this file's layout
            vals = {'(not available)': str(e)}
        for k, v in vals.items():
            rows.append((title, k, v))
    for w in ctx.by_class[1]:                        # configuration root
        for k, label in (('trunking_net_address', 'Trunking net address (0 disables Trunking)'),
                         ('stage_net_address', 'Stage net address (0 disables Stage)'),
                         ('stage_registration_url', 'Stage registration URL'), ('stage_base_url', 'Stage base URL'),
                         ('allow_more_logic_sources_per_destination', 'Allow more logic sources per destination'),
                         ('allow_more_logic_destinations_per_node', 'Allow more logic destinations per node'),
                         ('allow_more_members_per_conference', 'Allow more members per conference')):
            if k in w:
                rows.append(('Configuration root', label, w[k]))
        for s in w.get('setups') or []:
            rows.append(('Configuration root', 'Setup "%s"' % s['name'],
                         'panels A: %s | panels B: %s' % (', '.join(ctx.name(i) for i in s['a']),
                                                          ', '.join(ctx.name(i) for i in s['b']))))
    write_table(wb, 'System', ['Section', 'Setting', 'Value'], rows,
                note='Director\'s wording from the reader helpers (net_general, net_panel_defaults, ...).')


def sheet_markers(wb, ctx):
    try:
        marks = A.net_markers(ctx.net)
    except Exception:
        marks = []
    if not marks:
        return
    # Director's "Marker definition" table in plain words: how a panel key lights up in each key state
    cols = [('marker', 'Key state'), ('priority', 'Priority'), ('persistence_timeout_s', 'Stays lit after event (s)'),
            ('user_name', 'Custom name'), ('2000 series base color', '2000-series colour'),
            ('2000 series flash to color', '2000-series flashes to'),
            ('1000 series background', '1000-series key background'),
            ('1000 series crosspoint level color', '1000-series level colour'),
            ('1000 series muted crosspoint level color', '1000-series muted level colour'),
            ('1000 series flash', '1000-series flashing'),
            ('Show crosspoint level in foreground', '1000-series level shown in front'),
            ('RIF LED state', 'RIF LED')]

    def plain(key, v):
        if key == '1000 series background' and isinstance(v, str) and len(set(v.split())) == 1:
            return v.split()[0]                       # the same colour on all 8 background segments
        return v
    rows = [[plain(k, m.get(k)) for k, _ in cols] for m in marks]
    write_table(wb, 'Key Light Colours', [h for _, h in cols], rows,
                note='How a panel key lights up in each key state, system-wide (Director: Marker definition). '
                     'Priority decides which state shows when several apply (lower numbers are the active states). '
                     'Usually left at factory values.')


def sheet_nodes(wb, ctx):
    ports_on = Counter(A.port_card(p, ctx.byid).get('node') for p in ctx.ports if p.get('card') in ctx.byid)
    rows = []
    for n in ctx.nodes:
        rows.append([
            n.get('name'), n.get('node_address'), n.get('node_id'),
            A.NODE_TYPE_NAMES.get(n.get('node_type'), 'type %s' % n.get('node_type')),
            n.get('serial_number'), ports_on.get(n['id'], 0), n.get('soa'), n.get('noa'),
            ', '.join(ctx.name(c) for c in n.get('controllers') or [] if c not in NO_REF),
            ', '.join(ctx.name(c) for c in n.get('power_supplies') or [] if c not in NO_REF),
            ', '.join(n.get('error_alarms') or []), ', '.join(n.get('relay1_alarms') or []),
            ', '.join(n.get('relay2_alarms') or []),
            ', '.join(ctx.name(i) for i in n.get('logic_destinations') or []),
            n.get('changed_last_session'),
        ])
    write_table(wb, 'Nodes', ['Name', 'Node address', 'Node ID', 'Frame type', 'Serial number', 'Ports configured',
                              'Ring start (SOA)', 'Ring allocation (NOA)',
                              'Controllers', 'Power supplies', 'Error alarms', 'Relay 1 alarms', 'Relay 2 alarms',
                              'Logic destinations', 'Changed last session'], rows, changed_col=14)
    links = [[ctx.name(l.get('node_a')), ctx.name(l.get('node_b')), len(l.get('drawing_points') or []),
              l.get('changed_last_session')] for l in ctx.by_class[5]]
    if links:
        write_table(wb, 'Fibre Links', ['Node A', 'Node B', 'Drawing waypoints', 'Changed last session'], links,
                    changed_col=3)


def card_network(c):
    """Network settings of a card, in the reader's names."""
    out = []
    for i, m in enumerate(c.get('media') or [], 1):
        bits = ['IP %s/%s gw %s' % (ip(m.get('ip')), ip(m.get('mask')), ip(m.get('gateway')))]
        if m.get('dhcp'):
            bits.append('DHCP')
        for k, lab in (('sip_port', 'SIP port'), ('dscp', 'DSCP'), ('igmp_version', 'IGMP'), ('network_speed', 'speed')):
            if m.get(k) is not None:
                bits.append('%s %s' % (lab, m[k]))
        out.append('Media %d: %s' % (i, ', '.join(bits)))
    p = c.get('ptp_settings')
    if p:
        out.append('PTP: role %s, mode %s, domain %s, priority 1/2 %s/%s' % (
            p.get('role_name'), p.get('mode_name'), p.get('domain'), p.get('priority1'), p.get('priority2')))
    n = c.get('nmos')
    if n:
        out.append('NMOS: %s, port %s, registration %s' % ('enabled' if n.get('enabled') else 'disabled',
                                                           n.get('port'), n.get('registration_mode')))
    d = c.get('dns')
    if d and (d.get('primary') or d.get('secondary') or d.get('suffix')):
        out.append('DNS: %s / %s %s' % (ip(d.get('primary')), ip(d.get('secondary')), d.get('suffix') or ''))
    if c.get('bolero_discovery_ip'):
        out.append('Bolero discovery %s:%s' % (ip(c['bolero_discovery_ip']), c.get('bolero_discovery_port')))
    if c.get('ip') and not c.get('media'):
        out.append('IP %s/%s gw %s%s' % (ip(c.get('ip')), ip(c.get('mask')), ip(c.get('gateway')),
                                          ' (DHCP)' if c.get('voip_dhcp') else ''))
    for k in ('up_interface', 'down_interface', 'frame_length', 'channels', 'dante_name'):
        if c.get(k) not in (None, ''):
            out.append('%s: %s' % (k.replace('_', ' '), c[k]))
    return ' | '.join(out)


def sheet_cards(wb, ctx):
    """One row per card, controller and power supply, with its role in the frame.

    - Controllers and power supplies come from each frame's own lists (node 'controllers' / 'power_supplies':
      CPU cards, PSUs; on Performer frames the second controller position can hold the ELA-OP card).
    - Artist 1024 frames store no controller or PSU objects (both lists are 0); their two NICs (CPhysClientNic,
      0x10c) are the frame controllers. (A NIC also keeps its own copy of the bay table, nic_slots: bay id and two
      counts that look like channels in use / allocated, but they do not always agree with the cards, so they are
      not shown.)
    - Each SIC card on a 1024 frame owns CPhysClientSubSic (0x10d) records (parent = base_58), numbered port
      groups of up to 8 ports of one kind. They are folded into their card as 'Port groups' instead of being
      listed as cards of their own. Director keeps no power-supply objects for 1024 frames."""
    ports_on = Counter(p.get('card') for p in ctx.ports)
    groups_of = defaultdict(list)                        # SIC card id -> [(group no, count, port types)]
    for sub in ctx.cards:
        if sub['class'] != 0x10d or not ports_on.get(sub['id']):
            continue
        kinds = Counter()
        for p in ctx.ports:
            if p.get('card') == sub['id']:
                try:
                    kinds[A.port_type(p, ctx.byid)] += 1
                except Exception:
                    kinds[A.PORT_TYPE_NAMES.get(p['class'], 'class 0x%x' % p['class'])] += 1
        groups_of[sub.get('base_58')].append(((sub.get('slot') or 0) + 1, ports_on[sub['id']], kinds))

    def model_of(c, node):
        try:
            return A.card_model(c, node)
        except Exception:
            return 'class 0x%x' % c['class']

    rows = []
    listed = set()
    for node in ctx.nodes:                               # controllers and power supplies, from the frame
        for ri, (role, key) in enumerate((('Controller', 'controllers'), ('Power supply', 'power_supplies'))):
            for i, oid in enumerate(node.get(key) or []):
                c = ctx.byid.get(oid)
                if not c:
                    continue
                listed.add(oid)
                r = role if c['class'] != 0x201 else 'GPIO card'
                label = ('Controller %s' % 'AB'[i]) if key == 'controllers' and i < 2 else (
                    'PSU %d' % (i + 1) if key == 'power_supplies' else 'Controller %d' % (i + 1))
                rows.append(((str(node.get('name')), 0, ri, i), [node.get('name'), label,
                             None, r, model_of(c, node), c.get('name'), None, '', '0x%x' % c['class'], None, None,
                             card_network(c), c.get('device_uuid'), c.get('changed_last_session')]))
    for c in ctx.cards:
        if c['class'] == 0x10d or c['id'] in listed:
            continue                                     # port groups are folded into their SIC card
        node = ctx.byid.get(c.get('node'), {})
        model = model_of(c, node)
        if c['class'] == 0x10c:
            role = 'Controller (NIC)'
        elif c['class'] == 0x201:
            role = 'GPIO card'
        else:
            role = 'I/O card'
        groups = sorted(groups_of.get(c['id'], []))
        n_ports = ports_on.get(c['id'], 0) + sum(n for _, n, _ in groups)
        group_text = '; '.join('Group %d: %s' % (g, ', '.join('%d x %s' % (k, t) for t, k in kinds.most_common()))
                               for g, _, kinds in groups)
        rows.append(((str(ctx.name(c.get('node'))), 1, c.get('slot', 0), c.get('sub_bay') or 0),
                     [ctx.name(c.get('node')), (c.get('slot') or 0) + 1, c.get('sub_bay'), role, model, c.get('name'),
                      n_ports if role == 'I/O card' or n_ports else None, group_text, '0x%x' % c['class'],
                      c.get('start_port'), c.get('allocated_ports'), card_network(c), c.get('device_uuid'),
                      c.get('changed_last_session')]))
    rows = [r for _, r in sorted(rows, key=lambda x: x[0])]
    write_table(wb, 'Cards', ['Node', 'Bay', 'Sub-bay', 'Role', 'Model', 'Name', 'Ports', 'Port groups (SIC cards)',
                              'Class', 'Start port', 'Allocated ports', 'Network / sync', 'Device UUID',
                              'Changed last session'],
                rows, changed_col=13,
                note='One row per card, controller and power supply. On Artist 1024 frames the two NICs are the '
                     'controllers; Director stores no power-supply objects for 1024 frames. A SIC card\'s ports '
                     'sit in numbered port groups, listed on the card.')


def port_details(p, ctx):
    """Type-specific settings of a port."""
    out = []
    s = p.get('port_d0c2c0')
    if s:
        out.append('VoIP: local SIP ID %s, remote %s / %s, codec %s, packet %s, buffer %s, VAD %s%s' % (
            s.get('local_sip_id'), s.get('remote_host'), s.get('remote_sip_id'), s.get('audio_codec'),
            s.get('audio_packet_size'), s.get('receive_buffer_size'), s.get('voice_act_detection'),
            ', STUN %s' % s['stun_server'] if s.get('stun_server') else ''))
    if p['class'] == 0x502:
        out.append('SIP: user %s, display %s, domain %s, proxy %s, auth user %s, auth password %s, transport %s, '
                   're-register %s s%s' % (p.get('sip_username'), p.get('display_name'), p.get('domain_server'),
                                          p.get('proxy_server'), p.get('auth_username'), p.get('auth_password'),
                                          p.get('sip_transport'), p.get('reregister_time_s'),
                                          ', STUN %s' % p['stun_server'] if p.get('stun_server') else ''))
    om2 = p.get('output_media_2')
    if om2:
        out.append('Bolero: multicast %s:%s, user ID %s, port to Bolero %s' % (
            om2.get('multicast'), om2.get('multicast_port'), om2.get('bolero_user_id'),
            om2.get('multicast_port_to_bolero')))
    for k, lab in (('stream_rx', 'AES67 in'), ('stream_tx', 'AES67 out')):
        st = p.get(k)
        if st:
            out.append('%s: %s:%s, %s ch, packet %s us, PT %s%s%s' % (
                lab, ip(st.get('multicast')), st.get('multicast_port'), st.get('channels'), st.get('packet_time'),
                st.get('payload_type'), ', RTSP %s' % st['rtsp_uri'] if st.get('rtsp_uri') else '',
                ', play mode %s' % st['play_mode_name'] if st.get('play_mode_name') else ''))
    a = p.get('audio_settings')
    if a:
        out.append('AES67 settings: %s:%s, packet %s, buffer %s%s' % (
            ip(a.get('ip_address')), a.get('listen_port'), a.get('packet_time'), a.get('receive_buffer'),
            ', play mode %s' % a['play_mode_name'] if a.get('play_mode_name') else ''))
    if p['class'] == 0x508:
        out.append('Codec: auto answer %s, auto dial %s %s' % (p.get('auto_answer'), p.get('auto_dial_enabled'),
                                                               p.get('auto_dial_number') or ''))
    if p.get('input_channel') is not None or p.get('output_channel') is not None:
        out.append('NSA channels in/out %s/%s' % (p.get('input_channel', '-'), p.get('output_channel', '-')))
    for k in ('phone_number_1', 'phone_number_2'):
        if p.get(k):
            out.append('%s: %s' % (k.replace('_', ' '), p[k]))
    ui = p.get('panel_ui')
    if ui:
        bits = ['%s %s' % (k.replace('_', ' '), ui[k]) for k in (
            'panel_operation_mode', 'show_colors_on', 'enable_colors', 'show_volume_bars',
            'incoming_call_signalization', 'live_view_password', 'panel_menu_pin') if k in ui]
        out.append('Panel UI: ' + ', '.join(bits))
    if p.get('adjust_from_command_elements'):
        out.append('Audio patch elements adjustable from command: %s' % p['adjust_from_command_elements'])
    return ' | '.join(out)


def sheet_ports(wb, ctx):
    holders = set(k['holder'] for k in ctx.keys)
    panel_cols = None
    rows = []
    for p in sorted(ctx.ports, key=ctx.port_sort_key):
        try:
            node_bay, ptype = A.port_node_bay(p, ctx.byid), A.port_type(p, ctx.byid)
        except Exception:
            node_bay, ptype = '', A.PORT_TYPE_NAMES.get(p['class'], 'class 0x%x' % p['class'])
        ps = p.get('port_strings') or []
        settings = A.panel_settings(p) if p['id'] in holders else {}
        if settings and panel_cols is None:
            panel_cols = list(settings.keys())
        rows.append((p, [ps[1] if len(ps) > 1 else '', p.get('name'), p.get('port_str'), p.get('alias'),
                         p.get('port_str2'), ptype, node_bay, p.get('trunk_address'),
                         '%+.1f dB' % p['input_gain_db'] if 'input_gain_db' in p else '',
                         '%+.1f dB' % p['output_gain_db'] if 'output_gain_db' in p else '',
                         A.room_code_label(p.get('room_code')), p.get('room_mode'), p.get('second_audio_channel'),
                         p.get('keypad_shortcut'), p.get('media_interface'), ctx.name(p.get('phone_book')),
                         ', '.join(ctx.name(s) for s in p.get('scroll_lists') or [] if s not in NO_REF),
                         port_details(p, ctx)], settings))
    panel_cols = panel_cols or []
    headers = ['Port', 'Local 8-char label', 'Long name', 'Alias', 'Subtitle', 'Port type', 'Node-Bay',
               'Trunking object address', 'Input gain', 'Output gain', 'Room code', 'Room mode', '2nd audio channel',
               'Keypad shortcut', 'Media interface', 'Phone book', 'Scroll lists', 'Type-specific settings']
    out = [base + [st.get(c, '') for c in panel_cols] + [p.get('changed_last_session')] for p, base, st in rows]
    write_table(wb, 'Ports', headers + panel_cols + ['Changed last session'], out,
                changed_col=len(headers) + len(panel_cols),
                note='Port, labels, long name, subtitle, type, Node-Bay, trunking address, gains and room code '
                     'match Director\'s Ports grid (tools/check_ports_csv.py). Panel settings only for ports with keys.')


def sheet_keys(wb, ctx):
    """Keys as columns: one row per panel / beltpack / expansion panel, and Label / Mode / Function for every key
    position used anywhere in the file (bank 1 keys first, then bank 2). Empty keys stay blank."""
    counts = ctx.key_counts_cache()
    per_holder = defaultdict(dict)                       # holder id -> {(bank, key): (label, mode, functions)}
    for k in ctx.keys:
        cmds = [ctx.byid[c] for c in k.get('commands') or [] if c in ctx.byid]
        if not cmds and not k.get('label'):
            continue                                     # empty key slot
        key_no, bank = key_number(k['slot'], counts.get(k['holder'], 0))
        fns = ' | '.join('%s: %s' % (f, t) if t else f for f, t, _ in (describe_command(c, ctx) for c in cmds))
        per_holder[k['holder']][(bank, key_no)] = (k.get('label'), k.get('mode'), fns or '(no function)')
    positions = sorted({pos for keys in per_holder.values() for pos in keys})
    headers = ['Port', 'Label', 'Long name', 'Type', 'Keys used']
    for bank, n in positions:
        tag = 'Key %d' % n + ('' if bank == 1 else ' bank %d' % bank)
        headers += ['%s Label' % tag, '%s Mode' % tag, '%s Function' % tag]
    rows = []
    for hid, keys in per_holder.items():
        h = ctx.byid.get(hid, {})
        host = h
        if ctx.reader.get(hid) == 'read_expansion':
            host = ctx.byid.get(h.get('host_panel'), {})
            model = A.EXPANSION_NAMES.get(h.get('class')) or 'Expansion panel'
            label, long_name = host.get('name') or '', '%s #%s on %s' % (model, h.get('expansion_address', ''),
                                                                        host.get('port_str') or host.get('name') or '')
            typ = model
        else:
            label, long_name = h.get('name') or '', h.get('port_str') or ''
            try:
                typ = A.port_type(h, ctx.byid)
            except Exception:
                typ = A.PORT_TYPE_NAMES.get(h.get('class'), 'class 0x%x' % h.get('class', 0))
        ps = host.get('port_strings') or []
        port = ps[1] if len(ps) > 1 else ''
        try:
            order = ctx.port_sort_key(host) if host.get('class') in A.PORT_TYPE_NAMES else ('~',)
        except Exception:
            order = ('~',)
        is_bp = host.get('class') == 0x440
        row = [port, label, long_name, typ, len(keys)]
        for pos in positions:
            row += list(keys.get(pos, ('', '', '')))
        rows.append(((is_bp, order, host is not h, h.get('expansion_address') or 0), row))
    rows = [r for _, r in sorted(rows, key=lambda x: x[0])]
    ws = write_table(wb, 'Keys', headers, rows,
                     note='One row per panel, beltpack and expansion panel; Label / Mode / Function for each key. '
                          'Bank 2 = the upper half of the stored key slots (inferred from usage). '
                          'Per-key colours, timeouts and other options are on the Key Details sheet.')
    ws.freeze_panes = 'F4'                               # keep the panel columns in view while scrolling right


def sheet_key_details(wb, ctx):
    counts = ctx.key_counts_cache()
    rows, funcs = [], []
    for k in sorted(ctx.keys, key=lambda k: (ctx.name(k['holder']), k['slot'])):
        key_no, bank = key_number(k['slot'], counts.get(k['holder'], 0))
        cmds = [ctx.byid[c] for c in k.get('commands') or [] if c in ctx.byid]
        desc = [describe_command(c, ctx) for c in cmds]
        if not cmds and not k.get('label'):
            continue                                     # empty key slot
        rows.append([ctx.name(k['holder']), key_no, bank, k['slot'], k.get('label'), k.get('subtitle'),
                     k.get('mode'), A._pick(A.LATCHING_TIMEOUTS, k.get('latching_timeout', 0)),
                     k.get('dim'), k.get('auto_label'), A.swatch_color_name(k.get('group_colour')),
                     '#' + k['text_colour'].upper() if k.get('text_colour') else 'Default',
                     k.get('icon'), k.get('monitoring_state_name'), k.get('radio_button') or '',
                     A._pick(A.MUTED_KEY_ACTIONS, k['action_by_key_pressed']) if 'action_by_key_pressed' in k else '',
                     k.get('restore_volume_level'), k.get('restart_latching_timer'),
                     ' | '.join('%s: %s' % (f, t) if t else f for f, t, _ in desc),
                     ' | '.join(d for _, _, d in desc), k.get('changed_last_session')])
    write_table(wb, 'Key Details', ['Panel / holder', 'Key', 'Bank', 'Stored slot', 'Label', 'Subtitle', 'Mode',
                             'Latching timeout', 'Dim', 'Auto label', 'Group colour', 'Text colour', 'Icon',
                             'Monitoring state', 'Radio button group', 'Action when muted', 'Restore volume level',
                             'Restart latching timer', 'Functions', 'Function details', 'Changed last session'],
                rows, changed_col=20,
                note='One row per key that has a label or a function. Key = stored slot within half of the holder\'s '
                     'slots; Bank 2 = the upper half (inferred from usage). "Stored slot" is the raw position.')


def sheet_functions(wb, ctx):
    rows = []
    for c in ctx.recs:
        if not ctx.reader[c['id']].startswith('read_cmd'):
            continue
        fn, target, details = describe_command(c, ctx)
        rows.append([ctx.cmd_owner.get(c['id'], '(not assigned)'), fn, target, c.get('priority', ''), details,
                     c.get('changed_last_session')])
    write_table(wb, 'Functions', ['Where', 'Function', 'Target', 'Priority', 'Details', 'Changed last session'], rows,
                changed_col=5, note='Every function (command) record, with where it is assigned.')


def sheet_conferences(wb, ctx):
    rows = []
    for c in sorted(ctx.by_class[0x12], key=lambda c: c.get('label', '')):
        det = c.get('member_details') or [{'member': m} for m in c.get('members') or []]
        mem = ['%s [%s%s%s]' % (ctx.name(d['member']), 'T' if d.get('talk') else '-', 'L' if d.get('listen') else '-',
                                ', 2nd ch' if d.get('use_second_channel') else '') for d in det]
        rows.append([c.get('label'), c.get('long_name'), c.get('alias'), A.swatch_color_name(c.get('colour')),
                     c.get('icon'), c.get('trunk_enabled'), c.get('trunk_address'), c.get('dynaconf'),
                     c.get('mcr_use'), ctx.name(c.get('gpio_out')), len(det), '; '.join(mem),
                     c.get('changed_last_session')])
    write_table(wb, 'Conferences', ['Label', 'Long name', 'Alias', 'Colour', 'Icon', 'Trunk enabled', 'Trunk address',
                                    'DynaConf', 'MCR use', 'GPIO out', 'Members', 'Member list [Talk/Listen]',
                                    'Changed last session'], rows, changed_col=12)


def sheet_groups(wb, ctx):
    rows = []
    for g in sorted(ctx.by_class[0x11], key=lambda g: g.get('label', '')):
        sec = g.get('member_second_channel') or [False] * len(g.get('members') or [])
        mem = ['%s%s' % (ctx.name(m), ' [2nd ch]' if s else '') for m, s in zip(g.get('members') or [], sec)]
        rows.append([g.get('label'), g.get('long_name'), A.swatch_color_name(g.get('colour')), g.get('icon'),
                     g.get('keypad_shortcut') if g.get('keypad_shortcut') != 0xffff else '', g.get('trunk_enabled'),
                     g.get('trunk_address'), ctx.name(g.get('gpio_out')), len(mem), '; '.join(mem),
                     g.get('changed_last_session')])
    write_table(wb, 'Groups', ['Label', 'Long name', 'Colour', 'Icon', 'Keypad shortcut', 'Trunk enabled',
                               'Trunk address', 'GPIO out', 'Members', 'Member list', 'Changed last session'],
                rows, changed_col=10)


def endpoint(e, ctx):
    if not e:
        return ''
    if 'port' in e:
        return ctx.name(e['port'])
    if 'group' in e:
        return 'Group ' + ctx.name(e['group'])
    return 'Trunk (not kept by Director)'


def sheet_ifbs(wb, ctx):
    rows = []
    for i in sorted(ctx.by_class[0x66], key=lambda i: i.get('ifb_number', 0)):
        rows.append([i.get('ifb_number'), i.get('label'), i.get('long_name'), endpoint(i.get('input'), ctx),
                     endpoint(i.get('mix_minus'), ctx), endpoint(i.get('output'), ctx), i.get('dim_db'),
                     i.get('sidetone'), i.get('is_trunk_enabled'), i.get('changed_last_session')])
    write_table(wb, 'IFBs', ['Number', 'Label', 'Long name', 'Input', 'Mix minus', 'Output', 'Dim level', 'Sidetone',
                             'Trunk enabled', 'Changed last session'], rows, changed_col=9)


def sheet_scroll_lists(wb, ctx):
    rows = []
    for s in ctx.by_class[0x10]:
        for n, e in enumerate(s.get('entries') or [], 1):
            c = ctx.byid.get(e['command'])
            fn, target, det = describe_command(c, ctx) if c else ('', '', '')
            rows.append([s.get('name'), s.get('is_global'), n, e.get('label'), fn, target, det, e.get('key_mode'),
                         e.get('latching_timeout'), e.get('dim_speaker'), e.get('auto_label'),
                         e.get('keypad_shortcut'), s.get('changed_last_session')])
        if not s.get('entries'):
            rows.append([s.get('name'), s.get('is_global'), '', '(empty)', '', '', '', '', '', '', '', '',
                         s.get('changed_last_session')])
    write_table(wb, 'Scroll Lists', ['Scroll list', 'Global', 'Entry', 'Label', 'Function', 'Target', 'Details',
                                     'Key mode', 'Latching timeout', 'Dim panel speaker', 'Label defined automatically',
                                     'Keypad shortcut', 'Changed last session'], rows, changed_col=12)


def sheet_audio_patches(wb, ctx):
    rows = []
    for p in ctx.by_class[0x19]:
        try:
            routes, muted = A.audiopatch_routes(p)
        except Exception:
            routes, muted = [], []
        rows.append([ctx.name(p.get('panel')), p.get('name'), p.get('patch_mode_name'), '; '.join(routes),
                     ', '.join(muted), p.get('changed_last_session')])
    write_table(wb, 'Audio Patches', ['Panel', 'Patch', 'Mode', 'Active crosspoints', 'Muted outputs',
                                      'Changed last session'], rows, changed_col=5)


def sheet_logic_gpio(wb, ctx):
    rows = []
    for s in ctx.by_class[0x40]:
        rows.append(['Logic source', s.get('name') or s.get('label'), s.get('src_type_name'),
                     '2nd audio channel' if s.get('second_audio_channel') else '', ctx.name(s.get('src_ref')),
                     s.get('changed_last_session')])
    for d in ctx.by_class[0x41]:
        cmds = [describe_command(ctx.byid[c], ctx) for c in d.get('commands') or [] if c in ctx.byid]
        rows.append(['Logic destination', d.get('name'), 'active from: %s' % ', '.join(ctx.name(i) for i in d.get('active_inputs') or []),
                     'not active from: %s' % ', '.join(ctx.name(i) for i in d.get('not_active_inputs') or []),
                     ' | '.join('%s: %s' % (f, t) for f, t, _ in cmds), d.get('changed_last_session')])
    for g in ctx.recs:
        if g['class'] in A.LOGIC_GATE_NAMES:
            extra = ''
            if g['class'] == 0x86:
                extra = 'time %s, %s' % (g.get('monoflop_time'), 'retrigger extends time' if g.get('retrigger_extends_time') else 'fixed')
            rows.append(['Logic gate', g.get('name', ''), g.get('gate_type'), extra,
                         'inputs %d, outputs %d' % (len(g.get('inputs') or []), len(g.get('outputs') or [])),
                         g.get('changed_last_session')])
    for c in ctx.by_class[0x87]:
        rows.append(['Logic clock', '', 'Clock', '', ctx.name(c.get('dst')), c.get('changed_last_session')])
    for l in ctx.by_class[0x42]:
        rows.append(['Logic line', '', '%s (pin %s) -> %s (pin %s)' % (ctx.name(l.get('from')), l.get('from_pin'),
                                                                    ctx.name(l.get('to')), l.get('to_pin')),
                     '', '', l.get('changed_last_session')])
    for g in ctx.by_class[0xc]:
        rows.append(['GPIO in', g.get('name'), 'input %s' % ((g.get('gpio_index') or 0) + 1),
                     'inverted' if g.get('inverted') else 'normal', ctx.name(g.get('panel') or g.get('card_gpio')),
                     g.get('changed_last_session')])
    for g in ctx.by_class[0xd]:
        rows.append(['GPIO out', g.get('name') or g.get('label'), 'output %s' % ((g.get('gpio_index') or 0) + 1),
                     '%s%s' % ('normally closed' if g.get('normally_closed') else 'normally open',
                               ', off delay %s' % g['off_delay'] if g.get('off_delay') else ''),
                     ctx.name(g.get('panel') or g.get('card_gpio')), g.get('changed_last_session')])
    write_table(wb, 'Logic & GPIO', ['Kind', 'Name', 'Type / connection', 'Settings', 'Linked to',
                                     'Changed last session'], rows, changed_col=5)


def sheet_users(wb, ctx):
    rows = [[u.get('name'), u.get('full_name'), u.get('password'), u.get('user_manager'),
             ', '.join(u.get('permissions') or []), u.get('changed_last_session')] for u in ctx.by_class[0x23]]
    write_table(wb, 'Users', ['User', 'Full name', 'Password', 'User account manager', 'Permissions',
                              'Changed last session'], rows, changed_col=5,
                note='Passwords are courtesy lock-outs, shown in plain text as stored (decoded from Director\'s '
                     'character-inverted form).')


RESOURCE_ORDER = ['Frames', 'Controllers', 'Power supplies', 'Cards', 'Panels', 'Expansion panels',
                  'Bolero beltpacks', 'Wired beltpacks', 'Other ports']


def resource_counts(ctx):
    """[(category, item, quantity)] for every kind of hardware and port in the file, e.g.
    ('Cards', 'AES67-108 G2', 4), ('Panels', 'RSP-2318 Pro', 37), ('Bolero beltpacks', 'Bolero Wireless Beltpack', 80).
    Panels are the port types that hold keys; Artist 1024 NICs count as controllers (Director stores no
    controller or power-supply objects for 1024 frames)."""
    cnt = Counter()
    for n in ctx.nodes:
        cnt[('Frames', A.NODE_TYPE_NAMES.get(n.get('node_type'), 'Frame type %s' % n.get('node_type')))] += 1
        for key, cat in (('controllers', 'Controllers'), ('power_supplies', 'Power supplies')):
            for oid in n.get(key) or []:
                c = ctx.byid.get(oid)
                if c:
                    try:
                        model = A.card_model(c, n)
                    except Exception:
                        model = 'class 0x%x' % c['class']
                    cnt[('Cards' if c['class'] == 0x201 else cat, model)] += 1
    counted = {oid for n in ctx.nodes for key in ('controllers', 'power_supplies') for oid in n.get(key) or []}
    for c in ctx.cards:
        if c['class'] == 0x10d or c['id'] in counted:
            continue                                     # SIC port groups are part of their card
        node = ctx.byid.get(c.get('node'), {})
        try:
            model = A.card_model(c, node)
        except Exception:
            model = 'class 0x%x' % c['class']
        cnt[('Controllers', model + ' (Artist 1024 controller)') if c['class'] == 0x10c else ('Cards', model)] += 1
    key_classes = {ctx.byid[k['holder']]['class'] for k in ctx.keys if k['holder'] in ctx.byid}
    for p in ctx.ports:
        try:
            typ = A.port_type(p, ctx.byid)
        except Exception:
            typ = A.PORT_TYPE_NAMES.get(p['class'], 'class 0x%x' % p['class'])
        if 'Bolero' in typ:
            cat = 'Bolero beltpacks'
        elif 'Beltpack' in typ:
            cat = 'Wired beltpacks'
        elif p['class'] in key_classes:
            cat = 'Panels'
        else:
            cat = 'Other ports'
        cnt[(cat, typ)] += 1
    for e in ctx.recs:
        if ctx.reader.get(e['id']) == 'read_expansion':
            model = (A.EXPANSION_NAMES.get(e['class']) or A.PORT_TYPE_NAMES.get(e['class'])
                     or 'Expansion panel (class 0x%x)' % e['class'])
            cnt[('Expansion panels', model)] += 1
    return sorted(((cat, item, n) for (cat, item), n in cnt.items()),
                  key=lambda r: (RESOURCE_ORDER.index(r[0]) if r[0] in RESOURCE_ORDER else 99, -r[2], r[1]))


def sheet_resources(wb, ctx):
    rows = resource_counts(ctx)
    totals = Counter()
    for cat, _, n in rows:
        totals[cat] += n
    out = []
    for cat in RESOURCE_ORDER:
        items = [r for r in rows if r[0] == cat]
        if items:
            out += [[cat if i == 0 else '', item, n] for i, (_, item, n) in enumerate(items)]
            out.append(['', 'Total %s' % cat.lower(), totals[cat]])
    ws = write_table(wb, 'Resources', ['Category', 'Item', 'Quantity'], out,
                     note='How many of each frame, controller, power supply, card, panel, expansion panel, beltpack and '
                          'port type the file contains. Artist 1024 frames store no power supplies.')
    for r in range(4, 4 + len(out)):
        if str(ws.cell(r, 2).value or '').startswith('Total '):
            ws.cell(r, 2).font = ws.cell(r, 3).font = Font(bold=True)


VF_COLUMNS = ['Always', 'On VOX', 'On Call']          # Director's Virtual Functions group (dialog 384)


def virtual_function_rows(ctx):
    """One entry per panel / beltpack that has virtual functions: {port, label, long name, type, and the
    functions under Always / On VOX / On Call}. A virtual function (CPhysVirtFn 0x24) is a key without a button;
    vf_slot says when it acts. Slot 2 has no name in Director and is not shown unless it holds functions."""
    per = defaultdict(lambda: defaultdict(list))
    changed = defaultdict(bool)
    for v in ctx.by_class[0x24]:
        cmds = [describe_command(ctx.byid[c], ctx) for c in v.get('commands') or [] if c in ctx.byid]
        if not cmds:
            continue                                     # empty virtual function slot
        slot = v.get('vf_slot')
        slot = slot if slot in VF_COLUMNS else 'Slot %s' % slot
        per[v.get('panel')][slot] += ['%s: %s' % (f, t) if t else f for f, t, _ in cmds]
        changed[v.get('panel')] |= bool(v.get('changed_last_session'))
    out = []
    for pid, slots in per.items():
        p = ctx.byid.get(pid, {})
        ps = p.get('port_strings') or []
        try:
            typ = A.port_type(p, ctx.byid)
        except Exception:
            typ = A.PORT_TYPE_NAMES.get(p.get('class'), 'class 0x%x' % p.get('class', 0))
        try:
            order = ctx.port_sort_key(p)
        except Exception:
            order = ('~',)
        out.append({'order': (p.get('class') == 0x440, order), 'port': ps[1] if len(ps) > 1 else '',
                    'label': p.get('name') or '', 'long_name': p.get('port_str') or '', 'type': typ,
                    'slots': {k: v for k, v in slots.items()}, 'changed': changed[pid]})
    out.sort(key=lambda r: r['order'])
    return out


def sheet_virtual_functions(wb, ctx):
    rows = virtual_function_rows(ctx)
    extra = sorted({k for r in rows for k in r['slots'] if k not in VF_COLUMNS})
    cols = VF_COLUMNS + extra
    write_table(wb, 'Virtual Functions', ['Port', 'Label', 'Long name', 'Type'] + cols + ['Changed last session'],
                [[r['port'], r['label'], r['long_name'], r['type']] + [' | '.join(r['slots'].get(c, [])) for c in cols]
                 + [r['changed']] for r in rows],
                changed_col=4 + len(cols),
                note='Functions that act without a key press, per panel and beltpack: Always (all the time), '
                     'On VOX (when the port\'s VOX opens), On Call (when the port is called). Director: Virtual Functions.')


def sheet_other(wb, ctx):
    rows = []
    for b in ctx.by_class[0x1a]:
        rows.append(['Phone book', b.get('name'), '', '; '.join(str(e) for e in b.get('entries') or []),
                     b.get('changed_last_session')])
    for r in ctx.recs:
        rn = ctx.reader[r['id']]
        if rn == 'read_port_shortlist':
            rows.append(['Port shortlist', r.get('name'), '', ', '.join(ctx.name(i) for i in r.get('panels') or []),
                         r.get('changed_last_session')])
        elif rn == 'read_group_conf_shortlist':
            rows.append(['Group / conference shortlist', r.get('name'), '',
                         ', '.join(ctx.name(i) for i in r.get('members') or r.get('items') or []),
                         r.get('changed_last_session')])
        elif rn == 'read_scheduler_task':
            rows.append(['Scheduled task', r.get('name'), '%s-%s-%s %s:%s:%s' % (
                r.get('year'), r.get('month'), r.get('day'), r.get('hour'), r.get('minute'), r.get('second')),
                'event: %s' % ctx.name(r.get('event_id')), r.get('changed_last_session')])
        elif rn == 'read_event':
            rows.append(['Event', r.get('name'), 'active' if r.get('active') else 'inactive',
                         '; '.join(str(a) for a in r.get('actions') or []), r.get('changed_last_session')])
        elif rn in ('read_nsa_device', 'read_connect_voip_device'):
            keys = [k for k in r if k in ('media1_ip', 'media2_ip', 'webui_ip', 'ip_address', 'input_multicast_ip',
                                          'output_multicast_ip')]
            rows.append(['NSA device' if rn == 'read_nsa_device' else 'VoIP device', r.get('name'), '',
                         ', '.join('%s %s' % (k, ip(r[k])) for k in keys), r.get('changed_last_session')])
    if rows:
        write_table(wb, 'Other Objects', ['Kind', 'Name', 'Detail', 'Contents', 'Changed last session'], rows,
                    changed_col=4)


def sheet_all_records(wb, ctx):
    skip = {'id', 'class', 'group', 'category', 'offset', 'length'}
    rows = []
    for r in ctx.recs:
        fields = {k: v for k, v in r.items() if k not in skip}
        rows.append([r['id'], '0x%x' % r['class'], r.get('category'), ctx.name(r['id']), r.get('changed_last_session'),
                     ctx.name(r.get('parent')), json.dumps(fields, default=str, ensure_ascii=False)])
    write_table(wb, 'All Records', ['ID', 'Class', 'Record type', 'Name', 'Changed last session', 'Parent',
                                    'All decoded fields (JSON)'], rows, widths={'All decoded fields (JSON)': 120},
                note='Every record and every decoded field, for values that have no column elsewhere.')


def json_default(o):
    """JSON for values json can't write: raw bytes as hex, anything else as text."""
    return o.hex() if isinstance(o, (bytes, bytearray)) else str(o)


def art_to_json_dict(data, filename=''):
    """The Artist JSON export: header, counts and every decoded record (the same content as the All Records sheet,
    as structured data). Used by export_tool.py --format json and by the web page's Download JSON."""
    h, recs = A.parse_art(data)
    count = lambda cls: sum(1 for r in recs if r['class'] == cls)
    return {
        'format': 'Riedel Artist .Art',
        'file': filename,
        'header': h,
        'counts': {
            'records': len(recs),
            'nodes': count(3),
            'ports': sum(1 for r in recs if r['class'] in A.PORT_TYPE_NAMES),
            'active_keys': sum(1 for r in recs if r['class'] == 9 and r.get('commands')),
            'conferences': count(0x12),
            'groups': count(0x11),
            'ifbs': count(0x66),
        },
        'records': recs,
    }


def art_to_json_text(data, filename=''):
    return json.dumps(art_to_json_dict(data, filename), indent=2, default=json_default)


def export_art_to_excel(art_file_path, output_path=None):
    """Write the workbook for one .Art file; returns the output path."""
    ctx = Ctx(art_file_path)
    output_path = pathlib.Path(output_path) if output_path else ctx.path.with_suffix('.xlsx')
    wb = Workbook()
    sheet_summary(wb, ctx)
    for fn in (sheet_resources, sheet_system, sheet_nodes, sheet_cards, sheet_ports, sheet_keys, sheet_virtual_functions, sheet_functions,
               sheet_conferences, sheet_groups, sheet_ifbs, sheet_scroll_lists, sheet_audio_patches,
               sheet_logic_gpio, sheet_users, sheet_other, sheet_key_details, sheet_markers, sheet_all_records):
        fn(wb, ctx)
    wb.save(output_path)
    print(f"Successfully generated: {output_path}")
    return output_path


USAGE = """usage: python art_to_excel.py [-o OUTPUT] FILE.Art [FILE.Art ...]

  FILE.Art   one or more Artist saves
  -o OUTPUT  output .xlsx for a single input, or an existing folder for several inputs
  -h, --help show this help and exit (nothing is written)"""


if __name__ == '__main__':
    out_opt = None
    args = []
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('-h', '--help'):
            print(USAGE)
            sys.exit(0)
        if a == '-o':
            if i + 1 >= len(argv):
                sys.exit('error: -o needs an output path\n\n' + USAGE)
            out_opt = argv[i + 1]
            i += 2
            continue
        if a.startswith('-'):
            sys.exit('error: unknown option %s\n\n%s' % (a, USAGE))
        args.append(a)
        i += 1

    if not args:
        sys.exit(USAGE)
    files = args
    if len(files) > 1 and out_opt and not os.path.isdir(out_opt):
        sys.exit('error: with several inputs, -o must be an existing folder')
    for f in files:
        target = out_opt
        if out_opt and os.path.isdir(out_opt):
            target = os.path.join(out_opt, pathlib.Path(f).stem + '.xlsx')
        try:
            export_art_to_excel(f, target)
        except Exception as e:
            print(f"Error converting {f}: {e}")
            if args:
                raise
