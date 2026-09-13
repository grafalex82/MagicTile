import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QImage, QKeyEvent, QPainter
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

from magic_tile.domain import HexCoordinate, PeriodicBoard, TurnDirection
from magic_tile.input import TurnCommand, parse_macro, serialize_macro
from magic_tile.persistence import Settings
from magic_tile.ui.camera import Camera
from magic_tile.ui.game_window import (
    GameBoardWidget,
    GameWindow,
    MACRO_HIGHLIGHT_COLOR,
    TURN_GUIDE_HIGHLIGHT_COLOR,
    _digit_from_key,
    _left_drag_started,
    draw_recording_panel,
    draw_status_message,
    render_board,
)
from magic_tile.ui.qt_renderer import _cell_geometries
from magic_tile.ui.turn_animation import TurnAnimation


@pytest.fixture(scope="session", autouse=True)
def application() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def widget(application) -> GameBoardWidget:
    result = GameBoardWidget(Settings(turn_animation_duration_seconds=0.001))
    result.resize(640, 480)
    result._frame_timer.stop()
    yield result
    result.close()
    result.deleteLater()


def _image_contains(image, color: QColor) -> bool:
    target = (color.red(), color.green(), color.blue())
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            if (pixel.red(), pixel.green(), pixel.blue()) == target:
                return True
    return False


def _image_bytes(image) -> bytes:
    return bytes(image.constBits().asstring(image.sizeInBytes()))


def _finish_turns(widget: GameBoardWidget) -> None:
    for _ in range(100):
        if widget.animation is None and not widget.turn_queue:
            widget.advance(10_000_000.0)
            return
        now = (
            widget.animation.started_at + widget.animation.duration_seconds + 1.0
            if widget.animation is not None
            else 10_000_000.0
        )
        widget.advance(now)
        widget.advance(now)
    raise AssertionError("turn queue did not finish")


def test_left_drag_starts_only_after_moving_more_than_five_pixels_on_an_axis() -> None:
    button_down_at = (100, 100)

    assert not _left_drag_started(button_down_at, (105, 105))
    assert _left_drag_started(button_down_at, (106, 100))
    assert _left_drag_started(button_down_at, (100, 94))


def test_vector_geometry_builds_six_circle_cut_edges_and_corners() -> None:
    geometry = _cell_geometries(200)[0]

    assert len(geometry.edges) == 6
    assert len(geometry.corners) == 6
    assert all(len(polygon) >= 3 for polygon in geometry.edges)
    assert all(len(polygon) >= 3 for polygon in geometry.corners)


def test_number_row_and_keypad_digits_map_to_macro_slots() -> None:
    assert _digit_from_key(Qt.Key.Key_0) == 0
    assert _digit_from_key(Qt.Key.Key_7) == 7
    assert _digit_from_key(Qt.Key.Key_3) == 3
    assert _digit_from_key(Qt.Key.Key_Escape) is None


def test_board_draws_macro_markers() -> None:
    board = PeriodicBoard()
    selected_face = board.face_at(HexCoordinate(0, 0))

    image = render_board(
        (640, 480),
        board=board,
        camera=Camera(320, 240),
        macro_face_numbers={selected_face: 1},
    )

    assert _image_contains(image, MACRO_HIGHLIGHT_COLOR)


def test_recording_panel_and_status_are_drawn_as_separate_overlays() -> None:
    image = render_board((640, 480), camera=Camera(320, 240))
    board_only = _image_bytes(image)
    painter = QPainter(image)
    try:
        draw_recording_panel(painter, slot=4, move_count=3, face_count=2)
        draw_status_message(painter, (640, 480), "Macro saved", is_error=False)
    finally:
        painter.end()

    assert _image_bytes(image) != board_only
    assert _image_contains(image, QColor("#ff3b30"))


def test_hover_highlight_is_drawn_with_macro_highlight() -> None:
    board = PeriodicBoard()
    coordinate = HexCoordinate(0, 0)
    image = render_board(
        (640, 480),
        board=board,
        camera=Camera(320, 240),
        hovered_coordinate=coordinate,
        macro_face_numbers={board.face_at(coordinate): 1},
    )

    assert _image_contains(image, MACRO_HIGHLIGHT_COLOR)
    assert _image_contains(image, TURN_GUIDE_HIGHLIGHT_COLOR)


