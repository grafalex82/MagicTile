import json

import pytest

from magic_tile.domain import HexCoordinate, PeriodicBoard, TurnDirection
from magic_tile.persistence import GameState, load_game_state, save_game_state
from magic_tile.persistence.game_state import GAME_STATE_FORMAT, GAME_STATE_VERSION


def test_game_state_round_trip_restores_board_and_move_count(tmp_path) -> None:
    board = PeriodicBoard()
    board.turn(HexCoordinate(0, 0), TurnDirection.CLOCKWISE)
    board.turn(HexCoordinate(2, 0), TurnDirection.COUNTERCLOCKWISE)
    expected_stickers = board.sticker_state()
    path = tmp_path / "game.json"

    save_game_state(GameState.capture(board, game_active=True, move_count=17), path)
    loaded = load_game_state(path)
    restored = PeriodicBoard()
    loaded.restore_board(restored)

    assert restored.sticker_state() == expected_stickers
    assert loaded.game_active
    assert loaded.move_count == 17
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["format"] == GAME_STATE_FORMAT
    assert document["version"] == GAME_STATE_VERSION


@pytest.mark.parametrize(
    "change",
    (
        lambda data: data.update(version=99),
        lambda data: data.update(version=True),
        lambda data: data.update(move_count=-1),
        lambda data: data.update(game_active="yes"),
        lambda data: data["faces"].pop(),
        lambda data: data["faces"][0]["edge_colors"].__setitem__(0, "PURPLE"),
    ),
)
def test_invalid_game_state_files_are_rejected(tmp_path, change) -> None:
    path = tmp_path / "game.json"
    save_game_state(GameState.capture(PeriodicBoard(), game_active=False, move_count=0), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError):
        load_game_state(path)
