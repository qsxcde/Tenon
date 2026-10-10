"""Serial slot arbitration for delegated child runs."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Generic, TypeVar

__all__ = ["SubagentSlotRegistry"]

T = TypeVar("T")


class SubagentSlotRegistry(Generic[T]):
    """Track in-flight delegations with duplicate protection.

    Reservation legality is a domain decision: one ``delegation_id`` may never
    have two live child runs, no matter which child factory the application
    injects. The per-parent-run quota (``max_children_per_run``) is enforced at
    the ``delegate`` tool boundary because it counts accepted delegations
    cumulatively rather than concurrently.
    """

    def __init__(self, capacity: int | None = None) -> None:
        if capacity is not None and capacity <= 0:
            raise ValueError("capacity 必须为正整数")
        self._capacity = capacity
        self._payloads: dict[str, T] = {}

    @property
    def capacity(self) -> int | None:
        return self._capacity

    def __len__(self) -> int:
        return len(self._payloads)

    def __iter__(self) -> Iterator[str]:
        return iter(tuple(self._payloads))

    def ids(self) -> tuple[str, ...]:
        """Return reserved delegation ids in reservation order."""
        return tuple(self._payloads)

    def items(self) -> tuple[tuple[str, T], ...]:
        """Return reserved pairs in reservation order for diagnostics."""
        return tuple(self._payloads.items())

    def contains(self, delegation_id: str) -> bool:
        return delegation_id in self._payloads

    def is_full(self) -> bool:
        return self._capacity is not None and len(self._payloads) >= self._capacity

    def reserve(self, delegation_id: str, payload: T) -> bool:
        """Reserve one slot; reject duplicates and over-capacity reservations."""
        if not delegation_id or delegation_id in self._payloads:
            return False
        if self.is_full():
            return False
        self._payloads[delegation_id] = payload
        return True

    def get(self, delegation_id: str) -> T | None:
        return self._payloads.get(delegation_id)

    def release(self, delegation_id: str) -> T | None:
        return self._payloads.pop(delegation_id, None)
