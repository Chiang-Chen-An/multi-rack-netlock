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
from control_plane.controller import _parse_lock_ids, _telemetry_row
from control_plane.knapsack import LockMemoryCandidate, choose_locks_for_switch
from control_plane.migration_manager import LockState, MigrationManager
import control_plane.p4runtime_switch as p4runtime_switch
from control_plane.p4runtime_switch import P4RuntimeSwitch
from control_plane.stats_collector import (
    LockTelemetryDelta,
    LockTelemetrySnapshot,
    StatsCollector,
)


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

    def test_switch_config_loads_optional_bmv2_thrift_port(self) -> None:
        config = SwitchConfig.from_dict({"thrift_port": 9101})

        self.assertEqual(config.thrift_port, 9101)

    def test_switch_config_can_skip_pipeline_artifact_validation(self) -> None:
        config = SwitchConfig(push_pipeline=False)

        config.validate()

    def test_switch_config_rejects_invalid_bmv2_thrift_port(self) -> None:
        config = SwitchConfig.from_dict({"thrift_port": 0})

        with self.assertRaisesRegex(ValueError, "thrift_port"):
            config.validate()


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


class FakeRegisterEntry:
    def __init__(self, values: dict[tuple[str, int], int], register_name: str):
        self.values = values
        self.register_name = register_name
        self.index: int | None = None

    def __getitem__(self, index: int) -> "FakeRegisterEntry":
        self.index = index
        return self

    def read(self):
        if self.index is None:
            return iter(())
        return iter([self.values[(self.register_name, self.index)]])


