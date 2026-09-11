"""Pygame window and the static MagicTile board prototype."""

from __future__ import annotations

import pygame

from magic_tile.domain import BOARD, HexCoordinate, PeriodicBoard
from magic_tile.ui.camera import Camera
from magic_tile.ui.hex_grid import hex_vertices, visible_hexes

WINDOW_SIZE = (1280, 800)
WINDOW_TITLE = "MagicTile"

BACKGROUND = pygame.Color("#000000")
GRID_COLOR = pygame.Color("#000000")
GRID_WIDTH = 10

def draw_board(
    surface: pygame.Surface,
    board: PeriodicBoard = BOARD,
    camera: Camera | None = None,
) -> None:
    """Draw the board using colours supplied by the domain model."""
    surface.fill(BACKGROUND)
    offset = camera.offset if camera is not None else (0.0, 0.0)

    for q, r, center in visible_hexes(surface.get_size(), offset=offset):
        face = board.face_at(HexCoordinate(q, r))
        points = hex_vertices(center)
        pygame.draw.polygon(surface, face.center.color.rgb, points)
        pygame.draw.polygon(surface, GRID_COLOR, points, width=GRID_WIDTH)


def run() -> int:
    """Open the main window and run its event/render loop."""
    pygame.init()
    try:
        screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
        pygame.display.set_caption(WINDOW_TITLE)
        clock = pygame.time.Clock()
        camera = Camera()
        panning_buttons: set[int] = set()
        running = True

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 2):
                    panning_buttons.add(event.button)
                elif event.type == pygame.MOUSEBUTTONUP and event.button in (1, 2):
                    panning_buttons.discard(event.button)
                elif event.type == pygame.MOUSEMOTION and panning_buttons:
                    camera.pan(*event.rel)

            draw_board(screen, camera=camera)
            pygame.display.flip()
            clock.tick(60)
    finally:
        pygame.quit()

    return 0
