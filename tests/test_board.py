from collections import Counter

from magic_tile.domain import (
    FaceColor,
    HexCoordinate,
    PeriodicBoard,
    TurnDirection,
)


def test_coordinates_resolve_to_seven_coordinate_free_face_objects() -> None:
    board = PeriodicBoard()

    assert len(board.faces) == 7
    assert all(not hasattr(face, "coordinate") for face in board.faces)
    assert board.face_at(HexCoordinate(0, 0)) is board.face_at(HexCoordinate(7, 0))
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
    focus = board.face_at(HexCoordinate(0, 0))

    colors = [focus.color]
    colors.extend(face.color for face in focus.neighbors)

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


def test_faces_hold_their_six_neighbor_references() -> None:
    board = PeriodicBoard()

    for index, face in enumerate(board.faces):
        representative = HexCoordinate(index, 0)
        expected = tuple(
            board.face_at(representative.translated(dq, dr)) for dq, dr in board.NEIGHBOUR_DIRECTIONS
        )
        assert face.neighbors == expected


def test_each_direction_wraps_around_the_seven_face_torus() -> None:
    board = PeriodicBoard()

    for direction_index in range(6):
        start = board.face_at(HexCoordinate(0, 0))
        current = start
        visited = set()
        for _ in range(7):
            visited.add(current)
            current = current.neighbors[direction_index]

        assert current is start
        assert len(visited) == 7


def test_affected_slots_are_addressed_by_face_references() -> None:
    board = PeriodicBoard()
    focus = board.face_at(HexCoordinate(0, 0))

    slots = board.affected_slots(HexCoordinate(0, 0))

    assert len(slots) == 30
    assert all(face in board.faces for face, _, _ in slots)
    assert (focus, "edge", 0) in slots
    assert (focus.neighbors[0], "edge", 3) in slots


def test_turn_uses_face_neighbor_references_after_center_colors_are_swapped() -> None:
    board = PeriodicBoard()
    focus = board.face_at(HexCoordinate(0, 0))
    other = board.face_at(HexCoordinate(2, 0))
    focus.color, other.color = other.color, focus.color
    source_edges = tuple(
        neighbor.edge_colors[(index + 3) % 6] for index, neighbor in enumerate(focus.neighbors)
    )

    board.turn(HexCoordinate(0, 0), TurnDirection.COUNTERCLOCKWISE)

    for destination_index, destination_face in enumerate(focus.neighbors):
        inward_edge = (destination_index + 3) % 6
        assert destination_face.edge_colors[inward_edge] is source_edges[(destination_index - 1) % 6]


def test_turn_moves_neighbor_stickers_in_requested_direction() -> None:
    board = PeriodicBoard()
    focus_coordinate = HexCoordinate(0, 0)
    neighbors = board.face_at(focus_coordinate).neighbors

    board.turn(focus_coordinate, TurnDirection.COUNTERCLOCKWISE)

    for destination_index, destination_face in enumerate(neighbors):
        source_color = neighbors[(destination_index - 1) % 6].color
        inward_edge = (destination_index + 3) % 6
        assert destination_face.edge_colors[inward_edge] is source_color


def test_turn_followed_by_inverse_restores_every_sticker() -> None:
    board = PeriodicBoard()
    original = board.sticker_state()

    coordinate = HexCoordinate(2, 0)
    board.turn(coordinate, TurnDirection.CLOCKWISE)
    board.turn(coordinate, TurnDirection.COUNTERCLOCKWISE)

    assert board.sticker_state() == original


def test_six_turns_restore_every_sticker() -> None:
    board = PeriodicBoard()
    original = board.sticker_state()

    for _ in range(6):
        board.turn(HexCoordinate(1, 0), TurnDirection.CLOCKWISE)

    assert board.sticker_state() == original


def test_turns_preserve_all_sticker_colors() -> None:
    board = PeriodicBoard()

    def color_counts() -> Counter[FaceColor]:
        return Counter(color for face_state in board.sticker_state() for color in face_state)

    original_counts = color_counts()
    moves = (
        (HexCoordinate(0, 0), TurnDirection.COUNTERCLOCKWISE),
        (HexCoordinate(4, 0), TurnDirection.CLOCKWISE),
        (HexCoordinate(3, 0), TurnDirection.COUNTERCLOCKWISE),
        (HexCoordinate(0, 0), TurnDirection.CLOCKWISE),
    )
    for coordinate, direction in moves:
        board.turn(coordinate, direction)

    assert color_counts() == original_counts
