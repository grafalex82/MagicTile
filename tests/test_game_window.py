import pygame

from magic_tile.domain import HexCoordinate, PeriodicBoard, TurnDirection
from magic_tile.input import parse_macro, serialize_macro
from magic_tile.persistence import Settings
from magic_tile.ui.camera import Camera
from magic_tile.ui.game_window import (
    MACRO_HIGHLIGHT_COLOR,
    TURN_GUIDE_HIGHLIGHT_COLOR,
    _circular_alpha_mask,
    _curved_face_geometry,
    _digit_from_key,
    _left_drag_started,
    _render_turn_frame,
    _scale_turn_frame,
    draw_board,
    run,
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


def test_number_row_and_keypad_digits_map_to_macro_slots() -> None:
    assert _digit_from_key(pygame.K_0) == 0
    assert _digit_from_key(pygame.K_7) == 7
    assert _digit_from_key(pygame.K_KP3) == 3
    assert _digit_from_key(pygame.K_ESCAPE) is None


def test_board_draws_macro_markers_and_recording_panel() -> None:
    board = PeriodicBoard()
    surface = pygame.Surface((640, 480))
    selected_face = board.face_at(HexCoordinate(0, 0))

    draw_board(
        surface,
        board=board,
        macro_face_numbers={selected_face: 1},
        recording_slot=4,
        recording_move_count=3,
    )

    marker_pixels = pygame.mask.from_threshold(
        surface,
        MACRO_HIGHLIGHT_COLOR,
        threshold=(1, 1, 1, 255),
    )
    assert marker_pixels.count() > 0


def test_hover_highlight_is_drawn_above_macro_highlight() -> None:
    board = PeriodicBoard()
    macro_surface = pygame.Surface((640, 480))
    combined_surface = pygame.Surface((640, 480))
    coordinate = HexCoordinate(0, 0)
    camera = Camera(320, 240)

    draw_board(
        macro_surface,
        board=board,
        camera=camera,
        macro_face_numbers={board.face_at(coordinate): 1},
    )
    draw_board(
        combined_surface,
        board=board,
        camera=camera,
        hovered_coordinate=coordinate,
        macro_face_numbers={board.face_at(coordinate): 1},
    )

    macro_mask = pygame.mask.from_threshold(
        macro_surface,
        MACRO_HIGHLIGHT_COLOR,
        threshold=(1, 1, 1, 255),
    )
    hover_mask = pygame.mask.from_threshold(
        combined_surface,
        TURN_GUIDE_HIGHLIGHT_COLOR,
        threshold=(1, 1, 1, 255),
    )
    assert macro_mask.overlap(hover_mask, (0, 0)) is not None


def test_escape_does_not_close_the_application(monkeypatch) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setattr("magic_tile.ui.game_window.WINDOW_SIZE", (320, 240))
    batches = iter(
        (
            [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0)],
            [pygame.event.Event(pygame.QUIT)],
        )
    )
    event_reads = 0

    def next_events() -> list[pygame.event.Event]:
        nonlocal event_reads
        event_reads += 1
        return next(batches)

    monkeypatch.setattr(pygame.event, "get", next_events)

    assert run(Settings(turn_animation_duration_seconds=0.001)) == 0
    assert event_reads == 2


def test_escape_during_macro_playback_does_not_interrupt_queued_turns(monkeypatch) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setattr("magic_tile.ui.game_window.WINDOW_SIZE", (320, 240))
    monkeypatch.setattr(pygame.key, "get_mods", lambda: pygame.KMOD_SHIFT)
    batches = iter(
        (
            [
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100)),
                pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(100, 100)),
            ],
            [
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_0, mod=0),
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0),
            ],
            *([[]] * 8),
            [pygame.event.Event(pygame.QUIT)],
        )
    )
    monkeypatch.setattr(pygame.event, "get", lambda: next(batches))
    animations: list[TurnAnimation] = []
    original_begin = TurnAnimation.begin

    def track_animation(*args, **kwargs) -> TurnAnimation:
        animation = original_begin(*args, **kwargs)
        animations.append(animation)
        return animation

    monkeypatch.setattr(TurnAnimation, "begin", track_animation)
    settings = Settings(turn_animation_duration_seconds=0.001).with_macro(0, parse_macro("1-1'"))

    assert run(settings) == 0
    assert len(animations) == 2


def test_escape_during_recording_animates_rollback_without_saving(monkeypatch) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setattr("magic_tile.ui.game_window.WINDOW_SIZE", (320, 240))
    batches = iter(
        (
            [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_4, mod=pygame.KMOD_CTRL)],
            [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=(100, 100))],
            [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0)],
            *([[]] * 6),
            [pygame.event.Event(pygame.QUIT)],
        )
    )
    monkeypatch.setattr(pygame.event, "get", lambda: next(batches))
    saved_settings: list[Settings] = []
    monkeypatch.setattr("magic_tile.ui.game_window.save_settings", saved_settings.append)
    boards: list[PeriodicBoard] = []
    original_begin = TurnAnimation.begin

    def track_animation(board: PeriodicBoard, *args, **kwargs) -> TurnAnimation:
        boards.append(board)
        return original_begin(board, *args, **kwargs)

    monkeypatch.setattr(TurnAnimation, "begin", track_animation)
    solved_state = PeriodicBoard().sticker_state()

    assert run(Settings(turn_animation_duration_seconds=0.001)) == 0
    assert len(boards) == 2
    assert boards[-1].sticker_state() == solved_state
    assert saved_settings == []


def test_undo_and_redo_edit_the_active_macro_on_the_shared_history(monkeypatch) -> None:
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setattr("magic_tile.ui.game_window.WINDOW_SIZE", (320, 240))
    batches = iter(
        (
            [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_4, mod=pygame.KMOD_CTRL)],
            [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=(100, 100))],
            [],
            [],
            [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_z, mod=pygame.KMOD_CTRL)],
            [],
            [],
            [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0)],
            [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_y, mod=pygame.KMOD_CTRL)],
            [],
            [],
            [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0)],
            [pygame.event.Event(pygame.QUIT)],
        )
    )
    monkeypatch.setattr(pygame.event, "get", lambda: next(batches))
    saved_settings: list[Settings] = []
    monkeypatch.setattr("magic_tile.ui.game_window.save_settings", saved_settings.append)

    assert run(Settings(turn_animation_duration_seconds=0.001)) == 0
    assert len(saved_settings) == 1
    assert serialize_macro(saved_settings[0].macros[4]) == "1"
