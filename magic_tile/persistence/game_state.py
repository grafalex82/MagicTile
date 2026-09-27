"""Versioned JSON persistence for a complete MagicTile game session."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from magic_tile.domain import BoardMode, FaceColor, HexCoordinate, PeriodicBoard, TurnDirection
from magic_tile.input import SetupMove, TurnCommand

GAME_STATE_FORMAT = "magic-tile-game"
GAME_STATE_VERSION = 1


@dataclass(frozen=True, slots=True)
class GameState:
    """Serializable board and scoring state for one game session."""

    stickers: tuple[tuple[FaceColor, ...], ...]
    game_active: bool
    move_count: int
    setup_move: SetupMove | None = None
    mode: BoardMode = BoardMode.TORUS

    def __post_init__(self) -> None:
        if not isinstance(self.game_active, bool):
            raise TypeError("game_active must be a boolean")
        if isinstance(self.move_count, bool) or not isinstance(self.move_count, int):
            raise TypeError("move_count must be an integer")
        if self.move_count < 0:
            raise ValueError("move_count cannot be negative")
        if self.setup_move is not None and not isinstance(self.setup_move, SetupMove):
            raise TypeError("setup_move must be a SetupMove or None")
        if not isinstance(self.mode, BoardMode):
            raise TypeError("mode must be a BoardMode")

        # Reuse the board model's structural validation without retaining or
        # modifying a temporary board after construction.
        PeriodicBoard(self.mode).restore_sticker_state(self.stickers)

    @classmethod
    def capture(
        cls,
        board: PeriodicBoard,
        *,
        game_active: bool,
        move_count: int,
        setup_move: SetupMove | None = None,
    ) -> GameState:
        """Capture the settled model and score from the current session."""
        if not isinstance(board, PeriodicBoard):
            raise TypeError("board must be a PeriodicBoard")
        return cls(board.sticker_state(), game_active, move_count, setup_move, board.mode)

    def restore_board(self, board: PeriodicBoard) -> None:
        """Apply this saved sticker arrangement to *board*."""
        if not isinstance(board, PeriodicBoard):
            raise TypeError("board must be a PeriodicBoard")
        if board.mode is not self.mode:
            raise ValueError("saved game mode does not match the target board")
        board.restore_sticker_state(self.stickers)


def load_game_state(path: Path | str) -> GameState:
    """Load and validate a game state from a versioned JSON file."""
    save_path = Path(path)
    try:
        data = json.loads(save_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid game save file: {save_path}") from error

    if not isinstance(data, dict):
        raise ValueError("Game save must contain a JSON object.")
    if data.get("format") != GAME_STATE_FORMAT:
        raise ValueError("File is not a MagicTile game save.")
    version = data.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version != GAME_STATE_VERSION:
        raise ValueError(f"Unsupported game save version: {version!r}.")

    game_active = data.get("game_active")
    move_count = data.get("move_count")
    if not isinstance(game_active, bool):
        raise ValueError("'game_active' must be a boolean.")
    if isinstance(move_count, bool) or not isinstance(move_count, int) or move_count < 0:
        raise ValueError("'move_count' must be a non-negative integer.")

    raw_mode = data.get("mode", BoardMode.TORUS.value)
    try:
        mode = BoardMode(raw_mode)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Unknown game mode: {raw_mode!r}.") from error

    raw_faces = data.get("faces")
    board = PeriodicBoard(mode)
    if not isinstance(raw_faces, list) or len(raw_faces) != len(board.faces):
        raise ValueError(f"'faces' must contain exactly {len(board.faces)} face objects.")

    allowed_colors = {face.color for face in board.faces}
    stickers: list[tuple[FaceColor, ...]] = []
    for index, (raw_face, face) in enumerate(zip(raw_faces, board.faces, strict=True)):
        if not isinstance(raw_face, dict):
            raise ValueError(f"Face {index} must be an object.")
        if raw_face.get("center_color") != face.color.name:
            raise ValueError(f"Face {index} has an unexpected center color.")
        edges = _parse_colors(
            raw_face.get("edge_colors"), f"face {index} edge_colors", allowed_colors
        )
        corners = _parse_colors(
            raw_face.get("corner_colors"), f"face {index} corner_colors", allowed_colors
        )
        stickers.append(edges + corners)

    setup_move = _parse_setup_move(data.get("setup_move"))
    return GameState(tuple(stickers), game_active, move_count, setup_move, mode)


def save_game_state(state: GameState, path: Path | str) -> None:
    """Atomically write *state* to a human-readable JSON file."""
    if not isinstance(state, GameState):
        raise TypeError("state must be a GameState")
    save_path = Path(path)
    temporary_path = save_path.with_name(f".{save_path.name}.tmp")
    data = {
        "format": GAME_STATE_FORMAT,
        "version": GAME_STATE_VERSION,
        "mode": state.mode.value,
        "game_active": state.game_active,
        "move_count": state.move_count,
        "setup_move": _serialize_setup_move(state.setup_move),
        "faces": [
            {
                "center_color": face.color.name,
                "edge_colors": [color.name for color in face_state[:6]],
                "corner_colors": [color.name for color in face_state[6:]],
            }
            for face, face_state in zip(PeriodicBoard(state.mode).faces, state.stickers, strict=True)
        ],
    }
    temporary_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(save_path)


def _parse_setup_move(value: object) -> SetupMove | None:
    """Parse the optional active setup sequence from a save."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("'setup_move' must be an object or null.")
    recording = value.get("recording")
    raw_commands = value.get("commands")
    if not isinstance(recording, bool):
        raise ValueError("'setup_move.recording' must be a boolean.")
    if not isinstance(raw_commands, list):
        raise ValueError("'setup_move.commands' must be a list.")

    commands: list[TurnCommand] = []
    for index, raw_command in enumerate(raw_commands):
        if not isinstance(raw_command, dict):
            raise ValueError(f"Setup command {index} must be an object.")
        q = raw_command.get("q")
        r = raw_command.get("r")
        direction = raw_command.get("direction")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in (q, r)):
            raise ValueError(f"Setup command {index} coordinates must be integers.")
        if direction not in ("clockwise", "counterclockwise"):
            raise ValueError(f"Setup command {index} has an invalid direction.")
        commands.append(
            TurnCommand(
                HexCoordinate(q, r),
                (
                    TurnDirection.CLOCKWISE
                    if direction == "clockwise"
                    else TurnDirection.COUNTERCLOCKWISE
                ),
            )
        )
    if not recording and not commands:
        return None
    return SetupMove(tuple(commands), recording)


def _serialize_setup_move(setup_move: SetupMove | None) -> dict[str, object] | None:
    """Convert an active setup sequence to its JSON-compatible form."""
    if setup_move is None:
        return None
    return {
        "recording": setup_move.recording,
        "commands": [
            {
                "q": command.coordinate.q,
                "r": command.coordinate.r,
                "direction": (
                    "clockwise"
                    if command.direction is TurnDirection.CLOCKWISE
                    else "counterclockwise"
                ),
            }
            for command in setup_move.commands
        ],
    }


def _parse_colors(
    value: object,
    field_name: str,
    allowed_colors: set[FaceColor],
) -> tuple[FaceColor, ...]:
    """Parse one six-color sticker list with a field-specific error."""
    if not isinstance(value, list) or len(value) != 6 or any(not isinstance(item, str) for item in value):
        raise ValueError(f"'{field_name}' must contain exactly six color names.")
    try:
        colors = tuple(FaceColor[item] for item in value)
    except KeyError as error:
        raise ValueError(f"'{field_name}' contains an unknown color: {error.args[0]!r}.") from error
    if any(color not in allowed_colors for color in colors):
        raise ValueError(f"'{field_name}' contains a color unavailable in this game mode.")
    return colors
