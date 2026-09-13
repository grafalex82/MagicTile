"""PyQt6 window, input handling, and orchestration for MagicTile."""

from __future__ import annotations

import random
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import (
    QAction,
    QEnterEvent,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QWheelEvent,
)
from PyQt6.QtWidgets import QApplication, QFileDialog, QMainWindow, QWidget

from magic_tile.domain import HexCoordinate, PeriodicBoard, TurnDirection
from magic_tile.input import (
    MacroRecording,
    MacroSelection,
    SetupMove,
    TurnCommand,
    TurnHistory,
    TurnHistorySnapshot,
)
from magic_tile.persistence import (
    GameState,
    Settings,
    load_game_state,
    save_game_state,
    save_settings,
)
from magic_tile.ui.camera import Camera
from magic_tile.ui.hex_grid import HEX_HEIGHT, hex_at_point
from magic_tile.ui.qt_renderer import (
    MACRO_HIGHLIGHT_COLOR,
    TURN_GUIDE_HIGHLIGHT_COLOR,
    draw_board,
    draw_recording_panel,
    draw_status_message,
    render_board,
    render_static_board,
)
from magic_tile.ui.turn_animation import TurnAnimation

WINDOW_SIZE = (1280, 750)
WINDOW_TITLE = "MagicTile"
PAN_START_DISTANCE_PX = 5
MACRO_MENU_SLOT_ORDER = (*range(1, 10), 0)
SCRAMBLE_MOVE_COUNTS = (3, 5, 10, 50)
GAME_SAVE_FILTER = "MagicTile saves (*.json);;All files (*)"


def _left_drag_started(button_down_at: tuple[int, int], current_position: tuple[int, int]) -> bool:
    """Return whether a left-button gesture has become a camera drag."""
    return any(
        abs(current - initial) > PAN_START_DISTANCE_PX
        for initial, current in zip(button_down_at, current_position, strict=True)
    )


def _digit_from_key(key: int | Qt.Key) -> int | None:
    """Map number-row and keypad digit keys to a macro slot."""
    value = key.value if isinstance(key, Qt.Key) else int(key)
    zero = Qt.Key.Key_0.value
    if zero <= value <= Qt.Key.Key_9.value:
        return value - zero
    return None


@dataclass(frozen=True, slots=True)
class _QueuedTurn:
    """One animation waiting to play, with its history policy."""

    command: TurnCommand
    record_history: bool
    count_player_move: bool = True


