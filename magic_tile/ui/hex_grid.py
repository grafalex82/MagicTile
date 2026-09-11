"""Pure geometry helpers for the flat-top hexagonal grid."""

from __future__ import annotations

import math
from collections.abc import Iterator


HEX_HEIGHT = 200


def hex_dimensions(height: float = HEX_HEIGHT) -> tuple[float, float]:
    """Return the width and height of a regular flat-top hexagon."""
    radius = height / math.sqrt(3)
    return 2 * radius, float(height)


def hex_vertices(
    center: tuple[float, float], height: float = HEX_HEIGHT
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


def hex_center(
    q: int, r: int, height: float = HEX_HEIGHT
) -> tuple[float, float]:
    """Convert axial coordinates to a center point in screen pixels.

    Increasing ``r`` moves vertically down. Increasing ``q`` moves down and
    right, so the q axis is inclined by 30 degrees to the screen horizontal.
    """
    width, _ = hex_dimensions(height)
    return q * width * 0.75, (r + q / 2) * height


def visible_hexes(
    viewport: tuple[int, int],
    height: float = HEX_HEIGHT,
    offset: tuple[float, float] = (0.0, 0.0),
) -> Iterator[tuple[int, int, tuple[float, float]]]:
    """Yield axial coordinates and screen centres covering the viewport.

    ``offset`` is the camera translation in screen pixels. It is deliberately
    unrestricted, so the infinite board can be explored in every direction.
    """
    viewport_width, viewport_height = viewport
    hex_width, _ = hex_dimensions(height)
    horizontal_step = hex_width * 0.75
    offset_x, offset_y = offset
    radius = hex_width / 2

    # Convert the viewport bounds to board space and include one extra ring.
    min_q = math.floor((-offset_x - radius) / horizontal_step) - 1
    max_q = math.ceil((viewport_width - offset_x + radius) / horizontal_step) + 1

    for q in range(min_q, max_q + 1):
        min_r = math.floor((-offset_y - height / 2) / height - q / 2) - 1
        max_r = math.ceil(
            (viewport_height - offset_y + height / 2) / height - q / 2
        ) + 1
        for r in range(min_r, max_r + 1):
            world_x, world_y = hex_center(q, r, height)
            yield q, r, (world_x + offset_x, world_y + offset_y)
