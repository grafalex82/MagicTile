from magic_tile.domain import HexCoordinate, TurnDirection
from magic_tile.input import TurnCommand, TurnHistory


def test_undo_returns_inverse_turn_and_makes_it_available_for_redo() -> None:
    history = TurnHistory()
    command = TurnCommand(HexCoordinate(4, -2), TurnDirection.CLOCKWISE)

    history.record(command)

    assert history.undo() == TurnCommand(HexCoordinate(4, -2), TurnDirection.COUNTERCLOCKWISE)
    assert history.redo() == command
    assert history.undo() == TurnCommand(HexCoordinate(4, -2), TurnDirection.COUNTERCLOCKWISE)


def test_new_turn_discards_redo_history() -> None:
    history = TurnHistory()
    first = TurnCommand(HexCoordinate(0, 0), TurnDirection.CLOCKWISE)
    second = TurnCommand(HexCoordinate(2, 1), TurnDirection.COUNTERCLOCKWISE)

    history.record(first)
    history.undo()
    history.record(second)

    assert history.redo() is None
    assert history.undo() == second.inverse


def test_history_is_unbounded() -> None:
    history = TurnHistory()
    turns = 1_001

    for coordinate in range(turns):
        history.record(TurnCommand(HexCoordinate(coordinate, 0), TurnDirection.CLOCKWISE))

    for coordinate in reversed(range(turns)):
        assert history.undo() == TurnCommand(HexCoordinate(coordinate, 0), TurnDirection.COUNTERCLOCKWISE)
    assert history.undo() is None