class GameBoardWidget(QWidget):
    """Interactive Qt widget containing the board and all game UI state."""

    def __init__(
        self,
        settings: Settings,
        parent: QWidget | None = None,
        *,
        board: PeriodicBoard | None = None,
    ) -> None:
        super().__init__(parent)

        # Create the persistent game services and the board being displayed.
        self.settings = settings
        self.board = PeriodicBoard() if board is None else board
        self.camera = Camera()
        self.turn_history = TurnHistory()

        # A game session begins only through Puzzle -> Scrumble. Free turns
        # made before that point do not contribute to a score or trigger a win.
        self.game_active = False
        self.move_count = 0

        # Initialize macro recording, selection, and queued-playback state.
        self.macro_selection = MacroSelection()
        self.macro_recording: MacroRecording | None = None
        self.recording_history: TurnHistorySnapshot | None = None
        self.setup_move: SetupMove | None = None
        self.setup_recording_history: TurnHistorySnapshot | None = None
        self.setup_history_floor: int | None = None
        self.turn_queue: deque[_QueuedTurn] = deque()
        self.playback_active = False

        # Track the current pointer gesture and active turn animation.
        self.panning = False
        self.left_button_down_at: tuple[int, int] | None = None
        self.left_button_selecting = False
        self.animation: TurnAnimation | None = None

        # Keep transient status and pointer information used by the overlay.
        self.status_message: str | None = None
        self.status_is_error = False
        self.status_until = 0.0
        self.mouse_inside = False
        self.mouse_position = (0, 0)

        # Retain the expensive static board layer until its inputs change.
        self._static_cache_view_key = None
        self._static_cache_state = None
        self._static_cache = None
        self._force_static_refresh = False

        # Configure the widget to receive keyboard and passive mouse events.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

        # Drive time-based animation and queue advancement at roughly 60 Hz.
        self._frame_timer = QTimer(self)
        self._frame_timer.setInterval(16)
        self._frame_timer.timeout.connect(self.advance)
        self._frame_timer.start()

    def sizeHint(self):  # noqa: N802 - Qt virtual method
        """Return the preferred initial board size."""
        from PyQt6.QtCore import QSize

        return QSize(*WINDOW_SIZE)

    def advance(self, now: float | None = None) -> None:
        """Advance status and turn queues, then schedule a repaint."""
        # Use an injected timestamp in tests and the monotonic application
        # clock during normal event-loop updates.
        current = time.monotonic() if now is None else now

        # Remove a temporary status notification after its display interval.
        if self.status_message is not None and current >= self.status_until:
            self.status_message = None

        # Finish the active turn in two phases. The first phase preserves one
        # exact 60-degree frame; the second releases the animation and marks
        # the completed static board for rebuilding.
        if self.animation is not None and self.animation.is_finished(current):
            if self.animation.completion_frame_shown:
                self.animation = None
                self._force_static_refresh = True
            else:
                self.animation.completion_frame_shown = True

        # When no turn is running, start the next queued command and record it
        # when required by its history policy. If the queue is empty, finish
        # the macro-playback session and unlock normal input.
        if self.animation is None:
            if self.turn_queue:
                queued = self.turn_queue.popleft()
                if queued.record_history:
                    self.turn_history.record(queued.command)
                    self._synchronize_setup_move()
                self.animation = TurnAnimation.begin(
                    self.board,
                    queued.command.coordinate,
                    queued.command.direction,
                    current,
                    self.settings.turn_animation_duration_seconds,
                )
                if queued.record_history and queued.count_player_move:
                    self._count_player_move(check_for_win=False)
            elif self.playback_active:
                self.playback_active = False
                self._check_for_win(current)

        # Ask Qt to schedule a paint event for the newly advanced state.
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt virtual method
        """Render the complete frame with QPainter."""
        # Bind a painter to the widget for the duration of this paint event.
        painter = QPainter(self)
        try:
            # Rebuild the static board only when its viewport or settled model
            # state changes, or when animation completion requests a refresh.
            viewport = (self.width(), self.height())
            view_key = (viewport, self.camera.offset, self.camera.zoom)
            board_state = self.board.sticker_state()
            cache_is_stale = self.animation is None and board_state != self._static_cache_state
            if (
                self._static_cache is None
                or view_key != self._static_cache_view_key
                or cache_is_stale
                or self._force_static_refresh
            ):
                self._static_cache = render_static_board(viewport, self.board, self.camera)
                self._static_cache_view_key = view_key
                self._static_cache_state = board_state
                self._force_static_refresh = False

            # Resolve the hovered screen position to a periodic board cell.
            hovered_coordinate = None
            if self.mouse_inside:
                q, r = hex_at_point(
                    self.mouse_position,
                    height=HEX_HEIGHT * self.camera.zoom,
                    offset=self.camera.offset,
                )
                hovered_coordinate = HexCoordinate(q, r)

            # Composite the cached board, current animation, highlights, and
            # macro markers into the widget.
            draw_board(
                painter,
                viewport,
                board=self.board,
                camera=self.camera,
                hovered_coordinate=hovered_coordinate,
                animation=self.animation,
                now=time.monotonic(),
                macro_face_numbers=(
                    self.macro_recording.face_numbers
                    if self.macro_recording is not None
                    else self.macro_selection.face_numbers
                ),
                static_background=self._static_cache,
            )

            # Draw macro-recording information independently from the board.
            if self.macro_recording is not None:
                draw_recording_panel(
                    painter,
                    self.macro_recording.slot,
                    self.macro_recording.move_count,
                    len(self.macro_recording.face_numbers),
                )

            # Draw the temporary status as the topmost interface element.
            if self.status_message is not None:
                draw_status_message(
                    painter,
                    viewport,
                    self.status_message,
                    self.status_is_error,
                )
        finally:
            # Always release the native painting resource, including on error.
            painter.end()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt virtual method
        """Handle macros, cancellation, and history shortcuts."""
        # Capture the key and normalized modifier state once for dispatch.
        now = time.monotonic()
        key = event.key()
        modifiers = event.modifiers()
        control_pressed = bool(
            modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier)
        )
        shift_pressed = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        # Give cancellation and recording completion priority over the normal
        # interaction lock so recording can be resolved at any time.
        if key == Qt.Key.Key_Escape:
            self._handle_escape(now)
            event.accept()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.macro_recording is not None:
            self._save_recording(now)
            event.accept()
            return

        # Ignore all other shortcuts while an atomic turn or macro is active.
        if self.animation is not None or self.playback_active:
            event.accept()
            return

        # Translate digits and history shortcuts into the same commands used
        # by the main-menu actions.
        digit = _digit_from_key(key)
        if digit is not None and control_pressed:
            self.record_macro(digit, now=now)
        elif digit is not None:
            self.play_macro(digit, reverse=shift_pressed, now=now)
        elif control_pressed and key == Qt.Key.Key_Z:
            if shift_pressed:
                self.redo(now=now)
            else:
                self.undo(now=now)
        elif control_pressed and key == Qt.Key.Key_Y:
            self.redo(now=now)
        else:
            super().keyPressEvent(event)
            return

        # Consume every recognized shortcut, including a temporarily blocked
        # command or an empty macro slot.
        event.accept()

    def undo(self, *, now: float | None = None) -> None:
        """Undo one turn through the shared animated history path."""
        if self.animation is not None or self.playback_active:
            return
        minimum = max(
            self.recording_history.position if self.recording_history is not None else 0,
            (
                self.setup_recording_history.position
                if self.setup_recording_history is not None
                else self.setup_history_floor or 0
            ),
        )
        self._apply_history_command(self.turn_history.undo(minimum), now)

    def redo(self, *, now: float | None = None) -> None:
        """Redo one turn through the shared animated history path."""
        if self.animation is not None or self.playback_active:
            return
        self._apply_history_command(self.turn_history.redo(), now)

    def reset(self) -> None:
        """Return to the initial board state and leave game mode."""
        self._prepare_for_new_board_state()
        self.board.reset()
        self.game_active = False
        self.move_count = 0
        self.update()

    def capture_game_state(self) -> GameState:
        """Return the complete persistent state of the current game."""
        return GameState.capture(
            self.board,
            game_active=self.game_active,
            move_count=self.move_count,
            setup_move=self.setup_move,
        )

    def restore_game_state(self, state: GameState) -> None:
        """Replace the current session with a validated saved game."""
        if not isinstance(state, GameState):
            raise TypeError("state must be a GameState")
        self._prepare_for_new_board_state()
        state.restore_board(self.board)
        self.game_active = state.game_active
        self.move_count = state.move_count
        self.setup_move = state.setup_move
        if self.setup_move is not None and self.setup_move.recording:
            self.setup_recording_history = self.turn_history.snapshot()
            for command in self.setup_move.commands:
                self.turn_history.record(command)
        elif self.setup_move is not None:
            self.setup_history_floor = self.turn_history.snapshot().position
        self.update()

    def scrumble(self, turn_count: int = 3) -> None:
        """Reset, apply the requested immediate random turns, and begin a game."""
        if not isinstance(turn_count, int) or isinstance(turn_count, bool) or turn_count <= 0:
            raise ValueError("turn_count must be a positive integer")
        self._prepare_for_new_board_state()
        self.board.reset()
        coordinates = tuple(HexCoordinate(index, 0) for index in range(len(self.board.faces)))
        directions = tuple(TurnDirection)
        for _ in range(turn_count):
            self.board.turn(random.choice(coordinates), random.choice(directions))
        self.game_active = True
        self.move_count = 0
        self._force_static_refresh = True
        self.update()

    def record_macro(self, slot: int, *, now: float | None = None) -> None:
        """Begin recording a macro slot, if board input is currently available."""
        if self.animation is not None or self.playback_active:
            return
        self._begin_recording(slot, time.monotonic() if now is None else now)
        self.update()

    def play_macro(
        self,
        slot: int,
        *,
        reverse: bool = False,
        now: float | None = None,
    ) -> None:
        """Play a macro slot, if board input is currently available."""
        if self.animation is not None or self.playback_active:
            return
        self._play_macro(slot, reverse=reverse, now=time.monotonic() if now is None else now)
        self.update()

    def start_setup_move(self, *, now: float | None = None) -> None:
        """Start recording a new setup sequence when none is active."""
        current = time.monotonic() if now is None else now
        if self.animation is not None or self.playback_active:
            return
        if self.macro_recording is not None:
            self._show_status("Finish the current macro recording first", True, current)
        elif self.setup_move is not None and not self.setup_move.recording:
            self._show_status("Unwind the current Setup Move first", True, current)
        else:
            self.setup_move = SetupMove()
            self.setup_recording_history = self.turn_history.snapshot()
            self.setup_history_floor = None
            self._show_status("Setup Move recording started", False, current)
        self.update()

    def end_setup_move(self, *, now: float | None = None) -> None:
        """Finish recording while retaining the sequence for later unwind."""
        current = time.monotonic() if now is None else now
        if self.animation is not None or self.playback_active:
            return
        if self.setup_move is None or not self.setup_move.recording:
            return
        self.setup_recording_history = None
        if self.setup_move.commands:
            self.setup_move = self.setup_move.finish()
            self.setup_history_floor = self.turn_history.snapshot().position
            self._show_status("Setup Move recording ended", False, current)
        else:
            self.setup_move = None
            self.setup_history_floor = None
            self._show_status("Empty Setup Move discarded", False, current)
        self.update()

    def unwind_setup_move(self, *, now: float | None = None) -> None:
        """Play the active setup sequence backward once, then discard it."""
        current = time.monotonic() if now is None else now
        if self.animation is not None or self.playback_active or self.setup_move is None:
            return
        rollback_commands = self.setup_move.rollback_commands
        self.setup_move = None
        self.setup_recording_history = None
        self.setup_history_floor = None
        self.turn_queue.extend(
            _QueuedTurn(command, record_history=True, count_player_move=False)
            for command in rollback_commands
        )
        self.playback_active = bool(self.turn_queue)
        self._show_status("Setup Move unwound", False, current)
        if self.playback_active:
            self.advance(current)
        else:
            self._check_for_win(current)
        self.update()

    def _apply_history_command(self, command: TurnCommand | None, now: float | None) -> None:
        """Animate a command returned by undo or redo and refresh recording state."""
        if command is not None:
            self.macro_selection.clear()
            self._synchronize_recording()
            self._synchronize_setup_move()
            self._begin_animation(command, time.monotonic() if now is None else now)
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt virtual method
        """Start a pan/select gesture or perform a clockwise turn."""
        # Update hover state from the position delivered with the press.
        self.mouse_inside = True
        self.mouse_position = self._event_position(event)

        # Keep turns and macro playback atomic by rejecting new board input.
        if self.animation is not None or self.playback_active:
            event.accept()
            return

        # A left press begins a possible click, selection, or pan gesture;
        # a right press performs its clockwise turn immediately.
        if event.button() == Qt.MouseButton.LeftButton:
            self.left_button_down_at = self.mouse_position
            self.left_button_selecting = self.macro_recording is None and bool(
                event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            )
            self.panning = False
        elif event.button() == Qt.MouseButton.RightButton:
            coordinate = self._coordinate_at(self.mouse_position)
            self._perform_new_turn(TurnCommand(coordinate, TurnDirection.CLOCKWISE))

        # Prevent the handled mouse press from propagating to the parent.
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt virtual method
        """Finish a left-button selection, turn, or pan gesture."""
        # Refresh the pointer position and delegate unrelated button releases.
        self.mouse_position = self._event_position(event)
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return

        # Treat a stationary left gesture as either macro-face selection or a
        # counterclockwise turn; a completed pan performs neither action.
        if self.left_button_down_at is not None and not self.panning:
            coordinate = self._coordinate_at(self.left_button_down_at)
            if self.left_button_selecting and self.macro_recording is None:
                self.macro_selection.add(self.board, coordinate)
            else:
                self._perform_new_turn(TurnCommand(coordinate, TurnDirection.COUNTERCLOCKWISE))

        # Clear all gesture flags so the next press starts independently.
        self.left_button_down_at = None
        self.left_button_selecting = False
        self.panning = False

        # Repaint selection changes and consume the release event.
        self.update()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt virtual method
        """Update hover state and pan an active drag."""
        previous = self.mouse_position
        self.mouse_position = self._event_position(event)
        self.mouse_inside = True
        if self.left_button_down_at is not None:
            if self.panning or _left_drag_started(self.left_button_down_at, self.mouse_position):
                self.panning = True
                self.camera.pan(
                    self.mouse_position[0] - previous[0],
                    self.mouse_position[1] - previous[1],
                )
        self.update()
        event.accept()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt virtual method
        """Zoom around the pointer using the wheel's standard step units."""
        if self.animation is None and not self.playback_active:
            delta = event.angleDelta().y()
            if delta:
                position = event.position()
                self.camera.zoom_by(delta / 120, (position.x(), position.y()))
                self.update()
        event.accept()

    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802 - Qt virtual method
        self.mouse_inside = True
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt virtual method
        self.mouse_inside = False
        self.update()

    @staticmethod
    def _event_position(event: QMouseEvent) -> tuple[int, int]:
        position = event.position()
        return round(position.x()), round(position.y())

    def _coordinate_at(self, point: tuple[int, int]) -> HexCoordinate:
        q, r = hex_at_point(point, height=HEX_HEIGHT * self.camera.zoom, offset=self.camera.offset)
        return HexCoordinate(q, r)

    def _perform_new_turn(self, command: TurnCommand) -> None:
        self.macro_selection.clear()
        self.turn_history.record(command)
        self._synchronize_recording()
        self._synchronize_setup_move()
        self._begin_animation(command, time.monotonic())
        self._count_player_move()

    def _begin_animation(self, command: TurnCommand, now: float) -> None:
        self.animation = TurnAnimation.begin(
            self.board,
            command.coordinate,
            command.direction,
            now,
            self.settings.turn_animation_duration_seconds,
        )

    def _synchronize_recording(self) -> None:
        if self.macro_recording is None:
            return
        if self.recording_history is None:
            raise RuntimeError("macro recording has no history snapshot")
        commands = self.turn_history.commands_since(self.recording_history.position)
        self.macro_recording.synchronize(self.board, commands)

    def _synchronize_setup_move(self) -> None:
        """Match an active setup recording to its editable history segment."""
        if self.setup_move is None or not self.setup_move.recording:
            return
        if self.setup_recording_history is None:
            raise RuntimeError("setup move recording has no history snapshot")
        commands = self.turn_history.commands_since(self.setup_recording_history.position)
        self.setup_move = self.setup_move.synchronize(commands)

    def _prepare_for_new_board_state(self) -> None:
        """Clear transient interaction and history before reset or scrambling."""
        self.animation = None
        self.turn_queue.clear()
        self.playback_active = False
        self.turn_history.clear()
        self.macro_recording = None
        self.recording_history = None
        self.setup_move = None
        self.setup_recording_history = None
        self.setup_history_floor = None
        self.macro_selection.clear()
        self.left_button_down_at = None
        self.left_button_selecting = False
        self.panning = False
        self.status_message = None
        self._force_static_refresh = True

    def _count_player_move(self, *, check_for_win: bool = True) -> None:
        """Count a player turn in game mode and optionally test the result."""
        if not self.game_active:
            return
        self.move_count += 1
        if check_for_win:
            self._check_for_win(time.monotonic())

    def _check_for_win(self, now: float) -> None:
        """Finish the active game when the board reaches its solved state."""
        if not self.game_active or not self.board.is_solved():
            return
        self.game_active = False
        move_word = "move" if self.move_count == 1 else "moves"
        self._show_status(
            f"Congratulations! Puzzle solved in {self.move_count} {move_word}.",
            False,
            now,
            duration=5.0,
        )

    def _handle_escape(self, now: float) -> None:
        # Macro playback is intentionally atomic and cannot be canceled.
        if self.playback_active:
            return

        # Cancel setup recording without changing turns already made on the board.
        if self.setup_move is not None and self.setup_move.recording:
            self.setup_move = None
            self.setup_recording_history = None
            self.setup_history_floor = None
            self.macro_selection.clear()
            self._show_status("Setup Move recording canceled", False, now)

        # Cancel a live recording by queuing inverse moves, restoring its
        # history snapshot, and clearing all provisional macro state.
        elif self.macro_recording is not None:
            self.turn_queue.extend(
                _QueuedTurn(command, record_history=False)
                for command in self.macro_recording.rollback_commands
            )
            if self.recording_history is None:
                raise RuntimeError("macro recording has no history snapshot")
            self.turn_history.restore(self.recording_history)
            self.macro_recording = None
            self.recording_history = None
            self.macro_selection.clear()
            self.playback_active = bool(self.turn_queue)
            self._show_status("Macro recording canceled", False, now)

        # Outside recording, Escape only clears the selected macro faces.
        elif self.macro_selection:
            self.macro_selection.clear()
            self.status_message = None

        # Display the updated recording or selection state.
        self.update()

    def _begin_recording(self, slot: int, now: float) -> None:
        if self.setup_move is not None and self.setup_move.recording:
            self._show_status("End Setup Move recording first", True, now)
        elif self.macro_recording is None:
            self.macro_selection.clear()
            self.macro_recording = MacroRecording(slot)
            self.recording_history = self.turn_history.snapshot()
            self.status_message = None
        else:
            self._show_status("Finish the current recording first", True, now)

    def _save_recording(self, now: float) -> None:
        # Ignore calls made after the recording has already ended.
        if self.macro_recording is None:
            return

        # Validate that the recording contains at least one serializable move.
        try:
            macro = self.macro_recording.macro
        except ValueError:
            self._show_status("Cannot save an empty macro", True, now)
            return

        # Build updated immutable settings and persist them atomically.
        new_settings = self.settings.with_macro(self.macro_recording.slot, macro)
        try:
            save_settings(new_settings)
        except OSError as error:
            self._show_status(f"Could not save macro: {error}", True, now, duration=5.0)
            return

        # Commit the new settings locally and leave recording mode.
        slot = self.macro_recording.slot
        self.settings = new_settings
        self.macro_recording = None
        self.recording_history = None
        self._show_status(f"Macro {slot} saved", False, now)

    def _play_macro(self, slot: int, *, reverse: bool, now: float) -> None:
        # A recording cannot recursively launch another macro.
        if self.macro_recording is not None:
            return
        if self.setup_move is not None and self.setup_move.recording:
            self._show_status("End Setup Move recording first", True, now)
            return

        # Empty macro slots have no action associated with their digit.
        macro = self.settings.macros[slot]
        if macro is None:
            return

        # Resolve relative face numbers against the ordered current selection.
        try:
            commands = macro.commands(self.macro_selection.coordinates, reverse=reverse)
        except ValueError:
            self._show_status(
                f"Macro {slot} requires {macro.required_face_count} faces; "
                f"selected {len(self.macro_selection.coordinates)}",
                True,
                now,
            )
            return

        # Queue the resolved turns, lock input for atomic playback, and start
        # the first command without waiting for the next timer tick.
        self.turn_queue.extend(_QueuedTurn(command, record_history=True) for command in commands)
        self.playback_active = True
        self.status_message = None
        self.advance(now)

    def _show_status(self, message: str, is_error: bool, now: float, duration: float = 3.0) -> None:
        self.status_message = message
        self.status_is_error = is_error
        self.status_until = now + duration


