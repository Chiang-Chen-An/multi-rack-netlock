from __future__ import annotations

from dataclasses import dataclass

try:
    from .p4runtime_switch import P4RuntimeSwitch
except ImportError:  # pragma: no cover
    from p4runtime_switch import P4RuntimeSwitch


@dataclass(frozen=True)
class LockQueueStats:
    """Snapshot of one lock's switch-resident queue state."""

    lock_id: int
    base: int
    depth: int
    head: int
    tail: int
    occupancy: int
    holder: int


class StatsCollector:
    """Read switch counters/registers needed by the migration policy."""

    def __init__(self, switch: P4RuntimeSwitch):
        self.switch = switch

    def read_lock_queue_stats(self, lock_id: int) -> LockQueueStats:
        """Read per-lock queue registers.

        The register read helper depends on the p4runtime-sh RegisterEntry API,
        so this method is intentionally left as the integration point for the
        next milestone.
        """

        raise NotImplementedError("register reads are the next control-plane milestone")
