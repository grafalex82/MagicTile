"""Recording, serialization, and expansion of face-relative macros."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from magic_tile.domain import Face, HexCoordinate, PeriodicBoard, TurnDirection
from magic_tile.input.turn_history import TurnCommand

MACRO_SLOT_COUNT = 10
_MACRO_PATTERN = re.compile(r"\s*\d+['’]?(?:(?:\s+|\s*-\s*)\d+['’]?)*\s*")


@dataclass(frozen=True, slots=True)
class MacroTurn:
    """One turn referencing a face by its one-based macro number."""

    face_number: int
    direction: TurnDirection

    def __post_init__(self) -> None:
        valid_number = isinstance(self.face_number, int) and not isinstance(self.face_number, bool)
        if not valid_number or self.face_number < 1:
            raise ValueError("macro face numbers must be positive integers")
        if not isinstance(self.direction, TurnDirection):
            raise TypeError("direction must be a TurnDirection")

    @property
    def inverse(self) -> MacroTurn:
        """Return this move with the opposite turn direction."""
        return MacroTurn(self.face_number, TurnDirection(-int(self.direction)))


@dataclass(frozen=True, slots=True)
class Macro:
    """A non-empty sequence of turns using relative face numbers."""

    turns: tuple[MacroTurn, ...]

    def __post_init__(self) -> None:
        if not self.turns:
            raise ValueError("a macro must contain at least one turn")
        face_numbers = {turn.face_number for turn in self.turns}
        expected = set(range(1, max(face_numbers) + 1))
        if face_numbers != expected:
            raise ValueError("macro face numbers must be contiguous and start at 1")

    @property
    def required_face_count(self) -> int:
        """Return the exact number of selected faces needed for playback."""
        return max(turn.face_number for turn in self.turns)

    @property
    def inverse(self) -> Macro:
        """Return the macro in reverse order with every direction inverted."""
        return Macro(tuple(turn.inverse for turn in reversed(self.turns)))

    def commands(
        self,
        face_coordinates: tuple[HexCoordinate, ...],
        *,
        reverse: bool = False,
    ) -> tuple[TurnCommand, ...]:
        """Resolve relative face numbers to concrete board coordinates."""
        if len(face_coordinates) != self.required_face_count:
            raise ValueError(
                f"macro requires {self.required_face_count} faces; selected {len(face_coordinates)}"
            )
        macro = self.inverse if reverse else self
        return tuple(
            TurnCommand(face_coordinates[turn.face_number - 1], turn.direction) for turn in macro.turns
        )


def parse_macro(text: str) -> Macro:
    """Parse the settings-file macro notation."""
    if not isinstance(text, str) or not _MACRO_PATTERN.fullmatch(text):
        raise ValueError("a macro must contain numbered moves separated by spaces or hyphens")
    turns = tuple(
        MacroTurn(
            int(face_number),
            TurnDirection.COUNTERCLOCKWISE if apostrophe else TurnDirection.CLOCKWISE,
        )
        for face_number, apostrophe in re.findall(r"(\d+)(['’]?)", text)
    )
    return Macro(turns)


def serialize_macro(macro: Macro) -> str:
    """Serialize a macro in the canonical hyphen-separated notation."""
    def serialize_turn(turn: MacroTurn) -> str:
        apostrophe = "'" if turn.direction is TurnDirection.COUNTERCLOCKWISE else ""
        return f"{turn.face_number}{apostrophe}"

    return "-".join(serialize_turn(turn) for turn in macro.turns)


@dataclass(slots=True)
class MacroRecording:
    """A live recording whose face numbering follows first use."""

    slot: int
    _face_numbers: dict[Face, int] = field(default_factory=dict, init=False, repr=False)
    _commands: list[TurnCommand] = field(default_factory=list, init=False, repr=False)
    _turns: list[MacroTurn] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.slot, bool) or not 0 <= self.slot < MACRO_SLOT_COUNT:
            raise ValueError("macro slot must be between 0 and 9")

    @property
    def face_numbers(self) -> dict[Face, int]:
        """Return a copy of logical faces and their displayed numbers."""
        return self._face_numbers.copy()

    @property
    def move_count(self) -> int:
        """Return the number of turns recorded so far."""
        return len(self._turns)

    @property
    def macro(self) -> Macro:
        """Return the completed macro, rejecting an empty recording."""
        return Macro(tuple(self._turns))

    @property
    def rollback_commands(self) -> tuple[TurnCommand, ...]:
        """Return commands that restore the state from before recording."""
        return tuple(command.inverse for command in reversed(self._commands))

    def record(self, face: Face, command: TurnCommand) -> None:
        """Append a normal board turn and assign its face number on first use."""
        face_number = self._face_numbers.setdefault(face, len(self._face_numbers) + 1)
        self._commands.append(command)
        self._turns.append(MacroTurn(face_number, command.direction))

    def synchronize(self, board: PeriodicBoard, commands: tuple[TurnCommand, ...]) -> None:
        """Rebuild the recording from the active segment of the shared history."""
        self._face_numbers.clear()
        self._commands.clear()
        self._turns.clear()
        for command in commands:
            self.record(board.face_at(command.coordinate), command)


@dataclass(slots=True)
class MacroSelection:
    """Ordered unique logical faces selected for macro playback."""

    _faces: list[Face] = field(default_factory=list, init=False, repr=False)
    _coordinates: list[HexCoordinate] = field(default_factory=list, init=False, repr=False)

    @property
    def coordinates(self) -> tuple[HexCoordinate, ...]:
        """Return representative coordinates in selection order."""
        return tuple(self._coordinates)

    @property
    def face_numbers(self) -> dict[Face, int]:
        """Return logical faces mapped to their one-based selection numbers."""
        return {face: index for index, face in enumerate(self._faces, start=1)}

    def __bool__(self) -> bool:
        return bool(self._faces)

    def add(self, board: PeriodicBoard, coordinate: HexCoordinate) -> bool:
        """Add a logical face once, returning whether the selection changed."""
        face = board.face_at(coordinate)
        if face in self._faces:
            return False
        self._faces.append(face)
        self._coordinates.append(coordinate)
        return True

    def clear(self) -> None:
        """Remove every selected face."""
        self._faces.clear()
        self._coordinates.clear()
