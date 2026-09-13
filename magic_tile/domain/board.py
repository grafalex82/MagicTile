"""Data model for a coordinate-identified periodic hexagonal plane."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum


class FaceColor(Enum):
    """The seven saturated colours used by the reference configuration."""

    WHITE = (255, 255, 255)
    CYAN = (0, 225, 232)
    RED = (255, 0, 0)
    ORANGE = (255, 128, 0)
    BLUE = (17, 17, 232)
    DARK_GREEN = (0, 143, 0)
    YELLOW = (255, 255, 0)

    @property
    def rgb(self) -> tuple[int, int, int]:
        """Return the colour as an RGB tuple usable by renderers."""
        return self.value


class TurnDirection(IntEnum):
    """Direction of one 60-degree face turn as seen on screen."""

    CLOCKWISE = -1
    COUNTERCLOCKWISE = 1


@dataclass(frozen=True, slots=True)
class HexCoordinate:
    r"""Integer axial coordinate of a hexagon on the infinite plane.

    ``q`` runs diagonally from upper-left to lower-right. Moving one step in
    the positive ``q`` direction changes ``(q, r)`` to ``(q + 1, r)``;
    moving in the negative direction changes it to ``(q - 1, r)``.

    ``r`` runs vertically from top to bottom. Moving one step in the positive
    ``r`` direction changes ``(q, r)`` to ``(q, r + 1)``; moving in the
    negative direction changes it to ``(q, r - 1)``.

    The third cube-coordinate component is not stored because it is always
    derived as ``s = -q - r``. The six directions around the origin are::

                              (0, -1)  r -
                                  |
             q -  (-1, 0)         |         (1, -1)
                            \      |      /
                             \     |     /
                                (0, 0)
                             /     |     \
                            /      |      \
                  (-1, 1)         |         (1, 0)  q +
                                  |
                               (0, 1)  r +

    Consequently, the six one-step coordinate changes in cyclic order are
    ``(+1, 0)``, ``(+1, -1)``, ``(0, -1)``, ``(-1, 0)``, ``(-1, +1)``, and
    ``(0, +1)``.
    """

    q: int
    r: int

    def translated(self, dq: int, dr: int) -> HexCoordinate:
        """Return the coordinate reached by an axial translation."""
        return HexCoordinate(self.q + dq, self.r + dr)


@dataclass(slots=True, eq=False)
class Face:
    """One logical face and its currently visible colours.

    A face deliberately has no coordinate: because the plane repeats, many
    cells at different coordinates can resolve to this same object. ``color``
    is presentation data rather than identity. Neighbor references are
    connected once by :class:`PeriodicBoard` after all objects are created.

    Equality and hashing use object identity, allowing a face reference to be
    used as a stable slot-map key without deriving an identifier from color.
    """

    color: FaceColor
    edge_colors: tuple[FaceColor, ...] = ()
    corner_colors: tuple[FaceColor, ...] = ()
    _neighbors: tuple[Face, ...] | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.edge_colors:
            self.edge_colors = (self.color,) * 6
        if not self.corner_colors:
            self.corner_colors = (self.color,) * 6
        if len(self.edge_colors) != 6:
            raise ValueError("a face must contain six edge colors")
        if len(self.corner_colors) != 6:
            raise ValueError("a face must contain six corner colors")

    @property
    def neighbors(self) -> tuple[Face, ...]:
        """Return the six permanently connected neighbors in slot order."""
        if self._neighbors is None:
            raise RuntimeError("face neighbors have not been connected")
        return self._neighbors

    def _connect_neighbors(self, neighbors: tuple[Face, ...]) -> None:
        """Connect this face exactly once while the board is being built."""
        if self._neighbors is not None:
            raise RuntimeError("face neighbors are already connected")
        if len(neighbors) != 6:
            raise ValueError("a face must have six neighbors")
        self._neighbors = neighbors


Slot = tuple[Face, str, int]


class PeriodicBoard:
    """Infinite plane backed by a fixed torus of logical face objects.

    The current reference configuration has seven faces. ``face_at`` retains
    the existing seven-cell mapping, while every other model operation works
    with face references and pre-built neighbor references. Following any one
    neighbor direction seven times therefore returns to the same face object.
    """

    NEIGHBOUR_DIRECTIONS = (
        (1, 0),
        (1, -1),
        (0, -1),
        (-1, 0),
        (-1, 1),
        (0, 1),
    )

    def __init__(self) -> None:
        """Build and permanently connect the solved seven-face torus."""
        palette = tuple(FaceColor)
        self._faces = tuple(Face(color) for color in palette)

        # Calculate adjacency here, once. Turns never derive it from colour.
        for index, face in enumerate(self._faces):
            representative = HexCoordinate(index, 0)
            face._connect_neighbors(
                tuple(
                    self.face_at(representative.translated(dq, dr)) for dq, dr in self.NEIGHBOUR_DIRECTIONS
                ),
            )

    @property
    def faces(self) -> tuple[Face, ...]:
        """Return the logical face objects in configuration order."""
        return self._faces

    def face_at(self, coordinate: HexCoordinate) -> Face:
        """Return the logical face repeated at an axial coordinate.

        Different coordinates may return the same object. The modulo formula
        is deliberately isolated here so it can later be replaced by a
        configuration-driven lookup without affecting adjacency or turn logic.

        The current seven-face layout numbers the face objects from 0 to 6 and
        maps ``(q, r)`` to ``(q + 3 * r) mod 7``. For the six neighbor offsets
        in ``NEIGHBOUR_DIRECTIONS``, ``dq + 3 * dr`` gives, in order,
        ``1, -2, -3, -1, 2, 3``. Modulo 7 these are exactly the six non-zero
        residues, so a cell and its six neighbors resolve to all seven face
        objects once each.

        A translation repeats the same face whenever ``dq + 3 * dr`` is a
        multiple of 7. For example, both ``(1, 2)`` and ``(3, -1)`` are period
        vectors. A step in any fixed neighbor direction adds a non-zero residue
        modulo 7, so seven such steps return to the starting face object.
        """
        index = (coordinate.q + 3 * coordinate.r) % len(self._faces)
        return self._faces[index]

    def turning_faces_at(self, coordinate: HexCoordinate) -> tuple[Face, ...]:
        """Return independently identified faces that turn together.

        Colour determines only the synchronous move group. Every returned face
        remains a distinct object and may have a different neighborhood.
        """
        selected = self.face_at(coordinate)
        return tuple(face for face in self._faces if face.color == selected.color)

    def turn(self, coordinate: HexCoordinate, direction: TurnDirection) -> None:
        """Apply simultaneous exact 60-degree turns for the selected group."""
        if not isinstance(coordinate, HexCoordinate):
            raise TypeError("coordinate must be a HexCoordinate")
        if not isinstance(direction, TurnDirection):
            raise TypeError("direction must be a TurnDirection")

        step = int(direction)
        old_edges = {face: face.edge_colors for face in self._faces}
        old_corners = {face: face.corner_colors for face in self._faces}
        new_edges = {face: list(face.edge_colors) for face in self._faces}
        new_corners = {face: list(face.corner_colors) for face in self._faces}

        for focus in self.turning_faces_at(coordinate):
            for source_index in range(6):
                destination_index = (source_index + step) % 6

                new_edges[focus][destination_index] = old_edges[focus][source_index]
                new_corners[focus][destination_index] = old_corners[focus][source_index]

                source_neighbor = focus.neighbors[source_index]
                destination_neighbor = focus.neighbors[destination_index]
                source_edge = (source_index + 3) % 6
                destination_edge = (destination_index + 3) % 6
                new_edges[destination_neighbor][destination_edge] = old_edges[source_neighbor][source_edge]

                for source_corner in (
                    (source_index + 2) % 6,
                    (source_index + 3) % 6,
                ):
                    destination_corner = (source_corner + step) % 6
                    new_corners[destination_neighbor][destination_corner] = old_corners[source_neighbor][
                        source_corner
                    ]

        for face in self._faces:
            face.edge_colors = tuple(new_edges[face])
            face.corner_colors = tuple(new_corners[face])

    def reset(self) -> None:
        """Restore every movable sticker to the solved configuration."""
        for face in self._faces:
            face.edge_colors = (face.color,) * 6
            face.corner_colors = (face.color,) * 6

    def is_solved(self) -> bool:
        """Return whether every sticker matches the centre of its face."""
        return all(
            all(color is face.color for color in face.edge_colors + face.corner_colors)
            for face in self._faces
        )

    def affected_slots(self, coordinate: HexCoordinate) -> frozenset[Slot]:
        """Return face-reference-addressed slots moved by the turn group."""
        if not isinstance(coordinate, HexCoordinate):
            raise TypeError("coordinate must be a HexCoordinate")

        slots: set[Slot] = set()
        for focus in self.turning_faces_at(coordinate):
            for index, neighbor in enumerate(focus.neighbors):
                slots.add((focus, "edge", index))
                slots.add((focus, "corner", index))
                slots.add((neighbor, "edge", (index + 3) % 6))
                slots.add((neighbor, "corner", (index + 2) % 6))
                slots.add((neighbor, "corner", (index + 3) % 6))
        return frozenset(slots)

    def sticker_state(self) -> tuple[tuple[FaceColor, ...], ...]:
        """Return a stable snapshot in face-configuration order."""
        return tuple(face.edge_colors + face.corner_colors for face in self._faces)

    def restore_sticker_state(self, state: tuple[tuple[FaceColor, ...], ...]) -> None:
        """Replace every movable sticker from a validated stable snapshot."""
        if not isinstance(state, tuple) or len(state) != len(self._faces):
            raise ValueError(f"board state must contain exactly {len(self._faces)} faces")
        if any(not isinstance(face_state, tuple) or len(face_state) != 12 for face_state in state):
            raise ValueError("each saved face must contain exactly 12 sticker colors")
        if any(not isinstance(color, FaceColor) for face_state in state for color in face_state):
            raise TypeError("every saved sticker must be a FaceColor")

        for face, face_state in zip(self._faces, state, strict=True):
            face.edge_colors = face_state[:6]
            face.corner_colors = face_state[6:]


BOARD = PeriodicBoard()
