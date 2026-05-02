from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path

from control_plane.config import (
    ControllerConfig,
    PipelineConfig,
    SwitchConfig,
    load_controller_config,
)
from control_plane.knapsack import LockMemoryCandidate, choose_locks_for_switch
from control_plane.migration_manager import LockState, MigrationManager
from control_plane.p4runtime_switch import P4RuntimeSwitch


class ConfigTests(unittest.TestCase):
    def test_load_controller_config_defaults_to_one_switch(self) -> None:
        config = load_controller_config()

        self.assertEqual(len(config.switches), 1)
        self.assertEqual(config.switches[0].name, "leaf1")
        self.assertEqual(config.switches[0].device_id, 1)
        self.assertEqual(config.switches[0].grpc_addr, "127.0.0.1:50001")

    def test_pipeline_config_accepts_existing_absolute_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p4info = root / "leaf.p4info.txt"
            bmv2_json = root / "leaf.json"
            p4info.write_text("p4info", encoding="utf-8")
            bmv2_json.write_text("json", encoding="utf-8")

            pipeline = PipelineConfig(p4info, bmv2_json)

            pipeline.validate()
            self.assertEqual(pipeline.p4info_path, p4info)
            self.assertEqual(pipeline.bmv2_json_path, bmv2_json)

    def test_controller_config_rejects_duplicate_switch_connection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p4info = root / "leaf.p4info.txt"
            bmv2_json = root / "leaf.json"
            p4info.write_text("p4info", encoding="utf-8")
            bmv2_json.write_text("json", encoding="utf-8")
            pipeline = PipelineConfig(p4info, bmv2_json)
            config = ControllerConfig(
                (
                    SwitchConfig("leaf1", 1, "127.0.0.1:50001", pipeline=pipeline),
                    SwitchConfig("leaf1-copy", 1, "127.0.0.1:50001", pipeline=pipeline),
                )
            )

            with self.assertRaisesRegex(ValueError, "duplicate switch connection"):
                config.validate()

    def test_switch_config_rejects_invalid_election_id_shape(self) -> None:
        with self.assertRaisesRegex(ValueError, "election_id"):
            SwitchConfig.from_dict({"election_id": [0, 1, 2]})


class KnapsackTests(unittest.TestCase):
    def test_choose_locks_maximizes_value_within_slot_budget(self) -> None:
        candidates = [
            LockMemoryCandidate(lock_id=1, value=8.0, slots=4),
            LockMemoryCandidate(lock_id=2, value=7.0, slots=3),
            LockMemoryCandidate(lock_id=3, value=5.0, slots=2),
        ]

        chosen = choose_locks_for_switch(candidates, slot_budget=5)

        self.assertEqual({candidate.lock_id for candidate in chosen}, {2, 3})
        self.assertLessEqual(sum(candidate.slots for candidate in chosen), 5)

    def test_choose_locks_ignores_non_positive_slot_candidates(self) -> None:
        candidates = [
            LockMemoryCandidate(lock_id=1, value=100.0, slots=0),
            LockMemoryCandidate(lock_id=2, value=6.0, slots=2),
        ]

        chosen = choose_locks_for_switch(candidates, slot_budget=2)

        self.assertEqual(chosen, [candidates[1]])

    def test_choose_locks_returns_empty_when_budget_is_empty(self) -> None:
        chosen = choose_locks_for_switch(
            [LockMemoryCandidate(lock_id=1, value=1.0, slots=1)],
            slot_budget=0,
        )

        self.assertEqual(chosen, [])


class MigrationManagerTests(unittest.TestCase):
    def test_migrate_to_server_builds_draining_plan(self) -> None:
        plan = MigrationManager().migrate_to_server(lock_id=42)

        self.assertEqual(plan.lock_id, 42)
        self.assertEqual(plan.source_state, LockState.HOT_HELD)
        self.assertEqual(plan.target_state, LockState.DRAINING)
        self.assertIsNone(plan.queue_base)
        self.assertIsNone(plan.queue_depth)

    def test_migrate_to_switch_builds_buffering_plan_with_queue_slice(self) -> None:
        plan = MigrationManager().migrate_to_switch(
            lock_id=42,
            queue_base=128,
            queue_depth=32,
        )

        self.assertEqual(plan.lock_id, 42)
        self.assertEqual(plan.source_state, LockState.COLD)
        self.assertEqual(plan.target_state, LockState.BUFFERING)
        self.assertEqual(plan.queue_base, 128)
        self.assertEqual(plan.queue_depth, 32)


class FakeP4RuntimeShell(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("p4runtime_sh")
        self.setup_calls: list[dict[str, object]] = []
        self.teardown_calls = 0

    def FwdPipeConfig(self, p4info_path: str, bmv2_json_path: str) -> tuple[str, str]:
        return (p4info_path, bmv2_json_path)

    def setup(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.setup_calls.append(kwargs)

    def teardown(self) -> None:
        self.teardown_calls += 1

    def TableEntry(self, table_name: str) -> tuple[str, str]:
        return ("table", table_name)

    def RegisterEntry(self, register_name: str) -> tuple[str, str]:
        return ("register", register_name)


class P4RuntimeSwitchTests(unittest.TestCase):
    def test_connect_pushes_pipeline_and_disconnect_tears_down(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p4info = root / "leaf.p4info.txt"
            bmv2_json = root / "leaf.json"
            p4info.write_text("p4info", encoding="utf-8")
            bmv2_json.write_text("json", encoding="utf-8")
            fake_shell = FakeP4RuntimeShell()
            previous_shell = sys.modules.get("p4runtime_sh")
            sys.modules["p4runtime_sh"] = fake_shell
            try:
                switch = P4RuntimeSwitch(
                    SwitchConfig(
                        name="leaf1",
                        device_id=7,
                        grpc_addr="127.0.0.1:50007",
                        election_id=(0, 9),
                        pipeline=PipelineConfig(p4info, bmv2_json),
                    )
                )

                switch.connect()

                self.assertTrue(switch.connected)
                self.assertEqual(len(fake_shell.setup_calls), 1)
                self.assertEqual(fake_shell.setup_calls[0]["device_id"], 7)
                self.assertEqual(fake_shell.setup_calls[0]["grpc_addr"], "127.0.0.1:50007")
                self.assertEqual(fake_shell.setup_calls[0]["election_id"], (0, 9))
                self.assertEqual(switch.table_entry("lock_state"), ("table", "lock_state"))
                self.assertEqual(
                    switch.register_entry("lock_queue_depth"),
                    ("register", "lock_queue_depth"),
                )

                switch.disconnect()

                self.assertFalse(switch.connected)
                self.assertEqual(fake_shell.teardown_calls, 1)
            finally:
                if previous_shell is None:
                    sys.modules.pop("p4runtime_sh", None)
                else:
                    sys.modules["p4runtime_sh"] = previous_shell


if __name__ == "__main__":
    unittest.main()
