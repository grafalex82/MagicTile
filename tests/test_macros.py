import pytest

from magic_tile.domain import HexCoordinate, PeriodicBoard, TurnDirection
from magic_tile.input import (
    MacroRecording,
    MacroSelection,
    TurnCommand,
    parse_macro,
    serialize_macro,
)


def test_macro_notation_accepts_spaces_and_hyphens_and_serializes_canonically() -> None:
    macro = parse_macro("1  2' - 1' 2")

    assert serialize_macro(macro) == "1-2'-1'-2"
    assert macro.required_face_count == 2


def test_inverse_macro_reverses_move_order_and_directions() -> None:
    macro = parse_macro("1-2'-1'-2")

    assert serialize_macro(macro.inverse) == "2'-1-2-1'"


def test_macro_expands_relative_faces_to_selected_coordinates() -> None:
    first = HexCoordinate(5, -2)
    second = HexCoordinate(-3, 4)

    commands = parse_macro("1-2'-1'").commands((first, second))

    assert commands == (
        TurnCommand(first, TurnDirection.CLOCKWISE),
        TurnCommand(second, TurnDirection.COUNTERCLOCKWISE),
        TurnCommand(first, TurnDirection.COUNTERCLOCKWISE),
    )


@pytest.mark.parametrize("selected_count", (1, 3))
def test_macro_requires_exactly_the_recorded_number_of_faces(selected_count: int) -> None:
    coordinates = tuple(HexCoordinate(index, 0) for index in range(selected_count))

    with pytest.raises(ValueError, match=f"requires 2 faces; selected {selected_count}"):
        parse_macro("1-2").commands(coordinates)


@pytest.mark.parametrize("text", ("", "1--2", "0-1", "1-3", "face 1"))
def test_invalid_macro_notation_is_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        parse_macro(text)


def test_recording_numbers_logical_faces_by_first_use_and_builds_rollback() -> None:
    board = PeriodicBoard()
    first = HexCoordinate(0, 0)
    second = HexCoordinate(1, 0)
    recording = MacroRecording(slot=4)
    commands = (
        TurnCommand(first, TurnDirection.CLOCKWISE),
        TurnCommand(second, TurnDirection.COUNTERCLOCKWISE),
        TurnCommand(HexCoordinate(7, 0), TurnDirection.COUNTERCLOCKWISE),
    )

    for command in commands:
        recording.record(board.face_at(command.coordinate), command)

    assert serialize_macro(recording.macro) == "1-2'-1'"
    assert recording.face_numbers == {board.face_at(first): 1, board.face_at(second): 2}
    assert recording.rollback_commands == tuple(command.inverse for command in reversed(commands))


def test_recording_rebuilds_face_numbers_from_active_shared_history() -> None:
    board = PeriodicBoard()
    recording = MacroRecording(slot=2)
    first = TurnCommand(HexCoordinate(0, 0), TurnDirection.CLOCKWISE)
    second = TurnCommand(HexCoordinate(1, 0), TurnDirection.COUNTERCLOCKWISE)

    recording.synchronize(board, (first, second))
    recording.synchronize(board, (second,))

    assert serialize_macro(recording.macro) == "1'"
    assert recording.face_numbers == {board.face_at(second.coordinate): 1}
    assert recording.rollback_commands == (second.inverse,)


def test_selection_deduplicates_periodic_copies_of_one_logical_face() -> None:
    board = PeriodicBoard()
    selection = MacroSelection()

    assert selection.add(board, HexCoordinate(0, 0))
    assert not selection.add(board, HexCoordinate(7, 0))
    assert selection.add(board, HexCoordinate(1, 0))
    assert selection.coordinates == (HexCoordinate(0, 0), HexCoordinate(1, 0))
    assert selection.face_numbers == {
        board.face_at(HexCoordinate(0, 0)): 1,
        board.face_at(HexCoordinate(1, 0)): 2,
    }
