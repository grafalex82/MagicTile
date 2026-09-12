from collections import Counter

from magic_tile.domain import (
    FaceColor,
    HexCoordinate,
    PeriodicBoard,
    TurnDirection,
)


def test_board_has_seven_faces_identified_by_center_color() -> None:
    board = PeriodicBoard()

    assert len(board.faces) == 7
    assert {face.color for face in board.faces} == set(FaceColor)


def test_each_face_contains_six_edges_and_six_corners() -> None:
    board = PeriodicBoard()

    for face in board.faces:
        assert len(face.edge_colors) == 6
        assert len(face.corner_colors) == 6
        assert set(face.edge_colors) == {face.color}
        assert set(face.corner_colors) == {face.color}


def test_center_and_ring_contain_each_color_once() -> None:
    board = PeriodicBoard()
    neighborhood = board.neighborhood_at(HexCoordinate(0, 0))

    colors = [neighborhood.focus.color]
    colors.extend(face.color for face in neighborhood.neighbors)

    assert len(set(colors)) == 7
    assert set(colors) == set(FaceColor)


def test_colors_around_white_center_match_reference_directions() -> None:
    board = PeriodicBoard()
    expected_colors = {
        HexCoordinate(0, 0): FaceColor.WHITE,
        HexCoordinate(1, 0): FaceColor.CYAN,
        HexCoordinate(1, -1): FaceColor.DARK_GREEN,
        HexCoordinate(0, -1): FaceColor.BLUE,
        HexCoordinate(-1, 0): FaceColor.YELLOW,
        HexCoordinate(-1, 1): FaceColor.RED,
        HexCoordinate(0, 1): FaceColor.ORANGE,
    }

    for coordinate, expected_color in expected_colors.items():
        assert board.face_at(coordinate).color is expected_color


def test_faces_repeat_across_the_plane() -> None:
    board = PeriodicBoard()
    coordinate = HexCoordinate(4, -3)
    original = board.face_at(coordinate)

    # These two independent translations generate the seven-cell period.
    assert board.face_at(HexCoordinate(coordinate.q + 1, coordinate.r + 2)) is original
    assert board.face_at(HexCoordinate(coordinate.q + 3, coordinate.r - 1)) is original


def test_turn_moves_neighbor_stickers_in_requested_direction() -> None:
    board = PeriodicBoard()
    focus_color = FaceColor.WHITE
    neighbor_colors = tuple(
        face.color
        for face in board.neighborhood_at(HexCoordinate(0, 0)).neighbors
    )

    board.turn(focus_color, TurnDirection.COUNTERCLOCKWISE)

    for destination_index, destination_color in enumerate(neighbor_colors):
        source_color = neighbor_colors[(destination_index - 1) % 6]
        inward_edge = (destination_index + 3) % 6
        assert board.face_for_color(destination_color).edge_colors[inward_edge] is source_color


def test_turn_followed_by_inverse_restores_every_sticker() -> None:
    board = PeriodicBoard()
    original = board.sticker_state()

    board.turn(FaceColor.RED, TurnDirection.CLOCKWISE)
    board.turn(FaceColor.RED, TurnDirection.COUNTERCLOCKWISE)

    assert board.sticker_state() == original


def test_six_turns_restore_every_sticker() -> None:
    board = PeriodicBoard()
    original = board.sticker_state()

    for _ in range(6):
        board.turn(FaceColor.CYAN, TurnDirection.CLOCKWISE)

    assert board.sticker_state() == original


def test_turns_preserve_all_sticker_colors() -> None:
    board = PeriodicBoard()

    def color_counts() -> Counter[FaceColor]:
        return Counter(color for face_state in board.sticker_state() for color in face_state)

    original_counts = color_counts()
    moves = (
        (FaceColor.WHITE, TurnDirection.COUNTERCLOCKWISE),
        (FaceColor.BLUE, TurnDirection.CLOCKWISE),
        (FaceColor.ORANGE, TurnDirection.COUNTERCLOCKWISE),
        (FaceColor.WHITE, TurnDirection.CLOCKWISE),
    )
    for color, direction in moves:
        board.turn(color, direction)

    assert color_counts() == original_counts
