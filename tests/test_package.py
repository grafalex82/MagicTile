import math

from magic_tile import __version__
from magic_tile.ui.hex_grid import HEX_HEIGHT, hex_dimensions, hex_vertices


def test_package_has_version() -> None:
    assert __version__ == "0.1.0"


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
