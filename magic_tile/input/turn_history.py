"""Unbounded undo and redo history for face turns."""

from __future__ import annotations

from dataclasses import dataclass

from magic_tile.domain import HexCoordinate, TurnDirection


@dataclass(frozen=True, slots=True)
class TurnCommand:
    """A replayable turn, identified by its selected board coordinate."""

    coordinate: HexCoordinate
    direction: TurnDirection

    @property
    def inverse(self) -> TurnCommand:
        """Return the turn that restores the state before this command."""
        return TurnCommand(self.coordinate, TurnDirection(-int(self.direction)))


@dataclass(frozen=True, slots=True)
class TurnHistorySnapshot:
    """Immutable copy of a linear history and its current position."""

    commands: tuple[TurnCommand, ...]
    position: int


class TurnHistory:
    """Maintain one unbounded linear command history with an undo/redo cursor."""

    def __init__(self) -> None:
        self._commands: list[TurnCommand] = []
        self._position = 0

    def record(self, command: TurnCommand) -> None:
        """Record a newly made turn and discard its obsolete redo branch."""
        del self._commands[self._position :]
        self._commands.append(command)
        self._position += 1

    def undo(self, minimum_position: int = 0) -> TurnCommand | None:
        """Move the cursor backward without crossing *minimum_position*."""
        if not 0 <= minimum_position <= self._position:
            raise ValueError("minimum_position must be between zero and the current position")
        if self._position == minimum_position:
            return None
        self._position -= 1
        return self._commands[self._position].inverse

    def redo(self) -> TurnCommand | None:
        """Return the next undone turn, or ``None`` when unavailable."""
        if self._position == len(self._commands):
            return None
        command = self._commands[self._position]
        self._position += 1
        return command

    def snapshot(self) -> TurnHistorySnapshot:
        """Capture the timeline and cursor so provisional turns can be canceled."""
        return TurnHistorySnapshot(tuple(self._commands), self._position)

    def restore(self, snapshot: TurnHistorySnapshot) -> None:
        """Restore a snapshot without generating undo or redo commands."""
        if not isinstance(snapshot, TurnHistorySnapshot):
            raise TypeError("snapshot must be a TurnHistorySnapshot")
        self._commands = list(snapshot.commands)
        self._position = snapshot.position

    def commands_since(self, position: int) -> tuple[TurnCommand, ...]:
        """Return currently applied commands after a prior cursor position."""
        if not 0 <= position <= self._position:
            raise ValueError("position must be between zero and the current position")
        return tuple(self._commands[position : self._position])
