import pygame

from magic_tile.domain import HexCoordinate, PeriodicBoard, TurnDirection
from magic_tile.ui.game_window import (
    _left_drag_started,
    _circular_alpha_mask,
    _curved_face_geometry,
    _render_turn_frame,
    _scale_turn_frame,
)
from magic_tile.ui.turn_animation import TurnAnimation


def test_circular_mask_has_opaque_center_and_transparent_corners() -> None:
    mask = _circular_alpha_mask(radius=30)

    assert mask.get_at((33, 33)).a == 255
    assert mask.get_at((0, 0)).a == 0
    assert mask.get_at((66, 66)).a == 0


def test_left_drag_starts_only_after_moving_more_than_five_pixels_on_an_axis() -> None:
    button_down_at = (100, 100)

    assert not _left_drag_started(button_down_at, (105, 105))
    assert _left_drag_started(button_down_at, (106, 100))
    assert _left_drag_started(button_down_at, (100, 94))


def test_curved_geometry_builds_six_circle_cut_edges_and_corners() -> None:
    geometry = _curved_face_geometry(height=200, piece_width=3, grid_width=10)

    assert len(geometry.edge_masks) == 6
    assert len(geometry.corner_masks) == 6
    assert all(mask.count() > 0 for mask in geometry.edge_masks)
    assert all(mask.count() > 0 for mask in geometry.corner_masks)


def test_procedural_turn_frame_has_no_pixels_outside_its_mask() -> None:
    board = PeriodicBoard()
    animation = TurnAnimation.begin(
        board,
        HexCoordinate(0, 0),
        TurnDirection.CLOCKWISE,
        started_at=0.0,
        duration_seconds=0.5,
    )

    frame = _render_turn_frame(
        animation,
        board.face_at(HexCoordinate(0, 0)),
        angle_degrees=23.0,
        zoom=1.0,
    )

    assert frame.get_at((0, 0)).a == 0
    assert frame.get_at((frame.get_width() - 1, 0)).a == 0
    assert frame.get_at((0, frame.get_height() - 1)).a == 0


def test_turn_frame_scaling_uses_circle_radius_not_surface_padding() -> None:
    source_radius = 30
    source = _circular_alpha_mask(source_radius).copy()

    scaled = _scale_turn_frame(source, source_radius, target_radius=15)

    center = scaled.get_width() // 2
    assert scaled.get_at((center + 15, center)).a > 0
    assert scaled.get_at((center + 16, center)).a == 0