def test_mid_turn_frame_differs_from_completed_board() -> None:
    board = PeriodicBoard()
    camera = Camera(320, 240)
    animation = TurnAnimation.begin(
        board,
        HexCoordinate(0, 0),
        TurnDirection.CLOCKWISE,
        started_at=10.0,
        duration_seconds=0.5,
    )

    animated = render_board((640, 480), board=board, camera=camera, animation=animation, now=10.25)
    completed = render_board((640, 480), board=board, camera=camera)

    assert _image_bytes(animated) != _image_bytes(completed)


def test_static_face_cache_tracks_colors_read_from_mutable_face() -> None:
    board = PeriodicBoard()
    camera = Camera(320, 240)
    before = render_board((640, 480), board=board, camera=camera)

    board.turn(HexCoordinate(0, 0), TurnDirection.CLOCKWISE)
    after = render_board((640, 480), board=board, camera=camera)

    assert _image_bytes(after) != _image_bytes(before)


def test_animation_start_reuses_the_already_rendered_static_background(widget) -> None:
    initial_frame = QImage(640, 480, QImage.Format.Format_ARGB32_Premultiplied)
    widget.render(initial_frame)
    cached_background = widget._static_cache

    widget._perform_new_turn(
        TurnCommand(HexCoordinate(0, 0), TurnDirection.CLOCKWISE)
    )
    animated_frame = QImage(640, 480, QImage.Format.Format_ARGB32_Premultiplied)
    widget.render(animated_frame)

    assert widget._static_cache is cached_background


def test_escape_does_not_close_the_window(application) -> None:
    window = GameWindow(Settings())
    window.show()
    event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Escape,
        Qt.KeyboardModifier.NoModifier,
    )

    window.board_widget.keyPressEvent(event)

    assert window.isVisible()
    window.close()


def test_qt_mouse_event_turns_a_face(widget, application) -> None:
    widget.show()
    application.processEvents()
    original = widget.board.sticker_state()

    QTest.mouseClick(widget, Qt.MouseButton.RightButton, pos=QPoint(320, 240))

    assert widget.board.sticker_state() != original


def test_qt_keyboard_event_starts_macro_recording(widget, application) -> None:
    widget.show()
    widget.setFocus()
    application.processEvents()

    QTest.keyClick(widget, Qt.Key.Key_4, Qt.KeyboardModifier.ControlModifier)

    assert widget.macro_recording is not None
    assert widget.macro_recording.slot == 4


def test_escape_during_macro_playback_does_not_interrupt_queued_turns(widget) -> None:
    widget.settings = widget.settings.with_macro(0, parse_macro("1-1'"))
    widget.macro_selection.add(widget.board, HexCoordinate(0, 0))
    original = widget.board.sticker_state()
    widget._play_macro(0, reverse=False, now=1.0)

    widget._handle_escape(1.0)
    _finish_turns(widget)

    assert widget.board.sticker_state() == original
    assert not widget.playback_active


def test_escape_during_recording_animates_rollback_without_saving(widget, monkeypatch) -> None:
    saved_settings = []
    monkeypatch.setattr("magic_tile.ui.game_window.save_settings", saved_settings.append)
    original = widget.board.sticker_state()
    widget._begin_recording(4, now=1.0)
    widget._perform_new_turn(TurnCommand(HexCoordinate(0, 0), TurnDirection.CLOCKWISE))

    widget._handle_escape(now=2.0)
    _finish_turns(widget)

    assert widget.board.sticker_state() == original
    assert saved_settings == []


def test_undo_and_redo_edit_active_macro_on_shared_history(widget, monkeypatch) -> None:
    saved_settings = []
    monkeypatch.setattr("magic_tile.ui.game_window.save_settings", saved_settings.append)
    widget._begin_recording(4, now=1.0)
    command = TurnCommand(HexCoordinate(0, 0), TurnDirection.CLOCKWISE)
    widget._perform_new_turn(command)
    _finish_turns(widget)
    undo = widget.turn_history.undo(widget.recording_history.position)
    assert undo is not None
    widget._synchronize_recording()
    widget._begin_animation(undo, now=2.0)
    _finish_turns(widget)
    widget._save_recording(now=3.0)
    assert saved_settings == []
    redo = widget.turn_history.redo()
    assert redo is not None
    widget._synchronize_recording()
    widget._begin_animation(redo, now=4.0)
    _finish_turns(widget)
    widget._save_recording(now=5.0)

    assert len(saved_settings) == 1
    assert serialize_macro(saved_settings[0].macros[4]) == "1"