class FakeRegisterShell(FakeP4RuntimeShell):
    def __init__(self, values: dict[tuple[str, int], int]):
        super().__init__()
        self.values = values

    def RegisterEntry(self, register_name: str) -> FakeRegisterEntry:
        return FakeRegisterEntry(self.values, register_name)


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

    def test_connect_supports_real_p4runtime_shell_submodule_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p4info = root / "leaf.p4info.txt"
            bmv2_json = root / "leaf.json"
            p4info.write_text("p4info", encoding="utf-8")
            bmv2_json.write_text("json", encoding="utf-8")
            package = types.ModuleType("p4runtime_sh")
            package.__path__ = []  # type: ignore[attr-defined]
            fake_shell = FakeP4RuntimeShell()
            previous_package = sys.modules.get("p4runtime_sh")
            previous_shell = sys.modules.get("p4runtime_sh.shell")
            sys.modules["p4runtime_sh"] = package
            sys.modules["p4runtime_sh.shell"] = fake_shell
            try:
                switch = P4RuntimeSwitch(
                    SwitchConfig(
                        name="leaf1",
                        device_id=7,
                        grpc_addr="127.0.0.1:50007",
                        pipeline=PipelineConfig(p4info, bmv2_json),
                    )
                )

                switch.connect()

                self.assertTrue(switch.connected)
                self.assertEqual(len(fake_shell.setup_calls), 1)
                switch.disconnect()
                self.assertEqual(fake_shell.teardown_calls, 1)
            finally:
                if previous_package is None:
                    sys.modules.pop("p4runtime_sh", None)
                else:
                    sys.modules["p4runtime_sh"] = previous_package
                if previous_shell is None:
                    sys.modules.pop("p4runtime_sh.shell", None)
                else:
                    sys.modules["p4runtime_sh.shell"] = previous_shell

    def test_connect_can_skip_pipeline_push(self) -> None:
        fake_shell = FakeP4RuntimeShell()
        previous_shell = sys.modules.get("p4runtime_sh")
        sys.modules["p4runtime_sh"] = fake_shell
        try:
            switch = P4RuntimeSwitch(
                SwitchConfig(
                    name="leaf1",
                    device_id=7,
                    grpc_addr="127.0.0.1:50007",
                    push_pipeline=False,
                )
            )

            switch.connect()

            self.assertEqual(fake_shell.setup_calls[0]["config"], None)
            switch.disconnect()
        finally:
            if previous_shell is None:
                sys.modules.pop("p4runtime_sh", None)
            else:
                sys.modules["p4runtime_sh"] = previous_shell

    def test_read_register_cell_reads_indexed_register_value(self) -> None:
        fake_shell = FakeRegisterShell({("lock_queue_depth", 42): 16})
        switch = P4RuntimeSwitch(SwitchConfig())
        switch._sh = fake_shell
        switch.connected = True

        value = switch.read_register_cell("lock_queue_depth", 42)

        self.assertEqual(value, 16)

    def test_register_entry_reports_missing_register_api(self) -> None:
        switch = P4RuntimeSwitch(SwitchConfig())
        switch._sh = types.ModuleType("p4runtime_sh.shell")
        switch.connected = True

        with self.assertRaisesRegex(RuntimeError, "does not expose RegisterEntry"):
            switch.register_entry("lock_queue_depth")

    def test_parse_bmv2_register_read_extracts_register_value(self) -> None:
        output = """
Obtaining JSON from switch...
Done
RuntimeCmd: lock_acquire_count[1]= 3
RuntimeCmd:
"""

        value = p4runtime_switch._parse_bmv2_register_read(
            "lock_acquire_count",
            1,
            output,
        )

        self.assertEqual(value, 3)

    def test_read_register_cell_falls_back_to_bmv2_cli(self) -> None:
        class Completed:
            returncode = 0
            stdout = "RuntimeCmd: lock_acquire_count[1]= 3\n"
            stderr = ""

        calls = []

        def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
            calls.append((command, kwargs))
            return Completed()

        previous_run = p4runtime_switch.subprocess.run
        p4runtime_switch.subprocess.run = fake_run
        try:
            switch = P4RuntimeSwitch(SwitchConfig(thrift_port=9101))
            switch._sh = types.ModuleType("p4runtime_sh.shell")
            switch.connected = True

            value = switch.read_register_cell("lock_acquire_count", 1)

            self.assertEqual(value, 3)
            self.assertEqual(
                calls[0][0],
                ["simple_switch_CLI", "--thrift-port", "9101"],
            )
            self.assertEqual(calls[0][1]["input"], "register_read lock_acquire_count 1\n")
        finally:
            p4runtime_switch.subprocess.run = previous_run

    def test_read_register_cell_can_use_bmv2_cli_without_p4runtime_connection(self) -> None:
        class Completed:
            returncode = 0
            stdout = "RuntimeCmd: lock_acquire_count[1]= 3\n"
            stderr = ""

        previous_run = p4runtime_switch.subprocess.run
        p4runtime_switch.subprocess.run = lambda *args, **kwargs: Completed()
        try:
            switch = P4RuntimeSwitch(SwitchConfig(thrift_port=9101))

            value = switch.read_register_cell("lock_acquire_count", 1)

            self.assertEqual(value, 3)
        finally:
            p4runtime_switch.subprocess.run = previous_run


class FakeStatsSwitch:
    def __init__(self, values: dict[tuple[str, int], int]):
        self.values = values
        self.reads: list[tuple[str, int]] = []

    def read_register_cell(self, register_name: str, index: int) -> int:
        self.reads.append((register_name, index))
        return self.values[(register_name, index)]


