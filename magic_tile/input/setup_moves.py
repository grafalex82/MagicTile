"""Recording and reverse playback of concrete setup turns."""

from __future__ import annotations

from dataclasses import dataclass

from magic_tile.input.turn_history import TurnCommand


@dataclass(frozen=True, slots=True)
class SetupMove:
    """A preparation sequence that is either recording or ready to unwind."""

    commands: tuple[TurnCommand, ...] = ()
    recording: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.commands, tuple) or any(
            not isinstance(command, TurnCommand) for command in self.commands
        ):
            raise TypeError("commands must be a tuple of TurnCommand values")
        if not isinstance(self.recording, bool):
            raise TypeError("recording must be a boolean")
        if not self.recording and not self.commands:
            raise ValueError("a finished setup move must contain at least one command")

    @property
    def rollback_commands(self) -> tuple[TurnCommand, ...]:
        """Return the sequence that unwinds these setup turns."""
        return tuple(command.inverse for command in reversed(self.commands))

    def synchronize(self, commands: tuple[TurnCommand, ...]) -> SetupMove:
        """Replace a live recording with the active setup-history segment."""
        if not self.recording:
            return self
        return SetupMove(commands, recording=True)

    def finish(self) -> SetupMove:
        """Stop adding turns while keeping the sequence available to unwind."""
        return SetupMove(self.commands, recording=False)
