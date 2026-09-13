"""Input mapping, move history, macros, and setup-move commands."""

from magic_tile.input.macros import (
    MACRO_SLOT_COUNT,
    Macro,
    MacroRecording,
    MacroSelection,
    MacroTurn,
    parse_macro,
    serialize_macro,
)
from magic_tile.input.setup_moves import SetupMove
from magic_tile.input.turn_history import TurnCommand, TurnHistory, TurnHistorySnapshot

__all__ = (
    "MACRO_SLOT_COUNT",
    "Macro",
    "MacroRecording",
    "MacroSelection",
    "MacroTurn",
    "SetupMove",
    "TurnCommand",
    "TurnHistory",
    "TurnHistorySnapshot",
    "parse_macro",
    "serialize_macro",
)
