"""Time-based view state for an already-applied face turn."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from magic_tile.domain import Face, FaceColor, HexCoordinate, PeriodicBoard, TurnDirection


@dataclass(slots=True)
class TurnAnimation:
    """Colors and timing needed to display one atomic model permutation."""

    face: Face
    turning_faces: tuple[Face, ...]
    direction: TurnDirection
    started_at: float
    source_colors: dict[tuple[Face, str, int], FaceColor]
    duration_seconds: float
    render_cache: object | None = field(default=None, repr=False, compare=False)
    completion_frame_shown: bool = field(default=False, repr=False, compare=False)

    @classmethod
    def begin(
        cls,
        board: PeriodicBoard,
        face_coordinate: HexCoordinate,
        direction: TurnDirection,
        started_at: float,
        duration_seconds: float,
    ) -> TurnAnimation:
        """Capture the old colors, then immediately update the exact model."""
        face = board.face_at(face_coordinate)
        turning_faces = board.turning_faces_at(face_coordinate)
        source_colors: dict[tuple[Face, str, int], FaceColor] = {}
        for slot in board.affected_slots(face_coordinate):
            slot_face, kind, index = slot
            values = slot_face.edge_colors if kind == "edge" else slot_face.corner_colors
            source_colors[slot] = values[index]
        board.turn(face_coordinate, direction)
        return cls(
            face,
            turning_faces,
            direction,
            started_at,
            source_colors,
            duration_seconds,
        )

    def progress(self, now: float) -> float:
        """Return linear elapsed progress clamped to the animation duration."""
        return min(1.0, max(0.0, (now - self.started_at) / self.duration_seconds))

    def angle_degrees(self, now: float) -> float:
        """Return a smooth 0-to-60-degree visual rotation."""
        progress = self.progress(now)
        eased = 0.5 - math.cos(math.pi * progress) / 2
        # Positive mathematical rotation appears clockwise in screen
        # coordinates because pygame's y axis points down.
        return -60.0 * int(self.direction) * eased

    def is_finished(self, now: float) -> bool:
        """Return whether interaction may be enabled again."""
        return self.progress(now) >= 1.0
