import pytest

from magic_tile.domain import FaceColor, HexCoordinate, PeriodicBoard, TurnDirection
from magic_tile.ui.turn_animation import TurnAnimation


def test_animation_updates_model_at_start_and_finishes_after_half_second() -> None:
    board = PeriodicBoard()
    original = board.sticker_state()
    duration_seconds = 0.5

    animation = TurnAnimation.begin(
        board,
        HexCoordinate(0, 0),
        TurnDirection.COUNTERCLOCKWISE,
        started_at=10.0,
        duration_seconds=duration_seconds,
    )

    assert board.sticker_state() != original
    assert not animation.is_finished(10.0 + duration_seconds - 0.001)
    assert animation.is_finished(10.0 + duration_seconds)


def test_animation_resolves_coordinate_and_keys_source_slots_by_face() -> None:
    board = PeriodicBoard()

    animation = TurnAnimation.begin(
        board,
        HexCoordinate(7, 0),
        TurnDirection.CLOCKWISE,
        started_at=0.0,
        duration_seconds=0.5,
    )

    assert animation.face is board.face_at(HexCoordinate(0, 0))
    assert animation.turning_faces == (animation.face,)
    assert all(face in board.faces for face, _, _ in animation.source_colors)


def test_visual_turn_does_not_change_face_colors() -> None:
    board = PeriodicBoard()
    original_colors = tuple(face.color for face in board.faces)
    duration_seconds = 0.5

    TurnAnimation.begin(
        board,
        HexCoordinate(4, 0),
        TurnDirection.CLOCKWISE,
        started_at=4.0,
        duration_seconds=duration_seconds,
    )

    assert tuple(face.color for face in board.faces) == original_colors


def test_animation_uses_configured_duration() -> None:
    board = PeriodicBoard()
    animation = TurnAnimation.begin(
        board,
        HexCoordinate(2, 0),
        TurnDirection.CLOCKWISE,
        started_at=1.0,
        duration_seconds=1.25,
    )

    assert not animation.is_finished(2.249)
    assert animation.is_finished(2.25)


@pytest.mark.parametrize(
    ("direction", "expected_angle"),
    (
        (TurnDirection.COUNTERCLOCKWISE, -60.0),
        (TurnDirection.CLOCKWISE, 60.0),
    ),
)
def test_animation_reaches_sixty_degrees_in_screen_coordinates(
    direction: TurnDirection, expected_angle: float
) -> None:
    board = PeriodicBoard()
    duration_seconds = 0.5
    animation = TurnAnimation.begin(
        board,
        HexCoordinate(6, 0),
        direction,
        started_at=2.0,
        duration_seconds=duration_seconds,
    )

    assert animation.angle_degrees(2.0 + duration_seconds) == pytest.approx(expected_angle)
