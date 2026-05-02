from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
from typing import Any
import re
import subprocess

try:
    from .config import SwitchConfig
except ImportError:  # pragma: no cover - supports running files directly
    from config import SwitchConfig


class P4RuntimeDependencyError(RuntimeError):
    """Raised when P4Runtime Python dependencies are not installed."""


@dataclass
class P4RuntimeSwitch:
    """Small wrapper around p4runtime-sh for one P4Runtime switch.

    p4runtime-sh keeps process-global shell state, so this class is intended for
    the first working prototype and single-switch experiments. A future
    multi-switch controller should replace this wrapper with raw P4Runtime gRPC
    clients, one per switch.
    """

    config: SwitchConfig
    _sh: ModuleType | None = None
    connected: bool = False

    def connect(self) -> None:
        """Open the P4Runtime channel and push the configured pipeline."""

        if self.connected:
            return

        self.config.validate()
        sh = _load_p4runtime_shell()
        pipeline = (
            sh.FwdPipeConfig(
                str(self.config.pipeline.p4info_path),
                str(self.config.pipeline.bmv2_json_path),
            )
            if self.config.push_pipeline
            else None
        )
        sh.setup(
            device_id=self.config.device_id,
            grpc_addr=self.config.grpc_addr,
            election_id=self.config.election_id,
            config=pipeline,
        )
        self._sh = sh
        self.connected = True

    def disconnect(self) -> None:
        """Close the p4runtime-sh session if this switch is connected."""

        if not self.connected or self._sh is None:
            return
        self._sh.teardown()
        self.connected = False
        self._sh = None

    def table_entry(self, table_name: str) -> Any:
        """Create a p4runtime-sh TableEntry handle for the connected switch."""

        return self.shell.TableEntry(table_name)

    def register_entry(self, register_name: str) -> Any:
        """Create a p4runtime-sh RegisterEntry handle for the connected switch."""

        if not hasattr(self.shell, "RegisterEntry"):
            raise RuntimeError(
                "connected p4runtime-sh shell does not expose RegisterEntry; "
                "this environment cannot read P4 registers through the current "
                "P4Runtime shell API"
            )
        return self.shell.RegisterEntry(register_name)

    def read_register_cell(self, register_name: str, index: int) -> int:
        """Read one register cell through p4runtime-sh.

        p4runtime-sh has had more than one public shape for register entries
        across versions. Keep that compatibility code here so telemetry logic
        can stay independent from shell details.
        """

        if self.connected and hasattr(self.shell, "RegisterEntry"):
            entry = self.register_entry(register_name)
            indexed_entry = _set_register_index(entry, index)
            values = list(indexed_entry.read())
            if not values:
                raise RuntimeError(f"register {register_name}[{index}] returned no values")
            return _register_value_to_int(values[0])
        return self._read_register_cell_with_bmv2_cli(register_name, index)

    def _read_register_cell_with_bmv2_cli(self, register_name: str, index: int) -> int:
        """Read one BMv2 register cell through simple_switch_CLI.

        BMv2 simple_switch_grpc currently reports P4Runtime register reads as
        unimplemented in common p4-guide VM setups. The Thrift runtime remains
        available and is the practical development fallback.
        """

        if self.config.thrift_port is None:
            raise RuntimeError(
                "connected p4runtime-sh shell does not expose RegisterEntry and "
                "no BMv2 thrift_port is configured"
            )
        command = ["simple_switch_CLI", "--thrift-port", str(self.config.thrift_port)]
        request = f"register_read {register_name} {index}\n"
        result = subprocess.run(
            command,
            input=request,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "simple_switch_CLI register read failed "
                f"for {register_name}[{index}]: {result.stderr.strip()}"
            )
        return _parse_bmv2_register_read(register_name, index, result.stdout)

    @property
    def shell(self) -> ModuleType:
        if not self.connected or self._sh is None:
            raise RuntimeError(f"switch {self.config.name} is not connected")
        return self._sh

    def __enter__(self) -> "P4RuntimeSwitch":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()


def _load_p4runtime_shell() -> ModuleType:
    try:
        import p4runtime_sh as sh
    except ModuleNotFoundError as exc:
        raise P4RuntimeDependencyError(
            "p4runtime_sh is not installed. Install control-plane dependencies "
            "with: python -m pip install -r control_plane/requirements.txt"
        ) from exc
    if hasattr(sh, "FwdPipeConfig"):
        return sh
    try:
        import p4runtime_sh.shell as shell
    except ModuleNotFoundError as exc:
        raise P4RuntimeDependencyError(
            "p4runtime_sh is installed, but the shell module or one of its "
            "dependencies is missing. Install control-plane dependencies with: "
            "python -m pip install -r control_plane/requirements.txt"
        ) from exc
    return shell


def _set_register_index(entry: Any, index: int) -> Any:
    if hasattr(entry, "__getitem__"):
        try:
            return entry[index]
        except (TypeError, KeyError, AttributeError):
            pass
    if callable(entry):
        try:
            return entry(index=index)
        except TypeError:
            try:
                return entry(index)
            except TypeError:
                pass
    if hasattr(entry, "index"):
        entry.index = index
        return entry
    raise RuntimeError("p4runtime-sh RegisterEntry does not support indexed reads")


def _register_value_to_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    for attr in ("data", "value"):
        if hasattr(value, attr):
            try:
                return _register_value_to_int(getattr(value, attr))
            except TypeError:
                pass
    for attr in ("uint64", "uint32", "int64", "int32"):
        if hasattr(value, attr):
            raw = getattr(value, attr)
            if isinstance(raw, int):
                return raw
    if hasattr(value, "to_int"):
        return int(value.to_int())
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"cannot convert register read value to int: {value!r}") from exc


def _parse_bmv2_register_read(register_name: str, index: int, output: str) -> int:
    pattern = rf"{re.escape(register_name)}\[{index}\]\s*=\s*([0-9]+)"
    match = re.search(pattern, output)
    if match is None:
        raise RuntimeError(
            f"could not parse simple_switch_CLI register read for "
            f"{register_name}[{index}] from output: {output!r}"
        )
    return int(match.group(1))
