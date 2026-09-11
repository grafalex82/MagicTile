import math

from magic_tile.ui.hex_grid import (
    HEX_HEIGHT,
    hex_at_point,
    hex_center,
    hex_dimensions,
    hex_vertices,
)


def test_hexagon_has_fixed_height() -> None:
    vertices = hex_vertices((200, 200))

    assert max(y for _, y in vertices) - min(y for _, y in vertices) == HEX_HEIGHT


def test_hexagon_is_rotated_to_flat_top_orientation() -> None:
    vertices = hex_vertices((200, 200))

    assert sum(y == 100 for _, y in vertices) == 2
    assert sum(y == 300 for _, y in vertices) == 2


def test_hexagon_width_matches_regular_geometry() -> None:
    width, height = hex_dimensions()

    assert height == HEX_HEIGHT
    assert math.isclose(width, 2 * HEX_HEIGHT / math.sqrt(3))


def test_r_axis_is_vertical() -> None:
    center = hex_center(0, 0)
    next_on_r = hex_center(0, 1)

    assert next_on_r == (center[0], center[1] + HEX_HEIGHT)


def test_q_axis_is_inclined_down_and_right() -> None:
    center = hex_center(0, 0)
    next_on_q = hex_center(1, 0)

    assert next_on_q[0] > center[0]
    assert next_on_q[1] == center[1] + HEX_HEIGHT / 2


def test_hex_at_point_finds_hexagon_centers() -> None:
    for coordinate in ((0, 0), (3, -2), (-4, 5)):
        assert hex_at_point(hex_center(*coordinate)) == coordinate


def test_hex_at_point_accounts_for_zoom_and_camera_offset() -> None:
    height = HEX_HEIGHT * 1.75
    offset = (-123.0, 87.0)
    center_x, center_y = hex_center(2, -3, height)
    screen_center = center_x + offset[0], center_y + offset[1]

    assert hex_at_point(screen_center, height=height, offset=offset) == (2, -3)
