"""Regression tests for key numbering, Dante allocation and port gain applicability.

All inputs are synthetic: class codes are protocol constants, and no show data is used.
Run from the repository root:  python -I -m unittest discover -s tests -t .
"""
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import art_to_excel as X  # noqa: E402
import artist_reader as A  # noqa: E402

BOLERO = 0x440          # Bolero Wireless Beltpack (PORT_TYPE_NAMES)
RSP_1232HL = 0x505      # RSP-1232HL panel
PANEL_KEYS = 64         # stored slots on a 32-key panel (two slots per key)


class FakeReader:
    """Scripted stand-in for the binary reader: only the calls read_card_sic_dante makes."""

    def __init__(self, version, string, byte):
        self.version = version
        self._string, self._byte = string, byte

    def string(self):
        return self._string

    def u8(self):
        return self._byte


def fake_sic_base(ar, o):
    """Stands in for read_sic_base: it stores AllocatedPorts (+0x90) the way the real reader does."""
    o['sic_u16b'] = 4
    o['allocated_ports'] = 4


class DanteCardTests(unittest.TestCase):

    def test_dante_byte_does_not_overwrite_allocated_ports(self):
        o = {}
        with mock.patch.object(A, 'read_sic_base', fake_sic_base):
            A.read_card_sic_dante(FakeReader(0x4d0, 'dante', 16), o)
        self.assertEqual(o['allocated_ports'], 4)
        self.assertEqual(o['dante_u8'], 16)


class PortGainTests(unittest.TestCase):

    def test_input_only_ports_have_no_output_gain(self):
        for cls in (0x401, 0x441):                       # 2-Wire Input, Input (Dante)
            self.assertEqual(A.port_gains(cls, -3.0, 2.0), (-3.0, None), hex(cls))

    def test_output_only_ports_have_no_input_gain(self):
        for cls in (0x402, 0x442):                       # 2-Wire Output, Output (Dante)
            self.assertEqual(A.port_gains(cls, -3.0, 2.0), (None, 2.0), hex(cls))

    def test_4_wire_and_bolero_have_both_gains(self):
        for cls in (0x403, 0x440):                       # 4-Wire, Bolero Wireless Beltpack
            self.assertEqual(A.port_gains(cls, -3.0, 2.0), (-3.0, 2.0), hex(cls))

    def test_rsp_1232hl_panel_has_neither_gain(self):
        self.assertEqual(A.port_gains(RSP_1232HL, -3.0, 2.0), (None, None))

    def test_unconfirmed_class_keeps_both_gains(self):
        self.assertEqual(A.port_gains(0x506, -3.0, 2.0), (-3.0, 2.0))   # RSP-1216HL, not in the export


class KeyNumberTests(unittest.TestCase):

    def test_bolero_slots_0_to_5_are_keys_1_to_6(self):
        for slot in range(6):
            self.assertEqual(X.key_number(slot, 10, BOLERO), (slot + 1, 1), slot)

    def test_bolero_slot_6_is_reply(self):
        self.assertEqual(X.key_number(6, 10, BOLERO), ('Reply', 1))

    def test_bolero_slots_7_to_9_are_shown_by_slot_only(self):
        # Meaning of these slots is unconfirmed, so they carry no key number.
        self.assertEqual(X.key_number(8, 10, BOLERO), ('slot 8', 1))

    def test_panel_lower_half_is_bank_1(self):
        self.assertEqual(X.key_number(0, PANEL_KEYS, RSP_1232HL), (1, 1))
        self.assertEqual(X.key_number(31, PANEL_KEYS, RSP_1232HL), (32, 1))

    def test_panel_upper_half_is_bank_2(self):
        self.assertEqual(X.key_number(32, PANEL_KEYS, RSP_1232HL), (1, 2))


if __name__ == '__main__':
    unittest.main()
