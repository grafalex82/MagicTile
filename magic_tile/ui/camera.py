"""Camera state for navigating the infinite game board."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Camera:
    """An unrestricted screen-space translation of the game board."""

    x: float = 0.0
    y: float = 0.0

    @property
    def offset(self) -> tuple[float, float]:
        return self.x, self.y

    def pan(self, dx: float, dy: float) -> None:
        """Move the board by a mouse-sized screen-space delta."""
        self.x += dx
        self.y += dy
