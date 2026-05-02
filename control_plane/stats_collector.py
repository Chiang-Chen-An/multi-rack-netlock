from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

try:
    from .p4runtime_switch import P4RuntimeSwitch
except ImportError:  # pragma: no cover
    from p4runtime_switch import P4RuntimeSwitch


LOCK_QUEUE_BASE_REGISTER = "lock_queue_base"
LOCK_QUEUE_DEPTH_REGISTER = "lock_queue_depth"
LOCK_QUEUE_HEAD_REGISTER = "lock_queue_head"
LOCK_QUEUE_TAIL_REGISTER = "lock_queue_tail"
LOCK_QUEUE_OCCUPANCY_REGISTER = "lock_queue_occupancy"
LOCK_HOLDER_REGISTER = "lock_holder"
LOCK_ACQUIRE_COUNT_REGISTER = "lock_acquire_count"
LOCK_MISS_COUNT_REGISTER = "lock_miss_count"
LOCK_OVERFLOW_COUNT_REGISTER = "lock_overflow_count"


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


@dataclass(frozen=True)
class LockTelemetrySnapshot:
    """One poll of queue usage and request counters for one lock."""

    lock_id: int
    base: int
    depth: int
    head: int
    tail: int
    occupancy: int
    holder: int
    acquire_count: int
    miss_count: int
    overflow_count: int

    @property
    def memory_waste_slots(self) -> int:
        return max(self.depth - self.occupancy, 0)

    @property
    def memory_waste_ratio(self) -> float:
        if self.depth <= 0:
            return 0.0
        return self.memory_waste_slots / self.depth

    @property
    def miss_ratio(self) -> float:
        if self.acquire_count <= 0:
            return 0.0
        return self.miss_count / self.acquire_count

    @property
    def queue_overflow_ratio(self) -> float:
        if self.acquire_count <= 0:
            return 0.0
        return self.overflow_count / self.acquire_count


@dataclass(frozen=True)
class LockTelemetryDelta:
    """Polling-window metrics derived from two telemetry snapshots."""

    lock_id: int
    memory_waste_slots: int
    memory_waste_ratio: float
    acquire_delta: int
    miss_delta: int
    overflow_delta: int

    @property
    def miss_ratio(self) -> float:
        if self.acquire_delta <= 0:
            return 0.0
        return self.miss_delta / self.acquire_delta

    @property
    def queue_overflow_ratio(self) -> float:
        if self.acquire_delta <= 0:
            return 0.0
        return self.overflow_delta / self.acquire_delta

    @classmethod
    def from_snapshots(
        cls,
        previous: LockTelemetrySnapshot,
        current: LockTelemetrySnapshot,
    ) -> "LockTelemetryDelta":
        if previous.lock_id != current.lock_id:
            raise ValueError("telemetry snapshots must be for the same lock")
        return cls(
            lock_id=current.lock_id,
            memory_waste_slots=current.memory_waste_slots,
            memory_waste_ratio=current.memory_waste_ratio,
            acquire_delta=max(current.acquire_count - previous.acquire_count, 0),
            miss_delta=max(current.miss_count - previous.miss_count, 0),
            overflow_delta=max(current.overflow_count - previous.overflow_count, 0),
        )


class StatsCollector:
    """Read switch counters/registers needed by the migration policy."""

    def __init__(self, switch: P4RuntimeSwitch):
        self.switch = switch

    def read_lock_queue_stats(self, lock_id: int) -> LockQueueStats:
        """Read per-lock queue registers."""

        return LockQueueStats(
            lock_id=lock_id,
            base=self._read_register(LOCK_QUEUE_BASE_REGISTER, lock_id),
            depth=self._read_register(LOCK_QUEUE_DEPTH_REGISTER, lock_id),
            head=self._read_register(LOCK_QUEUE_HEAD_REGISTER, lock_id),
            tail=self._read_register(LOCK_QUEUE_TAIL_REGISTER, lock_id),
            occupancy=self._read_register(LOCK_QUEUE_OCCUPANCY_REGISTER, lock_id),
            holder=self._read_register(LOCK_HOLDER_REGISTER, lock_id),
        )

    def read_lock_telemetry(self, lock_id: int) -> LockTelemetrySnapshot:
        """Read all controller-side telemetry inputs for one lock."""

        queue = self.read_lock_queue_stats(lock_id)
        return LockTelemetrySnapshot(
            lock_id=lock_id,
            base=queue.base,
            depth=queue.depth,
            head=queue.head,
            tail=queue.tail,
            occupancy=queue.occupancy,
            holder=queue.holder,
            acquire_count=self._read_register(LOCK_ACQUIRE_COUNT_REGISTER, lock_id),
            miss_count=self._read_register(LOCK_MISS_COUNT_REGISTER, lock_id),
            overflow_count=self._read_register(LOCK_OVERFLOW_COUNT_REGISTER, lock_id),
        )

    def read_locks_telemetry(
        self,
        lock_ids: Iterable[int],
    ) -> list[LockTelemetrySnapshot]:
        return [self.read_lock_telemetry(lock_id) for lock_id in lock_ids]

    def _read_register(self, register_name: str, lock_id: int) -> int:
        return self.switch.read_register_cell(register_name, lock_id)
