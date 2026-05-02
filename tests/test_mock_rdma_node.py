from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MOCK_NODE_PATH = REPO_ROOT / "client" / "mock" / "rdma_node.py"


def load_mock_node():
    try:
        import scapy  # noqa: F401
    except ModuleNotFoundError as exc:
        raise unittest.SkipTest("Scapy is not installed") from exc

    spec = importlib.util.spec_from_file_location("mock_rdma_node", MOCK_NODE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MOCK_NODE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MockRdmaNodePacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.node = load_mock_node()
        from scapy.all import raw
        from scapy.layers.inet import IP, UDP
        from scapy.layers.l2 import Ether

        cls.raw_packet = staticmethod(raw)
        cls.Ether = Ether
        cls.IP = IP
        cls.UDP = UDP

    def test_acquire_packet_has_expected_layer_values(self) -> None:
        pkt = self.node.build_acquired_packet(
            src_mac="02:00:00:00:00:01",
            dst_mac="02:00:00:00:00:02",
            src_ip="10.0.0.1",
            dst_ip="10.0.0.2",
            lock_id=7,
            tenant_id=3,
            transaction_id=99,
            dest_qp=0x010203,
            src_qp=0x040506,
        )

        self.assertEqual(pkt[self.UDP].dport, self.node.ROCEV2_PORT)
        self.assertEqual(pkt[self.node.BTH].dest_qp, 0x010203)
        self.assertEqual(pkt[self.node.DETH].src_qp, 0x040506)
        self.assertEqual(pkt[self.node.NETLOCK].op_type, self.node.ACQUIRED)
        self.assertEqual(pkt[self.node.NETLOCK].tenant_id, 3)
        self.assertEqual(pkt[self.node.NETLOCK].lock_id, 7)
        self.assertEqual(pkt[self.node.NETLOCK].transaction_id, 99)

    def test_release_packet_sets_release_operation(self) -> None:
        pkt = self.node.build_release_packet(
            src_mac="02:00:00:00:00:01",
            dst_mac="02:00:00:00:00:02",
            src_ip="10.0.0.1",
            dst_ip="10.0.0.2",
            lock_id=7,
            tenant_id=3,
            transaction_id=100,
        )

        self.assertEqual(pkt[self.node.NETLOCK].op_type, self.node.RELEASE)
        self.assertEqual(pkt[self.node.NETLOCK].lock_id, 7)
        self.assertEqual(pkt[self.node.NETLOCK].tenant_id, 3)
        self.assertEqual(pkt[self.node.NETLOCK].transaction_id, 100)

    def test_rocev2_mock_header_lengths_match_p4_parser_contract(self) -> None:
        self.assertEqual(len(self.raw_packet(self.node.BTH())), 12)
        self.assertEqual(len(self.raw_packet(self.node.DETH())), 8)
        self.assertEqual(len(self.raw_packet(self.node.NETLOCK())), 20)

    def test_raw_packet_dissects_back_to_bound_custom_layers(self) -> None:
        pkt = self.node.build_acquired_packet(
            src_mac="02:00:00:00:00:01",
            dst_mac="02:00:00:00:00:02",
            src_ip="10.0.0.1",
            dst_ip="10.0.0.2",
            lock_id=11,
            tenant_id=4,
            transaction_id=1234,
        )

        reparsed = self.Ether(self.raw_packet(pkt))

        self.assertTrue(reparsed.haslayer(self.node.BTH))
        self.assertTrue(reparsed.haslayer(self.node.DETH))
        self.assertTrue(reparsed.haslayer(self.node.NETLOCK))
        self.assertEqual(reparsed[self.node.NETLOCK].op_type, self.node.ACQUIRED)
        self.assertEqual(reparsed[self.node.NETLOCK].lock_id, 11)
        self.assertEqual(reparsed[self.node.NETLOCK].tenant_id, 4)
        self.assertEqual(reparsed[self.node.NETLOCK].transaction_id, 1234)

    def test_serialized_offsets_match_p4_header_order(self) -> None:
        pkt = self.node.build_acquired_packet(
            src_mac="02:00:00:00:00:01",
            dst_mac="02:00:00:00:00:02",
            src_ip="10.0.0.1",
            dst_ip="10.0.0.2",
            lock_id=0x01020304,
            tenant_id=0x0506,
            transaction_id=0x0708090A,
        )

        packet_bytes = self.raw_packet(pkt)
        udp_payload_offset = 14 + 20 + 8
        bth_offset = udp_payload_offset
        deth_offset = bth_offset + 12
        netlock_offset = deth_offset + 8

        self.assertEqual(packet_bytes[bth_offset], 0x64)
        self.assertEqual(packet_bytes[netlock_offset], self.node.ACQUIRED)
        self.assertEqual(packet_bytes[netlock_offset + 2 : netlock_offset + 4], b"\x05\x06")
        self.assertEqual(
            packet_bytes[netlock_offset + 4 : netlock_offset + 8],
            b"\x01\x02\x03\x04",
        )
        self.assertEqual(
            packet_bytes[netlock_offset + 8 : netlock_offset + 12],
            b"\x07\x08\x09\x0a",
        )


if __name__ == "__main__":
    unittest.main()
