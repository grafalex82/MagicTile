from magic_tile.domain import FaceColor, HexCoordinate, PeriodicBoard


def test_board_has_seven_faces_identified_by_center_color() -> None:
    board = PeriodicBoard()

    assert len(board.faces) == 7
    assert {face.center.color for face in board.faces} == set(FaceColor)


def test_each_face_contains_six_edges_and_six_corners() -> None:
    board = PeriodicBoard()

    assert len(board.edges) == 21
    assert len(board.corners) == 14

    for face in board.faces:
        assert len(face.edges) == 6
        assert len(face.corners) == 6
        assert all(face.center.color in edge.colors for edge in face.edges)
        assert all(face.center.color in corner.colors for corner in face.corners)


def test_center_and_ring_contain_each_color_once() -> None:
    board = PeriodicBoard()
    neighborhood = board.neighborhood_at(HexCoordinate(0, 0))

    colors = [neighborhood.focus.center.color]
    colors.extend(face.center.color for face in neighborhood.neighbors)

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
        assert board.face_at(coordinate).center.color is expected_color


def test_adjacent_faces_share_the_same_edge_element() -> None:
    board = PeriodicBoard()
    first = board.face_at(HexCoordinate(0, 0))
    second = board.face_at(HexCoordinate(1, 0))

    shared_edges = set(first.edges).intersection(second.edges)

    assert len(shared_edges) == 1
    assert next(iter(shared_edges)).colors == (FaceColor.WHITE, FaceColor.CYAN)


def test_three_adjacent_faces_share_the_same_corner_element() -> None:
    board = PeriodicBoard()
    faces = (
        board.face_at(HexCoordinate(0, 0)),
        board.face_at(HexCoordinate(1, 0)),
        board.face_at(HexCoordinate(1, -1)),
    )

    shared_corners = set(faces[0].corners)
    shared_corners.intersection_update(faces[1].corners, faces[2].corners)

    assert len(shared_corners) == 1
    assert next(iter(shared_corners)).colors == (
        FaceColor.WHITE,
        FaceColor.CYAN,
        FaceColor.DARK_GREEN,
    )


def test_faces_repeat_across_the_plane() -> None:
    board = PeriodicBoard()
    coordinate = HexCoordinate(4, -3)
    original = board.face_at(coordinate)

    # These two independent translations generate the seven-cell period.
    assert board.face_at(HexCoordinate(coordinate.q + 1, coordinate.r + 2)) is original
    assert board.face_at(HexCoordinate(coordinate.q + 3, coordinate.r - 1)) is original
