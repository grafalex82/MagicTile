import json

import pytest

from magic_tile.domain import BoardMode, HexCoordinate, PeriodicBoard, TurnDirection
from magic_tile.input import SetupMove, TurnCommand
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


@pytest.mark.parametrize("recording", (True, False))
def test_game_state_round_trip_restores_active_setup_move(tmp_path, recording) -> None:
    commands = (
        TurnCommand(HexCoordinate(-3, 7), TurnDirection.CLOCKWISE),
        TurnCommand(HexCoordinate(4, -2), TurnDirection.COUNTERCLOCKWISE),
    )
    state = GameState.capture(
        PeriodicBoard(),
        game_active=False,
        move_count=0,
        setup_move=SetupMove(commands, recording),
    )
    path = tmp_path / "setup.json"

    save_game_state(state, path)
    loaded = load_game_state(path)

    assert loaded.setup_move == state.setup_move


def test_game_state_loads_without_an_optional_setup_move(tmp_path) -> None:
    path = tmp_path / "old.json"
    save_game_state(GameState.capture(PeriodicBoard(), game_active=False, move_count=0), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("setup_move")
    path.write_text(json.dumps(data), encoding="utf-8")

    assert load_game_state(path).setup_move is None


def test_game_state_without_mode_field_remains_a_torus_save(tmp_path) -> None:
    path = tmp_path / "old.json"
    save_game_state(GameState.capture(PeriodicBoard(), game_active=False, move_count=0), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("mode")
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = load_game_state(path)

    assert loaded.mode is BoardMode.TORUS


def test_game_state_treats_an_empty_finished_setup_move_as_inactive(tmp_path) -> None:
    path = tmp_path / "empty_setup.json"
    save_game_state(GameState.capture(PeriodicBoard(), game_active=False, move_count=0), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["setup_move"] = {"recording": False, "commands": []}
    path.write_text(json.dumps(data), encoding="utf-8")

    assert load_game_state(path).setup_move is None


@pytest.mark.parametrize(
    "setup_move",
    (
        {},
        {"recording": "yes", "commands": []},
        {"recording": True, "commands": "invalid"},
        {
            "recording": True,
            "commands": [{"q": True, "r": 0, "direction": "clockwise"}],
        },
        {
            "recording": False,
            "commands": [{"q": 0, "r": 0, "direction": "sideways"}],
        },
    ),
)
def test_invalid_saved_setup_move_is_rejected(tmp_path, setup_move) -> None:
    path = tmp_path / "invalid_setup.json"
    save_game_state(GameState.capture(PeriodicBoard(), game_active=False, move_count=0), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["setup_move"] = setup_move
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError):
        load_game_state(path)


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


def test_klein_bottle_mode_round_trips_without_a_save_version_bump(tmp_path) -> None:
    board = PeriodicBoard(BoardMode.KLEIN_BOTTLE)
    board.turn(HexCoordinate(3, 2), TurnDirection.CLOCKWISE)
    path = tmp_path / "klein.json"

    save_game_state(GameState.capture(board, game_active=True, move_count=4), path)
    loaded = load_game_state(path)
    restored = PeriodicBoard(BoardMode.KLEIN_BOTTLE)
    loaded.restore_board(restored)

    assert loaded.mode is BoardMode.KLEIN_BOTTLE
    assert restored.sticker_state() == board.sticker_state()
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["version"] == GAME_STATE_VERSION
    assert document["mode"] == BoardMode.KLEIN_BOTTLE.value
