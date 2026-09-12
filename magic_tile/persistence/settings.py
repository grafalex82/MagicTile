"""Application settings stored beside the executable's working directory."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path


SETTINGS_FILENAME = "settings.json"
DEFAULT_TURN_ANIMATION_DURATION_SECONDS = 0.5


@dataclass(frozen=True, slots=True)
class Settings:
    """Values that configure the application's presentation and behaviour."""

    turn_animation_duration_seconds: float = DEFAULT_TURN_ANIMATION_DURATION_SECONDS


def load_settings(directory: Path | None = None) -> Settings:
    """Load settings from *directory*, creating the default file when absent.

    ``directory`` is optional so the application naturally uses its current
    working directory, while callers and tests can supply another location.
    """
    settings_path = (Path.cwd() if directory is None else directory) / SETTINGS_FILENAME
    if not settings_path.exists():
        settings = Settings()
        _write_default_settings(settings_path, settings)
        return settings

    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid settings file: {settings_path}") from error

    try:
        duration = data["turn_animation_duration_seconds"]
    except (KeyError, TypeError) as error:
        raise ValueError("Settings must contain 'turn_animation_duration_seconds'.") from error

    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        raise ValueError("'turn_animation_duration_seconds' must be a number.")
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("'turn_animation_duration_seconds' must be greater than zero.")

    return Settings(turn_animation_duration_seconds=float(duration))


def _write_default_settings(settings_path: Path, settings: Settings) -> None:
    """Create the initial settings file for future editable configuration."""
    settings_path.write_text(json.dumps(asdict(settings), indent=2) + "\n", encoding="utf-8")
