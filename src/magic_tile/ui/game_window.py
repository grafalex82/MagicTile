"""Pygame window and the static MagicTile board prototype."""

from __future__ import annotations

import pygame

from magic_tile.ui.hex_grid import hex_vertices, visible_hexes

WINDOW_SIZE = (1280, 800)
WINDOW_TITLE = "MagicTile"

BACKGROUND = pygame.Color("#000000")
GRID_COLOR = pygame.Color("#000000")
GRID_WIDTH = 10

# Nine deliberately distinct face colours.  The sequence repeats across the
# viewport for now; it is presentation-only and is not a puzzle data model.
FACE_COLORS = (
    pygame.Color("#ff1010"),
    pygame.Color("#ff8500"),
    pygame.Color("#fff600"),
    pygame.Color("#07950d"),
    pygame.Color("#08e4e8"),
    pygame.Color("#1515e8"),
    pygame.Color("#f0008f"),
    pygame.Color("#7f24d6"),
    pygame.Color("#f7f7f7"),
)


def face_color(column: int, row: int) -> pygame.Color:
    """Choose one of nine periodic placeholder colours for a grid cell."""
    return FACE_COLORS[(column + 2 * row) % len(FACE_COLORS)]


def draw_board(surface: pygame.Surface) -> None:
    """Draw the static repeating hexagonal board."""
    surface.fill(BACKGROUND)

    for column, row, center in visible_hexes(surface.get_size()):
        points = hex_vertices(center)
        pygame.draw.polygon(surface, face_color(column, row), points)
        pygame.draw.polygon(surface, GRID_COLOR, points, width=GRID_WIDTH)


def run() -> int:
    """Open the main window and run its event/render loop."""
    pygame.init()
    try:
        screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
        pygame.display.set_caption(WINDOW_TITLE)
        clock = pygame.time.Clock()
        running = True

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False

            draw_board(screen)
            pygame.display.flip()
            clock.tick(60)
    finally:
        pygame.quit()

    return 0
