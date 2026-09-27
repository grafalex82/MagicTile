"""Application settings stored beside the executable's working directory."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path

from magic_tile.domain import BoardMode
from magic_tile.input.macros import (
    MACRO_SLOT_COUNT,
    Macro,
    parse_macro,
    serialize_macro,
)

SETTINGS_FILENAME = "settings.json"
DEFAULT_TURN_ANIMATION_DURATION_SECONDS = 0.5


@dataclass(frozen=True, slots=True)
class Settings:
    """Values that configure the application's presentation and behaviour."""

    turn_animation_duration_seconds: float = DEFAULT_TURN_ANIMATION_DURATION_SECONDS
    macros: tuple[Macro | None, ...] = field(default_factory=lambda: (None,) * MACRO_SLOT_COUNT)
    game_mode: BoardMode = BoardMode.TORUS

    def __post_init__(self) -> None:
        if not isinstance(self.game_mode, BoardMode):
            raise TypeError("game_mode must be a BoardMode")
        if len(self.macros) != MACRO_SLOT_COUNT:
            raise ValueError("settings must contain exactly 10 macro slots")
        if any(macro is not None and not isinstance(macro, Macro) for macro in self.macros):
            raise TypeError("each macro slot must contain a Macro or None")

    def with_macro(self, slot: int, macro: Macro) -> Settings:
        """Return settings with one macro slot replaced."""
        if isinstance(slot, bool) or not 0 <= slot < MACRO_SLOT_COUNT:
            raise ValueError("macro slot must be between 0 and 9")
        macros = list(self.macros)
        macros[slot] = macro
        return replace(self, macros=tuple(macros))

    def with_game_mode(self, game_mode: BoardMode) -> Settings:
        """Return settings with the startup game mode replaced."""
        if not isinstance(game_mode, BoardMode):
            raise TypeError("game_mode must be a BoardMode")
        return replace(self, game_mode=game_mode)


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

    raw_game_mode = data.get("game_mode", BoardMode.TORUS.value)
    try:
        game_mode = BoardMode(raw_game_mode)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Unknown game mode: {raw_game_mode!r}.") from error

    raw_macros = data.get("macros", {})
    if not isinstance(raw_macros, dict):
        raise ValueError("'macros' must be an object whose keys are slots from 0 to 9.")
    macros: list[Macro | None] = [None] * MACRO_SLOT_COUNT
    for raw_slot, raw_macro in raw_macros.items():
        if not isinstance(raw_slot, str) or not raw_slot.isdigit() or not 0 <= int(raw_slot) < 10:
            raise ValueError("Macro slot keys must be strings from '0' to '9'.")
        if not isinstance(raw_macro, str):
            raise ValueError(f"Macro slot {raw_slot} must contain a string.")
        try:
            macros[int(raw_slot)] = parse_macro(raw_macro)
        except ValueError as error:
            raise ValueError(f"Invalid macro in slot {raw_slot}: {error}") from error

    return Settings(
        turn_animation_duration_seconds=float(duration),
        macros=tuple(macros),
        game_mode=game_mode,
    )


def _write_default_settings(settings_path: Path, settings: Settings) -> None:
    """Create the initial settings file for future editable configuration."""
    _write_settings(settings_path, settings)


def save_settings(settings: Settings, directory: Path | None = None) -> None:
    """Atomically persist settings in *directory* or the current directory."""
    settings_path = (Path.cwd() if directory is None else directory) / SETTINGS_FILENAME
    temporary_path = settings_path.with_name(f".{settings_path.name}.tmp")
    _write_settings(temporary_path, settings)
    temporary_path.replace(settings_path)


def _write_settings(settings_path: Path, settings: Settings) -> None:
    """Write a complete, human-editable settings document."""
    data = {
        "turn_animation_duration_seconds": settings.turn_animation_duration_seconds,
        "game_mode": settings.game_mode.value,
        "macros": {
            str(slot): serialize_macro(macro)
            for slot, macro in enumerate(settings.macros)
            if macro is not None
        },
    }
    settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
