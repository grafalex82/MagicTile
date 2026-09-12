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


class TurnHistory:
    """Maintain unbounded standard undo and redo stacks for turns."""

    def __init__(self) -> None:
        self._undo_stack: list[TurnCommand] = []
        self._redo_stack: list[TurnCommand] = []

    def record(self, command: TurnCommand) -> None:
        """Record a newly made turn and discard its obsolete redo branch."""
        self._undo_stack.append(command)
        self._redo_stack.clear()

    def undo(self) -> TurnCommand | None:
        """Return the inverse of the last turn, or ``None`` when unavailable."""
        if not self._undo_stack:
            return None
        command = self._undo_stack.pop()
        self._redo_stack.append(command)
        return command.inverse

    def redo(self) -> TurnCommand | None:
        """Return the next undone turn, or ``None`` when unavailable."""
        if not self._redo_stack:
            return None
        command = self._redo_stack.pop()
        self._undo_stack.append(command)
        return command
