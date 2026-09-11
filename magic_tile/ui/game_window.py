"""Pygame window and the static MagicTile board prototype."""

from __future__ import annotations

import pygame

from magic_tile.domain import BOARD, HexCoordinate, PeriodicBoard
from magic_tile.ui.camera import Camera
from magic_tile.ui.hex_grid import HEX_HEIGHT, hex_at_point, hex_vertices, visible_hexes

WINDOW_SIZE = (1280, 800)
WINDOW_TITLE = "MagicTile"

BACKGROUND = pygame.Color("#000000")
GRID_COLOR = pygame.Color("#000000")
GRID_WIDTH = 10
TURN_GUIDE_COLOR = pygame.Color("#000000")
TURN_GUIDE_WIDTH = 4
TURN_GUIDE_HIGHLIGHT_COLOR = pygame.Color("#ff4040")
TURN_GUIDE_HIGHLIGHT_WIDTH = 2
# The guide reaches beyond every corner of the face and into its outer ring,
# matching the intended visual boundary of a future turn animation.
TURN_GUIDE_DIAMETER_SCALE = 1.55


def draw_board(
    surface: pygame.Surface,
    board: PeriodicBoard = BOARD,
    camera: Camera | None = None,
    hovered_coordinate: HexCoordinate | None = None,
) -> None:
    """Draw the board using colours supplied by the domain model."""
    # Clear the previous frame before drawing the current board state.
    surface.fill(BACKGROUND)

    # Convert the camera state into screen-space dimensions and translation.
    offset = camera.offset if camera is not None else (0.0, 0.0)
    zoom = camera.zoom if camera is not None else 1.0
    hex_height = HEX_HEIGHT * zoom

    # Materialize the visible cells once because every rendering layer uses them.
    visible = list(
        visible_hexes(surface.get_size(), height=hex_height, offset=offset)
    )

    # Draw the colored faces first, followed by their thick grid borders.
    for q, r, center in visible:
        face = board.face_at(HexCoordinate(q, r))
        points = hex_vertices(center, height=hex_height)
        pygame.draw.polygon(surface, face.center.color.rgb, points)
        pygame.draw.polygon(
            surface, GRID_COLOR, points, width=max(1, round(GRID_WIDTH * zoom))
        )

    # Draw turn-area guides above every face so neighboring fills cannot cover them.
    guide_radius = round(hex_height * TURN_GUIDE_DIAMETER_SCALE / 2)
    guide_width = max(1, round(TURN_GUIDE_WIDTH * zoom))
    for _, _, center in visible:
        pygame.draw.circle(
            surface,
            TURN_GUIDE_COLOR,
            (round(center[0]), round(center[1])),
            guide_radius,
            width=guide_width,
        )

    # Highlight every visible copy of the hovered logical face in the guide center.
    if hovered_coordinate is not None:
        hovered_face = board.face_at(hovered_coordinate)
        highlight_radius = guide_radius - (
            guide_width - TURN_GUIDE_HIGHLIGHT_WIDTH
        ) // 2
        for q, r, center in visible:
            if board.face_at(HexCoordinate(q, r)) is hovered_face:
                pygame.draw.circle(
                    surface,
                    TURN_GUIDE_HIGHLIGHT_COLOR,
                    (round(center[0]), round(center[1])),
                    highlight_radius,
                    width=TURN_GUIDE_HIGHLIGHT_WIDTH,
                )


def run() -> int:
    """Open the main window and run its event/render loop."""
    pygame.init()
    try:
        screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
        pygame.display.set_caption(WINDOW_TITLE)
        clock = pygame.time.Clock()
        camera = Camera()
        panning_buttons: set[int] = set()
        mouse_inside = pygame.mouse.get_focused()
        running = True

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.WINDOWLEAVE:
                    mouse_inside = False
                elif event.type == pygame.WINDOWENTER:
                    mouse_inside = True
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 2):
                    panning_buttons.add(event.button)
                elif event.type == pygame.MOUSEBUTTONUP and event.button in (1, 2):
                    panning_buttons.discard(event.button)
                elif event.type == pygame.MOUSEMOTION and panning_buttons:
                    mouse_inside = True
                    camera.pan(*event.rel)
                elif event.type == pygame.MOUSEMOTION:
                    mouse_inside = True
                elif event.type == pygame.MOUSEWHEEL:
                    camera.zoom_by(event.y, pygame.mouse.get_pos())

            hovered_coordinate = None
            if mouse_inside:
                q, r = hex_at_point(
                    pygame.mouse.get_pos(),
                    height=HEX_HEIGHT * camera.zoom,
                    offset=camera.offset,
                )
                hovered_coordinate = HexCoordinate(q, r)

            draw_board(
                screen,
                camera=camera,
                hovered_coordinate=hovered_coordinate,
            )
            pygame.display.flip()
            clock.tick(60)
    finally:
        pygame.quit()

    return 0
