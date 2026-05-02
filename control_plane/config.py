from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_P4INFO = REPO_ROOT / "build" / "leaf.p4info.txt"
DEFAULT_BMV2_JSON = REPO_ROOT / "build" / "leaf.json"


@dataclass(frozen=True)
class PipelineConfig:
    """P4Runtime forwarding pipeline artifacts for one switch target."""

    p4info_path: Path = DEFAULT_P4INFO
    bmv2_json_path: Path = DEFAULT_BMV2_JSON

    def __post_init__(self) -> None:
        object.__setattr__(self, "p4info_path", _repo_path(self.p4info_path))
        object.__setattr__(self, "bmv2_json_path", _repo_path(self.bmv2_json_path))

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PipelineConfig":
        return cls(
            p4info_path=raw.get("p4info_path", DEFAULT_P4INFO),
            bmv2_json_path=raw.get("bmv2_json_path", DEFAULT_BMV2_JSON),
        )

    def validate(self) -> None:
        _require_file(self.p4info_path, "P4Info file")
        _require_file(self.bmv2_json_path, "BMv2 JSON file")


@dataclass(frozen=True)
class SwitchConfig:
    """Connection settings for one P4Runtime switch."""

    name: str = "leaf1"
    device_id: int = 1
    grpc_addr: str = "127.0.0.1:50001"
    election_id: tuple[int, int] = (0, 1)
    thrift_port: int | None = 9090
    push_pipeline: bool = True
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SwitchConfig":
        election_id = raw.get("election_id", [0, 1])
        if not isinstance(election_id, (list, tuple)) or len(election_id) != 2:
            raise ValueError("switch election_id must be a 2-item list: [high, low]")

        return cls(
            name=str(raw.get("name", "leaf1")),
            device_id=int(raw.get("device_id", 1)),
            grpc_addr=str(raw.get("grpc_addr", "127.0.0.1:50001")),
            election_id=(int(election_id[0]), int(election_id[1])),
            thrift_port=(
                int(raw["thrift_port"])
                if raw.get("thrift_port") is not None
                else None
            ),
            push_pipeline=bool(raw.get("push_pipeline", True)),
            pipeline=PipelineConfig.from_dict(raw.get("pipeline", {})),
        )

    def validate(self) -> None:
        if self.device_id < 0:
            raise ValueError(f"{self.name}: device_id must be non-negative")
        if not self.grpc_addr:
            raise ValueError(f"{self.name}: grpc_addr must not be empty")
        if self.thrift_port is not None and not (0 < self.thrift_port < 65536):
            raise ValueError(f"{self.name}: thrift_port must be in range 1..65535")
        if self.push_pipeline:
            self.pipeline.validate()


@dataclass(frozen=True)
class ControllerConfig:
    """Top-level controller configuration."""

    switches: tuple[SwitchConfig, ...] = field(
        default_factory=lambda: (SwitchConfig(),)
    )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ControllerConfig":
        switches = raw.get("switches", [])
        if not switches:
            return cls()
        return cls(tuple(SwitchConfig.from_dict(switch) for switch in switches))

    def validate(self) -> None:
        if not self.switches:
            raise ValueError("controller config must contain at least one switch")
        seen: set[tuple[int, str]] = set()
        for switch in self.switches:
            switch.validate()
            key = (switch.device_id, switch.grpc_addr)
            if key in seen:
                raise ValueError(
                    f"duplicate switch connection for device_id={switch.device_id} "
                    f"grpc_addr={switch.grpc_addr}"
                )
            seen.add(key)


def load_controller_config(path: Path | str | None = None) -> ControllerConfig:
    """Load controller settings from JSON, or return a single-switch default."""

    if path is None:
        return ControllerConfig()

    config_path = _repo_path(path)
    _require_file(config_path, "controller config")
    with config_path.open("r", encoding="utf-8") as fp:
        raw = json.load(fp)
    return ControllerConfig.from_dict(raw)


def _repo_path(value: Path | str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
