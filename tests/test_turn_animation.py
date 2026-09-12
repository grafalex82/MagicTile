import pytest

from magic_tile.domain import FaceColor, PeriodicBoard, TurnDirection
from magic_tile.ui.turn_animation import TURN_DURATION_SECONDS, TurnAnimation


def test_animation_updates_model_at_start_and_finishes_after_half_second() -> None:
    board = PeriodicBoard()
    original = board.sticker_state()

    animation = TurnAnimation.begin(
        board, FaceColor.WHITE, TurnDirection.COUNTERCLOCKWISE, started_at=10.0
    )

    assert board.sticker_state() != original
    assert not animation.is_finished(10.0 + TURN_DURATION_SECONDS - 0.001)
    assert animation.is_finished(10.0 + TURN_DURATION_SECONDS)


def test_visual_turn_does_not_change_face_colors() -> None:
    board = PeriodicBoard()
    original_colors = tuple(face.color for face in board.faces)

    TurnAnimation.begin(
        board, FaceColor.BLUE, TurnDirection.CLOCKWISE, started_at=4.0
    )

    assert tuple(face.color for face in board.faces) == original_colors


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
    animation = TurnAnimation.begin(board, FaceColor.YELLOW, direction, started_at=2.0)

    assert animation.angle_degrees(2.0 + TURN_DURATION_SECONDS) == pytest.approx(
        expected_angle
    )