class GameWindow(QMainWindow):
    """Top-level resizable MagicTile window."""

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.board_widget = GameBoardWidget(settings, self)
        self.current_save_path: Path | None = None
        self.setCentralWidget(self.board_widget)
        self._create_actions()
        self._create_main_menu()
        self.resize(*WINDOW_SIZE)

    def _create_actions(self) -> None:
        """Create reusable application commands for the menu and shortcuts."""
        self.open_action = QAction("Open", self)
        self.open_action.setObjectName("open_action")
        self.open_action.setShortcuts(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.open_game)

        self.save_action = QAction("Save", self)
        self.save_action.setObjectName("save_action")
        self.save_action.setShortcuts(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.save_game)

        self.save_as_action = QAction("Save As", self)
        self.save_as_action.setObjectName("save_as_action")
        self.save_as_action.setShortcuts(QKeySequence.StandardKey.SaveAs)
        self.save_as_action.triggered.connect(self.save_game_as)

        self.quit_action = QAction("Quit", self)
        self.quit_action.setObjectName("quit_action")
        self.quit_action.setShortcuts(QKeySequence.StandardKey.Quit)
        self.quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        self.quit_action.triggered.connect(QApplication.quit)

        self.reset_action = QAction("Reset", self)
        self.reset_action.setObjectName("reset_action")
        self.reset_action.triggered.connect(self.board_widget.reset)

        self.scrumble_actions = tuple(
            self._scrumble_action(move_count) for move_count in SCRAMBLE_MOVE_COUNTS
        )

        self.undo_action = QAction("Undo", self)
        self.undo_action.setObjectName("undo_action")
        self.undo_action.setShortcuts(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self.board_widget.undo)

        self.redo_action = QAction("Redo", self)
        self.redo_action.setObjectName("redo_action")
        self.redo_action.setShortcuts(QKeySequence.StandardKey.Redo)
        self.redo_action.triggered.connect(self.board_widget.redo)

        self.record_actions = tuple(self._macro_action("Record", slot) for slot in range(10))
        self.play_actions = tuple(self._macro_action("Play", slot) for slot in range(10))
        self.reverse_play_actions = tuple(
            self._macro_action("Play", slot, reverse=True) for slot in range(10)
        )

        self.start_setup_move_action = self._setup_move_action(
            "Start Setup Move", "F1", self.board_widget.start_setup_move
        )
        self.end_setup_move_action = self._setup_move_action(
            "End Setup Move", "F2", self.board_widget.end_setup_move
        )
        self.unwind_setup_move_action = self._setup_move_action(
            "Unwind Setup Move", "F3", self.board_widget.unwind_setup_move
        )

    def open_game(self) -> None:
        """Choose a save file and replace the current game with its contents."""
        filename, _ = QFileDialog.getOpenFileName(self, "Open MagicTile Game", "", GAME_SAVE_FILTER)
        if not filename:
            return

        path = Path(filename)
        try:
            state = load_game_state(path)
            self.board_widget.restore_game_state(state)
        except (OSError, UnicodeError, ValueError) as error:
            self.board_widget._show_status(f"Could not open game: {error}", True, time.monotonic(), 5.0)
            self.board_widget.update()
            return

        self.current_save_path = path
        self.board_widget._show_status("Game loaded", False, time.monotonic())
        self.board_widget.update()

    def save_game(self) -> None:
        """Save to the current file, prompting for one when necessary."""
        if self.current_save_path is None:
            self.save_game_as()
            return
        self._save_game_to(self.current_save_path)

    def save_game_as(self) -> None:
        """Choose a file and save the current game to it."""
        initial = (
            str(self.current_save_path)
            if self.current_save_path is not None
            else "magic_tile_save.json"
        )
        filename, _ = QFileDialog.getSaveFileName(self, "Save MagicTile Game", initial, GAME_SAVE_FILTER)
        if filename:
            self._save_game_to(Path(filename))

    def _save_game_to(self, path: Path) -> None:
        """Persist the current game and report errors without replacing its path."""
        try:
            save_game_state(self.board_widget.capture_game_state(), path)
        except (OSError, ValueError) as error:
            self.board_widget._show_status(f"Could not save game: {error}", True, time.monotonic(), 5.0)
            self.board_widget.update()
            return

        self.current_save_path = path
        self.board_widget._show_status(f"Game saved to {path.name}", False, time.monotonic())
        self.board_widget.update()

    def _setup_move_action(self, text: str, shortcut: str, callback) -> QAction:
        """Create an enabled setup-move command with its function-key binding."""
        action = QAction(text, self)
        action.setObjectName(f"{text.lower().replace(' ', '_')}_action")
        action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(callback)
        return action

    def _macro_action(self, operation: str, slot: int, *, reverse: bool = False) -> QAction:
        """Create one macro-slot action and bind its existing keyboard shortcut."""
        text = f"Macro {slot}"
        action = QAction(f"{text} (Reverse)" if reverse else text, self)
        direction_name = "reverse_" if reverse else ""
        action.setObjectName(f"macro_{operation.lower()}_{direction_name}{slot}_action")
        if operation == "Record":
            action.setShortcut(QKeySequence(f"Ctrl+{slot}"))
            action.triggered.connect(
                lambda checked=False, selected_slot=slot: self.board_widget.record_macro(selected_slot),
            )
        else:
            shortcut = f"Shift+{slot}" if reverse else str(slot)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(
                lambda checked=False, selected_slot=slot, play_reverse=reverse: (
                    self.board_widget.play_macro(selected_slot, reverse=play_reverse)
                ),
            )
        return action

    def _scrumble_action(self, move_count: int) -> QAction:
        """Create a scramble action for one of the offered move counts."""
        action = QAction(f"{move_count} moves", self)
        action.setObjectName(f"scrumble_{move_count}_moves_action")
        action.triggered.connect(
            lambda checked=False, selected_count=move_count: (
                self.board_widget.scrumble(selected_count)
            ),
        )
        return action

    def _create_main_menu(self) -> None:
        """Build the requested top-level menu hierarchy."""
        menu_bar = self.menuBar()

        self.file_menu = menu_bar.addMenu("File")
        self.file_menu.addActions((self.open_action, self.save_action, self.save_as_action))
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.quit_action)

        self.puzzle_menu = menu_bar.addMenu("Puzzle")
        self.puzzle_menu.addAction(self.reset_action)
        self.scrumble_menu = self.puzzle_menu.addMenu("Scrumble")
        self.scrumble_menu.addActions(self.scrumble_actions)
        self.scrumble_action = self.scrumble_menu.menuAction()
        self.puzzle_menu.addSeparator()
        self.puzzle_menu.addActions((self.undo_action, self.redo_action))

        self.macro_menu = menu_bar.addMenu("Macro")
        self.record_menu = self.macro_menu.addMenu("Record")
        self.record_menu.addActions(tuple(self.record_actions[slot] for slot in MACRO_MENU_SLOT_ORDER))
        self.play_menu = self.macro_menu.addMenu("Play")
        self.play_menu.addActions(tuple(self.play_actions[slot] for slot in MACRO_MENU_SLOT_ORDER))
        self.play_menu.addSeparator()
        self.play_menu.addActions(
            tuple(self.reverse_play_actions[slot] for slot in MACRO_MENU_SLOT_ORDER),
        )
        self.macro_menu.addSeparator()
        self.macro_menu.addActions(
            (
                self.start_setup_move_action,
                self.end_setup_move_action,
                self.unwind_setup_move_action,
            ),
        )


def run(settings: Settings) -> int:
    """Create the Qt application and run its event loop."""
    application = QApplication.instance()
    owns_application = application is None
    if application is None:
        application = QApplication(sys.argv)
    window = GameWindow(settings)
    window.show()
    if not owns_application:
        return 0
    return application.exec()
