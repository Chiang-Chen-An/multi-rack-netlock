from __future__ import annotations

import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
P4_ROOT = REPO_ROOT / "p4"


def read_p4(relative_path: str) -> str:
    return (P4_ROOT / relative_path).read_text(encoding="utf-8")


class P4StaticContractTests(unittest.TestCase):
    def test_lock_state_constants_match_control_plane_enum(self) -> None:
        constants = read_p4("include/constants.p4")

        expected_values = {
            "HOT_FREE": "1",
            "HOT_HELD": "2",
            "COLD": "3",
            "DRAINING": "4",
            "BUFFERING": "5",
        }
        for name, value in expected_values.items():
            self.assertRegex(constants, rf"const\s+bit<3>\s+{name}\s*=\s*{value};")

    def test_netlock_header_contains_control_plane_observed_fields(self) -> None:
        headers = read_p4("include/headers.p4")

        netlock_fields = [
            "bit<8> op_type;",
            "bit<16> tenant_id;",
            "bit<32> lock_id;",
            "bit<32> transaction_id;",
            "bit<32> priority;",
            "bit<32> timestamp;",
        ]
        for field in netlock_fields:
            self.assertIn(field, headers)

        metadata_fields = [
            "bit<13> queue_base;",
            "bit<13> queue_head;",
            "bit<13> queue_tail;",
            "bit<13> queue_depth;",
            "bit<13> queue_occupancy;",
            "bit<16> current_lock_holder_id;",
        ]
        for field in metadata_fields:
            self.assertIn(field, headers)

    def test_register_file_exposes_queue_metadata_and_payload_registers(self) -> None:
        registers = read_p4("leaf/register.p4")

        metadata_registers = [
            "lock_holder",
            "lock_queue_base",
            "lock_queue_head",
            "lock_queue_tail",
            "lock_queue_depth",
            "lock_queue_occupancy",
        ]
        for register in metadata_registers:
            self.assertRegex(registers, rf"register<.+>\(TOTAL_LOCKS_NUM\)\s+{register};")

        payload_registers = [
            "queue_tenant_id",
            "queue_transaction_id",
            "queue_priority",
            "queue_src_mac",
            "queue_src_ip",
            "queue_src_qp",
            "queue_ingress_port",
        ]
        for register in payload_registers:
            self.assertRegex(registers, rf"register<.+>\(TOTAL_SLOTS\)\s+{register};")

    def test_parser_extracts_rocev2_netlock_header_chain(self) -> None:
        parser = read_p4("leaf/parser.p4")

        expected_order = [
            "packet.extract(hdr.ethernet);",
            "packet.extract(hdr.ipv4);",
            "packet.extract(hdr.udp);",
            "packet.extract(hdr.bth);",
            "packet.extract(hdr.deth);",
            "packet.extract(hdr.netlock);",
        ]
        positions = [parser.index(statement) for statement in expected_order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("ROCEV2_PORT: parse_bth;", parser)

    def test_ingress_contains_current_lock_state_fast_path_rules(self) -> None:
        ingress = read_p4("leaf/ingress.p4")

        self.assertIn("table lock_state", ingress)
        self.assertIn("hdr.netlock.lock_id: exact;", ingress)
        self.assertIn("read_lock_information();", ingress)
        self.assertIn("lock_state.apply();", ingress)

        for state in ["HOT_FREE", "HOT_HELD", "COLD", "BUFFERING", "DRAINING"]:
            self.assertIn(f"meta.lock_state == {state}", ingress)

        self.assertIn("lock_queue_tail.write", ingress)
        self.assertIn("lock_queue_head.write", ingress)
        self.assertIn("lock_queue_occupancy.write", ingress)
        self.assertIn("forward_to_lock_server();", ingress)
        self.assertIn("grant_next_waiter();", ingress)


class P4CompileSmokeTests(unittest.TestCase):
    def test_leaf_p4_compiles_when_enabled(self) -> None:
        if os.environ.get("RUN_P4_COMPILE_TESTS") != "1":
            self.skipTest("set RUN_P4_COMPILE_TESTS=1 to enable Docker-based P4 compile test")
        if shutil.which("docker") is None:
            self.skipTest("docker is not installed")

        result = subprocess.run(
            ["make", "compile"],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == "__main__":
    unittest.main()
