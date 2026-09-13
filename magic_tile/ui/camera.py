"""Camera state for navigating the infinite game board."""

from __future__ import annotations

from dataclasses import dataclass

MIN_ZOOM = 0.5
MAX_ZOOM = 2.5
ZOOM_STEP = 1.1


@dataclass
class Camera:
    """Screen-space translation and zoom of the game board."""

    x: float = 0.0
    y: float = 0.0
    zoom: float = 1.0

    @property
    def offset(self) -> tuple[float, float]:
        return self.x, self.y

    def pan(self, dx: float, dy: float) -> None:
        """Move the board by a mouse-sized screen-space delta."""
        self.x += dx
        self.y += dy

    def zoom_by(self, steps: float, focus: tuple[float, float]) -> None:
        """Zoom by mouse-wheel steps while keeping ``focus`` stationary."""
        if steps == 0:
            return

        old_zoom = self.zoom
        self.zoom = min(MAX_ZOOM, max(MIN_ZOOM, old_zoom * ZOOM_STEP**steps))
        ratio = self.zoom / old_zoom
        focus_x, focus_y = focus
        self.x = focus_x - (focus_x - self.x) * ratio
        self.y = focus_y - (focus_y - self.y) * ratio
