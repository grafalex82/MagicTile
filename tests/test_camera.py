from magic_tile.ui.camera import Camera
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
