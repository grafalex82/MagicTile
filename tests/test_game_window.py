import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QAction, QColor, QImage, QKeyEvent, QKeySequence, QPainter
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest

from magic_tile.domain import BoardMode, HexCoordinate, PeriodicBoard, TurnDirection
from magic_tile.input import SetupMove, TurnCommand, parse_macro, serialize_macro
from magic_tile.persistence import GameState, Settings
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
from magic_tile.ui.qt_renderer import _cell_geometries, _color
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


def test_edge_and_corner_dimming_change_rendered_colors_independently() -> None:
    board = PeriodicBoard()
    camera = Camera(320, 240)
    normal = render_board((640, 480), board=board, camera=camera)
    dim_edges = render_board((640, 480), board=board, camera=camera, dim_edges=True)
    dim_corners = render_board((640, 480), board=board, camera=camera, dim_corners=True)

    assert _image_bytes(dim_edges) != _image_bytes(normal)
    assert _image_bytes(dim_corners) != _image_bytes(normal)
    assert _image_bytes(dim_edges) != _image_bytes(dim_corners)
    assert _color(board.faces[0].color, dimmed=True).lightness() < _color(
        board.faces[0].color
    ).lightness()


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


def test_main_menu_has_requested_structure_and_game_file_commands(application) -> None:
    window = GameWindow(Settings())
    window.board_widget._frame_timer.stop()

    assert [action.text() for action in window.menuBar().actions()] == [
        "File",
        "Puzzle",
        "View",
        "Macro",
    ]
    assert [action.text() for action in window.file_menu.actions()] == [
        "Open",
        "Save",
        "Save As",
        "",
        "Quit",
    ]
    assert [action.text() for action in window.puzzle_menu.actions()] == [
        "Mode",
        "Reset",
        "Scrumble",
        "",
        "Undo",
        "Redo",
    ]
    assert [action.text() for action in window.scrumble_menu.actions()] == [
        "3 moves",
        "5 moves",
        "10 moves",
        "50 moves",
    ]
    assert [action.text() for action in window.mode_menu.actions()] == [
        "Torus mode",
        "Klein bottle mode",
    ]
    assert window.mode_actions[BoardMode.TORUS].isChecked()
    assert [action.text() for action in window.view_menu.actions()] == [
        "Dim Edges",
        "Dim Corners",
    ]
    assert window.dim_edges_action.isCheckable()
    assert window.dim_corners_action.isCheckable()
    assert not window.dim_edges_action.isChecked()
    assert not window.dim_corners_action.isChecked()
    assert [action.text() for action in window.macro_menu.actions()] == [
        "Record",
        "Play",
        "",
        "Start Setup Move",
        "End Setup Move",
        "Unwind Setup Move",
    ]
    assert [action.text() for action in window.record_menu.actions()] == [
        *(f"Macro {slot}" for slot in "1234567890"),
    ]
    assert [action.text() for action in window.play_menu.actions()] == [
        *(f"Macro {slot}" for slot in "1234567890"),
        "",
        *(f"Macro {slot} (Reverse)" for slot in "1234567890"),
    ]
    assert window.quit_action.menuRole() is QAction.MenuRole.QuitRole
    assert window.open_action.isEnabled()
    assert window.save_action.isEnabled()
    assert window.save_as_action.isEnabled()
    assert window.reset_action.isEnabled()
    assert window.scrumble_action.isEnabled()
    assert window.start_setup_move_action.isEnabled()
    assert window.start_setup_move_action.shortcut() == QKeySequence("F1")
    assert window.end_setup_move_action.shortcut() == QKeySequence("F2")
    assert window.unwind_setup_move_action.shortcut() == QKeySequence("F3")
    assert window.statusBar().currentMessage() == (
        "Mode: Torus   |   Edges: 21/21   |   Corners: 14/14"
    )

    window.close()


def test_view_actions_toggle_piece_dimming_and_refresh_static_cache(application) -> None:
    window = GameWindow(Settings())
    widget = window.board_widget
    widget._frame_timer.stop()
    initial = QImage(640, 480, QImage.Format.Format_ARGB32_Premultiplied)
    widget.resize(640, 480)
    widget.render(initial)
    assert widget._static_cache is not None

    window.dim_edges_action.trigger()
    assert window.dim_edges_action.isChecked()
    assert widget.dim_edges
    assert widget._static_cache is None

    window.dim_corners_action.trigger()
    assert window.dim_corners_action.isChecked()
    assert widget.dim_corners
    window.dim_edges_action.trigger()
    assert not widget.dim_edges
    assert widget.dim_corners
    window.close()


