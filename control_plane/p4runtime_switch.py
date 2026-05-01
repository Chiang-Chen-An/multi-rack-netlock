from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
from typing import Any

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
        pipeline = sh.FwdPipeConfig(
            str(self.config.pipeline.p4info_path),
            str(self.config.pipeline.bmv2_json_path),
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

        return self.shell.RegisterEntry(register_name)

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
    return sh
