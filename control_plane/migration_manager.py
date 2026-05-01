from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LockState(Enum):
    HOT_FREE = 1
    HOT_HELD = 2
    COLD = 3
    DRAINING = 4
    BUFFERING = 5


@dataclass(frozen=True)
class MigrationPlan:
    """One requested lock placement transition."""

    lock_id: int
    source_state: LockState
    target_state: LockState
    queue_base: int | None = None
    queue_depth: int | None = None


class MigrationManager:
    """Coordinates lock transitions between switch and lock-server ownership."""

    def migrate_to_server(self, lock_id: int) -> MigrationPlan:
        return MigrationPlan(
            lock_id=lock_id,
            source_state=LockState.HOT_HELD,
            target_state=LockState.DRAINING,
        )

    def migrate_to_switch(
        self,
        lock_id: int,
        queue_base: int,
        queue_depth: int,
    ) -> MigrationPlan:
        return MigrationPlan(
            lock_id=lock_id,
            source_state=LockState.COLD,
            target_state=LockState.BUFFERING,
            queue_base=queue_base,
            queue_depth=queue_depth,
        )
