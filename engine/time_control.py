"""Deterministic total-clock support for 15+0 Surakarta matches.

The searcher still receives a per-turn soft deadline.  This module is the
authoritative owner of the match clock: it measures elapsed wall time,
maintains an independent balance for each colour, and never adds increment.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from .board import Color


ClockSource = Callable[[], float]


@dataclass
class TotalClock:
    """A two-sided Fischer-style clock configured for zero increment.

    ``now`` is injectable so tests can advance time without sleeping.  Values
    are stored as floats because ``perf_counter`` is fractional; callers can
    round them only when presenting or serialising a result.
    """

    initial_ms: float = 900_000
    increment_ms: float = 0
    safety_ms: float = 25
    now: ClockSource = time.perf_counter
    _remaining: dict[Color, float] = field(init=False, repr=False)
    _elapsed: dict[Color, float] = field(init=False, repr=False)
    _active_side: Color | None = field(default=None, init=False, repr=False)
    _turn_started_at: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.initial_ms <= 0:
            raise ValueError("initial_ms must be positive")
        if self.increment_ms != 0:
            raise ValueError("Surakarta 2026 competition mode is 15+0; increment_ms must be zero")
        self._remaining = {Color.BLACK: float(self.initial_ms), Color.RED: float(self.initial_ms)}
        self._elapsed = {Color.BLACK: 0.0, Color.RED: 0.0}

    def remaining_ms(self, side: Color) -> float:
        """Return a live balance, including an in-progress turn if present."""
        self._require_player(side)
        remaining = self._remaining[side]
        if self._active_side == side and self._turn_started_at is not None:
            remaining -= max(0.0, (self.now() - self._turn_started_at) * 1000.0)
        return remaining

    def elapsed_ms(self, side: Color) -> float:
        self._require_player(side)
        elapsed = self._elapsed[side]
        if self._active_side == side and self._turn_started_at is not None:
            elapsed += max(0.0, (self.now() - self._turn_started_at) * 1000.0)
        return elapsed

    def start_turn(self, side: Color) -> bool:
        """Start ``side``'s clock and return whether it still has time."""
        self._require_player(side)
        if self._active_side is not None:
            raise RuntimeError("cannot start a turn while another clock is active")
        if self._remaining[side] <= 0:
            return False
        self._active_side = side
        self._turn_started_at = self.now()
        return True

    def stop_turn(self, side: Color) -> float:
        """Stop ``side``'s clock and return elapsed milliseconds for the turn."""
        self._require_player(side)
        if self._active_side != side or self._turn_started_at is None:
            raise RuntimeError("attempted to stop a clock that is not active")
        elapsed = max(0.0, (self.now() - self._turn_started_at) * 1000.0)
        self._remaining[side] -= elapsed
        self._elapsed[side] += elapsed
        self._active_side = None
        self._turn_started_at = None
        return elapsed

    def is_expired(self, side: Color) -> bool:
        return self.remaining_ms(side) <= 0

    def allocate_turn_ms(
        self,
        side: Color,
        *,
        expected_remaining_turns: int,
        reserve_ms: float = 90_000,
        min_turn_ms: float = 50,
        max_turn_ms: float = 20_000,
    ) -> int:
        """Allocate a conservative search budget without spending the reserve.

        The caller supplies an estimate of remaining turns, which makes this
        policy work for both live UI play and bounded headless matches.  The
        returned value is always strictly below the current balance by the
        safety margin whenever the player still has usable time.
        """
        self._require_player(side)
        if expected_remaining_turns <= 0:
            raise ValueError("expected_remaining_turns must be positive")
        if min_turn_ms <= 0 or max_turn_ms < min_turn_ms:
            raise ValueError("invalid per-turn time bounds")

        usable = max(0.0, self.remaining_ms(side) - self.safety_ms)
        if usable <= 0:
            return 0
        protected = min(max(0.0, reserve_ms), usable)
        spendable = max(0.0, usable - protected)
        if spendable <= 0:
            return max(1, int(min(min_turn_ms, usable)))

        budget = spendable / expected_remaining_turns
        return max(1, int(min(max_turn_ms, max(min_turn_ms, budget), usable)))

    def snapshot(self) -> dict[str, float]:
        """Return JSON-friendly balances and cumulative wall-clock usage."""
        return {
            "black_remaining_ms": round(self.remaining_ms(Color.BLACK), 3),
            "red_remaining_ms": round(self.remaining_ms(Color.RED), 3),
            "black_elapsed_ms": round(self.elapsed_ms(Color.BLACK), 3),
            "red_elapsed_ms": round(self.elapsed_ms(Color.RED), 3),
            "initial_ms": round(float(self.initial_ms), 3),
            "increment_ms": round(float(self.increment_ms), 3),
        }

    @staticmethod
    def _require_player(side: Color) -> None:
        if side not in (Color.BLACK, Color.RED):
            raise ValueError("clock side must be BLACK or RED")
