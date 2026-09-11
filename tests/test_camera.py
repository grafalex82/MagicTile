import pytest

from magic_tile.ui.camera import MAX_ZOOM, MIN_ZOOM, Camera
from magic_tile.ui.hex_grid import HEX_HEIGHT, visible_hexes


def test_camera_can_pan_into_negative_coordinates() -> None:
    camera = Camera()

    camera.pan(-350, -225)

    assert camera.offset == (-350, -225)


def test_visible_hexes_follow_camera_offset() -> None:
    offset = (-10_000.0, 8_000.0)
    visible = list(visible_hexes((1280, 800), offset=offset))

    assert visible
    assert any(
        -HEX_HEIGHT <= center_x <= 1280 + HEX_HEIGHT
        and -HEX_HEIGHT <= center_y <= 800 + HEX_HEIGHT
        for _, _, (center_x, center_y) in visible
    )


def test_wheel_up_zooms_in_and_wheel_down_zooms_out() -> None:
    camera = Camera()

    camera.zoom_by(1, (0, 0))
    zoomed_in = camera.zoom
    camera.zoom_by(-2, (0, 0))

    assert zoomed_in > 1.0
    assert camera.zoom < 1.0


def test_zoom_is_limited_to_50_and_250_percent() -> None:
    camera = Camera()

    camera.zoom_by(100, (0, 0))
    assert camera.zoom == MAX_ZOOM

    camera.zoom_by(-200, (0, 0))
    assert camera.zoom == MIN_ZOOM


def test_zoom_keeps_point_under_cursor_stationary() -> None:
    camera = Camera(x=20, y=-30)
    focus = (400, 300)
    world_point = (
        (focus[0] - camera.x) / camera.zoom,
        (focus[1] - camera.y) / camera.zoom,
    )

    camera.zoom_by(3, focus)

    assert world_point[0] * camera.zoom + camera.x == pytest.approx(focus[0])
    assert world_point[1] * camera.zoom + camera.y == pytest.approx(focus[1])
