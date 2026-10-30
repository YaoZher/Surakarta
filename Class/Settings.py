from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = PROJECT_ROOT / "output" / "ui_settings.json"

DEPTH_OPTIONS = (2, 3, 4, 5, 6, 7)
TIME_OPTIONS_MS = (250, 500, 1_000, 2_000, 5_000, 10_000)
MAX_TOTAL_CLOCK_MS = 120 * 60_000
CLOCK_OPTIONS_MS = (0, *(minute * 60_000 for minute in range(1, 121)))
PROFILE_OPTIONS = ("baseline", "candidate_016", "solid", "paper_2022")


@dataclass(frozen=True, slots=True)
class AISettings:
    """User-facing AI controls shared by the Pygame UI and SearchAI."""

    depth: int = 5
    time_ms: int = 5_000
    total_time_ms: int = 900_000
    eval_profile: str = "baseline"

    def normalized(self) -> AISettings:
        depth = min(DEPTH_OPTIONS, key=lambda value: abs(value - int(self.depth)))
        time_ms = min(TIME_OPTIONS_MS, key=lambda value: abs(value - int(self.time_ms)))
        requested_clock = int(self.total_time_ms)
        total_time_ms = (0 if requested_clock <= 0 else 900_000 if requested_clock < 60_000
                         else min(MAX_TOTAL_CLOCK_MS, round(requested_clock / 60_000) * 60_000))
        profile = self.eval_profile if self.eval_profile in PROFILE_OPTIONS else "baseline"
        return replace(
            self,
            depth=depth,
            time_ms=time_ms,
            total_time_ms=total_time_ms,
            eval_profile=profile,
        )

    def to_dict(self) -> dict[str, int | str]:
        value = self.normalized()
        return {
            "depth": value.depth,
            "time_ms": value.time_ms,
            "total_time_ms": value.total_time_ms,
            "eval_profile": value.eval_profile,
        }

    @classmethod
    def from_dict(cls, payload: object) -> AISettings:
        if not isinstance(payload, dict):
            return cls()
        try:
            value = cls(
                depth=int(payload.get("depth", cls.depth)),
                time_ms=int(payload.get("time_ms", cls.time_ms)),
                total_time_ms=int(payload.get("total_time_ms", cls.total_time_ms)),
                eval_profile=str(payload.get("eval_profile", cls.eval_profile)),
            )
        except (TypeError, ValueError):
            return cls()
        return value.normalized()

    @classmethod
    def load(cls, path: Path = SETTINGS_PATH) -> AISettings:
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            return cls()

    def save(self, path: Path = SETTINGS_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.normalized().to_dict(), ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
