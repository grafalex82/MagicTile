"""Pure geometry helpers for the flat-top hexagonal grid."""

from __future__ import annotations

import math
from collections.abc import Iterator


HEX_HEIGHT = 200


def hex_dimensions(height: int = HEX_HEIGHT) -> tuple[float, float]:
    """Return the width and height of a regular flat-top hexagon."""
    radius = height / math.sqrt(3)
    return 2 * radius, float(height)


def hex_vertices(
    center: tuple[float, float], height: int = HEX_HEIGHT
) -> list[tuple[int, int]]:
    """Build integer screen vertices for a flat-top regular hexagon."""
    cx, cy = center
    radius = height / math.sqrt(3)
    return [
        (
            round(cx + radius * math.cos(math.radians(60 * index))),
            round(cy + radius * math.sin(math.radians(60 * index))),
        )
        for index in range(6)
    ]


def visible_hexes(
    viewport: tuple[int, int], height: int = HEX_HEIGHT
) -> Iterator[tuple[int, int, tuple[float, float]]]:
    """Yield axial coordinates and centres covering the whole viewport."""
    viewport_width, viewport_height = viewport
    hex_width, _ = hex_dimensions(height)
    horizontal_step = hex_width * 0.75

    # Start outside the visible area so resizing never exposes an empty strip.
    rows = math.ceil(viewport_height / height) + 3
    columns = math.ceil(viewport_width / horizontal_step) + 3

    for column in range(-2, columns):
        offset = height / 2 if column % 2 else 0
        center_x = column * horizontal_step
        for row in range(-2, rows):
            center_y = row * height + offset
            yield column, row, (center_x, center_y)