class StatsCollectorTests(unittest.TestCase):
    def test_read_lock_queue_stats_reads_queue_registers(self) -> None:
        switch = FakeStatsSwitch(
            {
                ("lock_queue_base", 7): 100,
                ("lock_queue_depth", 7): 16,
                ("lock_queue_head", 7): 2,
                ("lock_queue_tail", 7): 5,
                ("lock_queue_occupancy", 7): 3,
                ("lock_holder", 7): 9,
            }
        )

        stats = StatsCollector(switch).read_lock_queue_stats(7)  # type: ignore[arg-type]

        self.assertEqual(stats.lock_id, 7)
        self.assertEqual(stats.base, 100)
        self.assertEqual(stats.depth, 16)
        self.assertEqual(stats.head, 2)
        self.assertEqual(stats.tail, 5)
        self.assertEqual(stats.occupancy, 3)
        self.assertEqual(stats.holder, 9)

    def test_read_lock_telemetry_computes_lifetime_ratios(self) -> None:
        switch = FakeStatsSwitch(
            {
                ("lock_queue_base", 7): 100,
                ("lock_queue_depth", 7): 16,
                ("lock_queue_head", 7): 2,
                ("lock_queue_tail", 7): 5,
                ("lock_queue_occupancy", 7): 3,
                ("lock_holder", 7): 9,
                ("lock_acquire_count", 7): 100,
                ("lock_miss_count", 7): 25,
                ("lock_overflow_count", 7): 10,
            }
        )

        stats = StatsCollector(switch).read_lock_telemetry(7)  # type: ignore[arg-type]

        self.assertEqual(stats.memory_waste_slots, 13)
        self.assertEqual(stats.memory_waste_ratio, 13 / 16)
        self.assertEqual(stats.miss_ratio, 0.25)
        self.assertEqual(stats.queue_overflow_ratio, 0.10)

    def test_lock_telemetry_delta_uses_polling_window_counters(self) -> None:
        previous = LockTelemetrySnapshot(
            lock_id=7,
            base=100,
            depth=16,
            head=2,
            tail=5,
            occupancy=3,
            holder=9,
            acquire_count=100,
            miss_count=25,
            overflow_count=10,
        )
        current = LockTelemetrySnapshot(
            lock_id=7,
            base=100,
            depth=16,
            head=2,
            tail=8,
            occupancy=6,
            holder=9,
            acquire_count=150,
            miss_count=30,
            overflow_count=20,
        )

        delta = LockTelemetryDelta.from_snapshots(previous, current)

        self.assertEqual(delta.memory_waste_slots, 10)
        self.assertEqual(delta.acquire_delta, 50)
        self.assertEqual(delta.miss_delta, 5)
        self.assertEqual(delta.overflow_delta, 10)
        self.assertEqual(delta.miss_ratio, 0.10)
        self.assertEqual(delta.queue_overflow_ratio, 0.20)

    def test_parse_lock_ids_accepts_comma_separated_ids(self) -> None:
        self.assertEqual(_parse_lock_ids("1, 2,42"), [1, 2, 42])

    def test_parse_lock_ids_rejects_empty_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            _parse_lock_ids(" , ")

    def test_telemetry_row_includes_lifetime_and_delta_metrics(self) -> None:
        previous = LockTelemetrySnapshot(
            lock_id=7,
            base=100,
            depth=16,
            head=2,
            tail=5,
            occupancy=3,
            holder=9,
            acquire_count=100,
            miss_count=25,
            overflow_count=10,
        )
        current = LockTelemetrySnapshot(
            lock_id=7,
            base=100,
            depth=16,
            head=2,
            tail=8,
            occupancy=6,
            holder=9,
            acquire_count=150,
            miss_count=30,
            overflow_count=20,
        )
        delta = LockTelemetryDelta.from_snapshots(previous, current)

        row = _telemetry_row("2026-05-03T00:00:00Z", "leaf1", current, delta)

        self.assertEqual(row["timestamp"], "2026-05-03T00:00:00Z")
        self.assertEqual(row["switch"], "leaf1")
        self.assertEqual(row["lock_id"], 7)
        self.assertEqual(row["memory_waste_slots"], 10)
        self.assertEqual(row["memory_waste_ratio"], 10 / 16)
        self.assertEqual(row["miss_ratio"], 30 / 150)
        self.assertEqual(row["queue_overflow_ratio"], 20 / 150)
        self.assertEqual(row["acquire_delta"], 50)
        self.assertEqual(row["miss_ratio_delta"], 5 / 50)
        self.assertEqual(row["queue_overflow_ratio_delta"], 10 / 50)


if __name__ == "__main__":
    unittest.main()