def test_switching_mode_resets_free_play_without_confirmation(application, monkeypatch) -> None:
    window = GameWindow(Settings())
    window.board_widget._frame_timer.stop()
    window.board_widget._perform_new_turn(
        TurnCommand(HexCoordinate(0, 0), TurnDirection.CLOCKWISE)
    )
    asked = []
    monkeypatch.setattr(
        "magic_tile.ui.game_window.QMessageBox.question",
        lambda *args: asked.append(args),
    )

    window.mode_actions[BoardMode.KLEIN_BOTTLE].trigger()

    assert asked == []
    assert window.board_widget.board.mode is BoardMode.KLEIN_BOTTLE
    assert window.board_widget.board.is_solved()
    assert window.mode_actions[BoardMode.KLEIN_BOTTLE].isChecked()
    window.close()


def test_switching_mode_during_scored_game_requires_confirmation(application, monkeypatch) -> None:
    window = GameWindow(Settings())
    window.board_widget._frame_timer.stop()
    window.board_widget.scrumble()
    monkeypatch.setattr(
        "magic_tile.ui.game_window.QMessageBox.question",
        lambda *args: QMessageBox.StandardButton.No,
    )

    window.mode_actions[BoardMode.KLEIN_BOTTLE].trigger()

    assert window.board_widget.board.mode is BoardMode.TORUS
    assert window.board_widget.game_active
    assert window.mode_actions[BoardMode.TORUS].isChecked()

    monkeypatch.setattr(
        "magic_tile.ui.game_window.QMessageBox.question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )
    window.mode_actions[BoardMode.KLEIN_BOTTLE].trigger()

    assert window.board_widget.board.mode is BoardMode.KLEIN_BOTTLE
    assert not window.board_widget.game_active
    assert window.board_widget.move_count == 0
    window.close()


def test_save_and_open_actions_round_trip_current_game(application, monkeypatch, tmp_path) -> None:
    window = GameWindow(Settings(turn_animation_duration_seconds=0.001))
    window.board_widget._frame_timer.stop()
    window.board_widget.scrumble()
    window.board_widget._perform_new_turn(
        TurnCommand(HexCoordinate(0, 0), TurnDirection.CLOCKWISE),
    )
    _finish_turns(window.board_widget)
    expected_stickers = window.board_widget.board.sticker_state()
    path = tmp_path / "saved_game.json"
    monkeypatch.setattr(
        "magic_tile.ui.game_window.QFileDialog.getSaveFileName",
        lambda *args: (str(path), ""),
    )

    window.save_action.trigger()
    assert window.board_widget.status_message == "Game saved to saved_game.json"
    window.board_widget.reset()
    monkeypatch.setattr(
        "magic_tile.ui.game_window.QFileDialog.getOpenFileName",
        lambda *args: (str(path), ""),
    )
    window.open_action.trigger()

    assert window.board_widget.board.sticker_state() == expected_stickers
    assert window.board_widget.game_active
    assert window.board_widget.move_count == 1
    assert window.current_save_path == path
    window.close()


def test_scrumble_menu_actions_apply_their_move_counts(application, monkeypatch) -> None:
    window = GameWindow(Settings())
    window.board_widget._frame_timer.stop()
    turns = []
    monkeypatch.setattr(
        window.board_widget.board,
        "turn",
        lambda coordinate, direction: turns.append((coordinate, direction)),
    )

    for expected_count, action in zip((3, 5, 10, 50), window.scrumble_actions, strict=True):
        turns.clear()
        action.trigger()

        assert len(turns) == expected_count
        assert window.board_widget.game_active
        assert window.board_widget.move_count == 0
        assert "Moves: 0" in window.statusBar().currentMessage()

    window.close()


def test_status_bar_tracks_mode_moves_and_solved_pieces(application, monkeypatch) -> None:
    window = GameWindow(Settings(turn_animation_duration_seconds=0.001))
    window.board_widget._frame_timer.stop()
    coordinate = HexCoordinate(0, 0)
    monkeypatch.setattr(
        "magic_tile.ui.game_window.random.choice",
        lambda values: coordinate if values is window.board_widget.board.representative_coordinates else values[0],
    )

    window.board_widget.scrumble(1)
    scrambled_status = window.statusBar().currentMessage()
    assert scrambled_status.startswith("Mode: Torus   |   Moves: 0")
    assert "Edges: " in scrambled_status
    assert "Corners: " in scrambled_status

    window.board_widget._perform_new_turn(
        TurnCommand(coordinate, TurnDirection.COUNTERCLOCKWISE)
    )
    assert "Moves: 1" not in window.statusBar().currentMessage()
    assert "Edges: 21/21" in window.statusBar().currentMessage()
    assert "Corners: 14/14" in window.statusBar().currentMessage()

    window.mode_actions[BoardMode.KLEIN_BOTTLE].trigger()
    assert window.statusBar().currentMessage() == (
        "Mode: Klein bottle   |   Edges: 27/27   |   Corners: 18/18"
    )
    window.close()


def test_main_menu_actions_use_existing_board_commands(application) -> None:
    window = GameWindow(Settings(turn_animation_duration_seconds=0.001))
    window.board_widget._frame_timer.stop()
    original = window.board_widget.board.sticker_state()
    command = TurnCommand(HexCoordinate(0, 0), TurnDirection.CLOCKWISE)
    window.board_widget._perform_new_turn(command)
    _finish_turns(window.board_widget)

    window.undo_action.trigger()

    assert window.board_widget.board.sticker_state() == original
    _finish_turns(window.board_widget)

    window.redo_action.trigger()

    assert window.board_widget.board.sticker_state() != original
    _finish_turns(window.board_widget)

    window.record_actions[4].trigger()

    assert window.board_widget.macro_recording is not None
    assert window.board_widget.macro_recording.slot == 4
    window.close()


def test_free_turns_do_not_start_a_game_or_count_moves(widget) -> None:
    widget._perform_new_turn(TurnCommand(HexCoordinate(0, 0), TurnDirection.CLOCKWISE))

    assert not widget.game_active
    assert widget.move_count == 0
    assert widget.status_message is None


def test_reset_restores_board_stops_game_and_clears_history(widget) -> None:
    widget.scrumble()
    widget._perform_new_turn(TurnCommand(HexCoordinate(0, 0), TurnDirection.CLOCKWISE))

    widget.reset()

    assert widget.board.is_solved()
    assert not widget.game_active
    assert widget.move_count == 0
    assert widget.turn_history.undo() is None
    assert widget.turn_history.redo() is None


def test_scrumble_applies_three_immediate_turns_and_starts_game(widget, monkeypatch) -> None:
    coordinate = HexCoordinate(0, 0)
    choices = iter((coordinate, TurnDirection.CLOCKWISE) * 3)
    monkeypatch.setattr("magic_tile.ui.game_window.random.choice", lambda values: next(choices))
    widget._perform_new_turn(TurnCommand(HexCoordinate(1, 0), TurnDirection.CLOCKWISE))

    widget.scrumble()

    expected = PeriodicBoard()
    for _ in range(3):
        expected.turn(coordinate, TurnDirection.CLOCKWISE)
    assert widget.board.sticker_state() == expected.sticker_state()
    assert widget.animation is None
    assert widget.game_active
    assert widget.move_count == 0
    assert widget.turn_history.undo() is None
    assert widget.turn_history.redo() is None


def test_solving_active_game_shows_move_count(widget, monkeypatch) -> None:
    coordinate = HexCoordinate(0, 0)
    choices = iter((coordinate, TurnDirection.CLOCKWISE) * 3)
    monkeypatch.setattr("magic_tile.ui.game_window.random.choice", lambda values: next(choices))
    widget.scrumble()

    for _ in range(3):
        widget._perform_new_turn(TurnCommand(coordinate, TurnDirection.CLOCKWISE))
        if widget.game_active:
            _finish_turns(widget)

    assert widget.board.is_solved()
    assert not widget.game_active
    assert widget.move_count == 3
    assert widget.status_message == "Congratulations! Puzzle solved in 3 moves."
    assert not widget.status_is_error


def test_undo_and_redo_adjust_the_active_game_move_count(widget, monkeypatch) -> None:
    coordinate = HexCoordinate(0, 0)
    choices = iter((coordinate, TurnDirection.CLOCKWISE) * 3)
    monkeypatch.setattr("magic_tile.ui.game_window.random.choice", lambda values: next(choices))
    command = TurnCommand(coordinate, TurnDirection.CLOCKWISE)
    widget.scrumble()
    widget._perform_new_turn(command)
    _finish_turns(widget)
    assert widget.move_count == 1

    widget.undo(now=2.0)
    assert widget.move_count == 0
    _finish_turns(widget)

    widget.redo(now=3.0)
    assert widget.move_count == 1


def test_unwinding_setup_move_counts_each_animated_turn_in_an_active_game(widget, monkeypatch) -> None:
    scramble_coordinate = HexCoordinate(0, 0)
    choices = iter((scramble_coordinate, TurnDirection.CLOCKWISE) * 3)
    monkeypatch.setattr("magic_tile.ui.game_window.random.choice", lambda values: next(choices))
    first = TurnCommand(HexCoordinate(0, 0), TurnDirection.CLOCKWISE)
    second = TurnCommand(HexCoordinate(1, 0), TurnDirection.COUNTERCLOCKWISE)
    widget.scrumble()
    widget.start_setup_move(now=1.0)
    for command in (first, second):
        widget._perform_new_turn(command)
        _finish_turns(widget)
    widget.end_setup_move(now=2.0)
    assert widget.move_count == 2

    widget.unwind_setup_move(now=3.0)
    _finish_turns(widget)

    assert widget.move_count == 4


def test_reverse_macro_menu_action_uses_inverse_turns(application) -> None:
    settings = Settings(turn_animation_duration_seconds=0.001).with_macro(0, parse_macro("1"))
    window = GameWindow(settings)
    window.board_widget._frame_timer.stop()
    coordinate = HexCoordinate(0, 0)
    window.board_widget.macro_selection.add(window.board_widget.board, coordinate)
    expected = PeriodicBoard()
    expected.turn(coordinate, TurnDirection.COUNTERCLOCKWISE)

    window.reverse_play_actions[0].trigger()

    assert window.board_widget.board.sticker_state() == expected.sticker_state()
    assert window.reverse_play_actions[0].shortcut() == QKeySequence("Shift+0")
    window.close()


def test_shift_digit_shortcut_triggers_reverse_macro_action(application) -> None:
    settings = Settings(turn_animation_duration_seconds=0.001).with_macro(3, parse_macro("1"))
    window = GameWindow(settings)
    window.board_widget._frame_timer.stop()
    window.show()
    window.board_widget.setFocus()
    application.processEvents()
    coordinate = HexCoordinate(0, 0)
    window.board_widget.macro_selection.add(window.board_widget.board, coordinate)
    expected = PeriodicBoard()
    expected.turn(coordinate, TurnDirection.COUNTERCLOCKWISE)

    QTest.keyClick(window.board_widget, Qt.Key.Key_3, Qt.KeyboardModifier.ShiftModifier)

    assert window.board_widget.board.sticker_state() == expected.sticker_state()
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


def test_setup_move_records_only_between_start_and_end_then_unwinds_once(widget) -> None:
    first = TurnCommand(HexCoordinate(0, 0), TurnDirection.CLOCKWISE)
    second = TurnCommand(HexCoordinate(1, 0), TurnDirection.COUNTERCLOCKWISE)
    formula = TurnCommand(HexCoordinate(2, 0), TurnDirection.CLOCKWISE)
    expected = PeriodicBoard()
    for command in (first, second, formula, second.inverse, first.inverse):
        expected.turn(command.coordinate, command.direction)

    widget.start_setup_move(now=1.0)
    for command in (first, second):
        widget._perform_new_turn(command)
        _finish_turns(widget)
    widget.end_setup_move(now=2.0)
    widget._perform_new_turn(formula)
    _finish_turns(widget)
    widget.unwind_setup_move(now=3.0)
    _finish_turns(widget)

    assert widget.board.sticker_state() == expected.sticker_state()
    assert widget.setup_move is None
    state_after_first_unwind = widget.board.sticker_state()
    widget.unwind_setup_move(now=4.0)
    assert widget.board.sticker_state() == state_after_first_unwind


def test_setup_move_can_be_unwound_while_still_recording(widget) -> None:
    original = widget.board.sticker_state()
    widget.start_setup_move(now=1.0)
    widget._perform_new_turn(TurnCommand(HexCoordinate(0, 0), TurnDirection.CLOCKWISE))
    _finish_turns(widget)

    widget.unwind_setup_move(now=2.0)
    _finish_turns(widget)

    assert widget.board.sticker_state() == original
    assert widget.setup_move is None


def test_macro_playback_is_recorded_in_live_setup_move_and_unwound(widget) -> None:
    first = HexCoordinate(0, 0)
    second = HexCoordinate(1, 0)
    widget.settings = widget.settings.with_macro(4, parse_macro("1-2'"))
    widget.start_setup_move(now=1.0)
    widget.macro_selection.add(widget.board, first)
    widget.macro_selection.add(widget.board, second)
    original = widget.board.sticker_state()

    widget.play_macro(4, now=2.0)
    _finish_turns(widget)

    expected_commands = (
        TurnCommand(first, TurnDirection.CLOCKWISE),
        TurnCommand(second, TurnDirection.COUNTERCLOCKWISE),
    )
    assert widget.setup_move is not None
    assert widget.setup_move.recording
    assert widget.setup_move.commands == expected_commands

    widget.unwind_setup_move(now=3.0)
    _finish_turns(widget)

    assert widget.board.sticker_state() == original
    assert widget.setup_move is None


def test_pressing_f1_again_restarts_setup_recording_from_current_position(widget) -> None:
    first = TurnCommand(HexCoordinate(0, 0), TurnDirection.CLOCKWISE)
    second = TurnCommand(HexCoordinate(1, 0), TurnDirection.COUNTERCLOCKWISE)
    widget.start_setup_move(now=1.0)
    widget._perform_new_turn(first)
    _finish_turns(widget)

    widget.start_setup_move(now=2.0)
    assert widget.setup_move is not None
    assert widget.setup_move.commands == ()
    widget._perform_new_turn(second)
    _finish_turns(widget)
    assert widget.setup_move.commands == (second,)

    expected = PeriodicBoard()
    expected.turn(first.coordinate, first.direction)
    widget.unwind_setup_move(now=3.0)
    _finish_turns(widget)
    assert widget.board.sticker_state() == expected.sticker_state()


def test_escape_cancels_setup_recording_without_reverting_board(widget) -> None:
    command = TurnCommand(HexCoordinate(0, 0), TurnDirection.CLOCKWISE)
    widget.start_setup_move(now=1.0)
    widget._perform_new_turn(command)
    _finish_turns(widget)
    state_before_escape = widget.board.sticker_state()

    widget._handle_escape(now=2.0)

    assert widget.setup_move is None
    assert widget.board.sticker_state() == state_before_escape
    assert widget.status_message == "Setup Move recording canceled"


def test_setup_move_shortcut_actions_control_recording(application) -> None:
    window = GameWindow(Settings(turn_animation_duration_seconds=0.001))
    window.board_widget._frame_timer.stop()

    window.start_setup_move_action.trigger()
    assert window.board_widget.setup_move is not None
    assert window.board_widget.setup_move.recording

    window.end_setup_move_action.trigger()
    assert window.board_widget.setup_move is None

    window.unwind_setup_move_action.trigger()
    assert window.board_widget.setup_move is None
    window.close()


def test_qt_function_keys_control_setup_move_through_window_actions(application) -> None:
    window = GameWindow(Settings(turn_animation_duration_seconds=0.001))
    window.board_widget._frame_timer.stop()
    window.show()
    window.board_widget.setFocus()
    application.processEvents()

    QTest.keyClick(window.board_widget, Qt.Key.Key_F1)
    assert window.board_widget.setup_move is not None
    assert window.board_widget.setup_move.recording
    QTest.keyClick(window.board_widget, Qt.Key.Key_F2)
    assert window.board_widget.setup_move is None
    QTest.keyClick(window.board_widget, Qt.Key.Key_F3)
    assert window.board_widget.setup_move is None
    window.close()


def test_empty_finished_setup_move_does_not_block_a_new_recording(widget) -> None:
    widget.start_setup_move(now=1.0)
    widget.end_setup_move(now=2.0)

    widget.start_setup_move(now=3.0)

    assert widget.setup_move is not None
    assert widget.setup_move.recording


def test_undo_and_redo_edit_a_live_setup_move(widget) -> None:
    command = TurnCommand(HexCoordinate(0, 0), TurnDirection.CLOCKWISE)
    widget.start_setup_move(now=1.0)
    widget._perform_new_turn(command)
    _finish_turns(widget)

    widget.undo(now=2.0)
    _finish_turns(widget)
    assert widget.setup_move is not None
    assert widget.setup_move.commands == ()

    widget.redo(now=3.0)
    _finish_turns(widget)
    assert widget.setup_move.commands == (command,)


def test_loaded_live_setup_recording_can_continue_and_unwind(widget) -> None:
    first = TurnCommand(HexCoordinate(0, 0), TurnDirection.CLOCKWISE)
    second = TurnCommand(HexCoordinate(1, 0), TurnDirection.COUNTERCLOCKWISE)
    saved_board = PeriodicBoard()
    saved_board.turn(first.coordinate, first.direction)
    state = GameState.capture(
        saved_board,
        game_active=False,
        move_count=0,
        setup_move=SetupMove((first,), recording=True),
    )

    widget.restore_game_state(state)
    widget._perform_new_turn(second)
    _finish_turns(widget)
    assert widget.setup_move is not None
    assert widget.setup_move.commands == (first, second)

    widget.unwind_setup_move(now=2.0)
    _finish_turns(widget)
    assert widget.board.is_solved()
