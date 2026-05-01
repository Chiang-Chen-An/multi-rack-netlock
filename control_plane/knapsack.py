from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LockMemoryCandidate:
    """Candidate lock for switch memory allocation."""

    lock_id: int
    value: float
    slots: int


def choose_locks_for_switch(
    candidates: list[LockMemoryCandidate],
    slot_budget: int,
) -> list[LockMemoryCandidate]:
    """Choose locks that maximize value under a switch queue-slot budget."""

    if slot_budget <= 0:
        return []

    dp: list[tuple[float, list[LockMemoryCandidate]]] = [
        (0.0, []) for _ in range(slot_budget + 1)
    ]

    for candidate in candidates:
        if candidate.slots <= 0:
            continue
        for budget in range(slot_budget, candidate.slots - 1, -1):
            prev_value, prev_items = dp[budget - candidate.slots]
            next_value = prev_value + candidate.value
            if next_value > dp[budget][0]:
                dp[budget] = (next_value, [*prev_items, candidate])

    return dp[slot_budget][1]
