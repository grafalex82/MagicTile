"""Versioned JSON persistence for a complete MagicTile game session."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from magic_tile.domain import FaceColor, PeriodicBoard

GAME_STATE_FORMAT = "magic-tile-game"
GAME_STATE_VERSION = 1


@dataclass(frozen=True, slots=True)
class GameState:
    """Serializable board and scoring state for one game session."""

    stickers: tuple[tuple[FaceColor, ...], ...]
    game_active: bool
    move_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.game_active, bool):
            raise TypeError("game_active must be a boolean")
        if isinstance(self.move_count, bool) or not isinstance(self.move_count, int):
            raise TypeError("move_count must be an integer")
        if self.move_count < 0:
            raise ValueError("move_count cannot be negative")

        # Reuse the board model's structural validation without retaining or
        # modifying a temporary board after construction.
        PeriodicBoard().restore_sticker_state(self.stickers)

    @classmethod
    def capture(cls, board: PeriodicBoard, *, game_active: bool, move_count: int) -> GameState:
        """Capture the settled model and score from the current session."""
        if not isinstance(board, PeriodicBoard):
            raise TypeError("board must be a PeriodicBoard")
        return cls(board.sticker_state(), game_active, move_count)

    def restore_board(self, board: PeriodicBoard) -> None:
        """Apply this saved sticker arrangement to *board*."""
        if not isinstance(board, PeriodicBoard):
            raise TypeError("board must be a PeriodicBoard")
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

    raw_faces = data.get("faces")
    if not isinstance(raw_faces, list) or len(raw_faces) != len(FaceColor):
        raise ValueError(f"'faces' must contain exactly {len(FaceColor)} face objects.")

    board = PeriodicBoard()
    stickers: list[tuple[FaceColor, ...]] = []
    for index, (raw_face, face) in enumerate(zip(raw_faces, board.faces, strict=True)):
        if not isinstance(raw_face, dict):
            raise ValueError(f"Face {index} must be an object.")
        if raw_face.get("center_color") != face.color.name:
            raise ValueError(f"Face {index} has an unexpected center color.")
        edges = _parse_colors(raw_face.get("edge_colors"), f"face {index} edge_colors")
        corners = _parse_colors(raw_face.get("corner_colors"), f"face {index} corner_colors")
        stickers.append(edges + corners)

    return GameState(tuple(stickers), game_active, move_count)


def save_game_state(state: GameState, path: Path | str) -> None:
    """Atomically write *state* to a human-readable JSON file."""
    if not isinstance(state, GameState):
        raise TypeError("state must be a GameState")
    save_path = Path(path)
    temporary_path = save_path.with_name(f".{save_path.name}.tmp")
    data = {
        "format": GAME_STATE_FORMAT,
        "version": GAME_STATE_VERSION,
        "game_active": state.game_active,
        "move_count": state.move_count,
        "faces": [
            {
                "center_color": face.color.name,
                "edge_colors": [color.name for color in face_state[:6]],
                "corner_colors": [color.name for color in face_state[6:]],
            }
            for face, face_state in zip(PeriodicBoard().faces, state.stickers, strict=True)
        ],
    }
    temporary_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(save_path)


def _parse_colors(value: object, field_name: str) -> tuple[FaceColor, ...]:
    """Parse one six-color sticker list with a field-specific error."""
    if not isinstance(value, list) or len(value) != 6 or any(not isinstance(item, str) for item in value):
        raise ValueError(f"'{field_name}' must contain exactly six color names.")
    try:
        return tuple(FaceColor[item] for item in value)
    except KeyError as error:
        raise ValueError(f"'{field_name}' contains an unknown color: {error.args[0]!r}.") from error
