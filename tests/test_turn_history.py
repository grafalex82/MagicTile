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


def test_snapshot_restores_undo_and_redo_branches_after_provisional_turns() -> None:
    history = TurnHistory()
    first = TurnCommand(HexCoordinate(0, 0), TurnDirection.CLOCKWISE)
    second = TurnCommand(HexCoordinate(1, 0), TurnDirection.COUNTERCLOCKWISE)
    provisional = TurnCommand(HexCoordinate(2, 0), TurnDirection.CLOCKWISE)
    history.record(first)
    history.record(second)
    history.undo()
    snapshot = history.snapshot()

    history.record(provisional)
    history.restore(snapshot)

    assert history.redo() == second
    assert history.undo() == second.inverse
    assert history.undo() == first.inverse


def test_recording_boundary_and_active_segment_share_the_main_history() -> None:
    history = TurnHistory()
    before_recording = TurnCommand(HexCoordinate(0, 0), TurnDirection.CLOCKWISE)
    recorded = TurnCommand(HexCoordinate(1, 0), TurnDirection.COUNTERCLOCKWISE)
    history.record(before_recording)
    recording_start = history.snapshot().position
    history.record(recorded)

    assert history.commands_since(recording_start) == (recorded,)
    assert history.undo(recording_start) == recorded.inverse
    assert history.commands_since(recording_start) == ()
    assert history.undo(recording_start) is None
    assert history.redo() == recorded
    assert history.commands_since(recording_start) == (recorded,)
