"""Data model for the seven-face periodic hexagonal plane."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum


class FaceColor(Enum):
    """The seven saturated colours used by the reference configuration."""

    # Enum order is the seven-cell periodic pattern indexed by
    # ``(q + 3 * r) % 7``.  Keep it in sync with the reference arrangement.
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

    ``r`` identifies a position along the vertical screen axis. ``q`` runs
    diagonally from upper-left to lower-right, at 30 degrees to the horizontal
    edge of the window. The third cube-coordinate component is not stored
    because it can always be calculated as ``s = -q - r``.

    Axial directions around the origin::

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

    The origin is ``HexCoordinate(0, 0)``. Its six neighbours are ``(1, 0)``,
    ``(1, -1)``, ``(0, -1)``, ``(-1, 0)``, ``(-1, 1)``, and ``(0, 1)``.
    """

    q: int
    r: int


@dataclass(slots=True)
class Face:
    """One board face and the colors currently visible in its twelve slots.

    State lives directly in color slots. This avoids incorrectly assuming that
    a physical piece always presents the same color when it later returns to a
    position with a different orientation.
    """

    color: FaceColor
    edge_colors: tuple[FaceColor, ...] = ()
    corner_colors: tuple[FaceColor, ...] = ()

    def __post_init__(self) -> None:
        if not self.edge_colors:
            self.edge_colors = (self.color,) * 6
        if not self.corner_colors:
            self.corner_colors = (self.color,) * 6
        if len(self.edge_colors) != 6:
            raise ValueError("a face must contain six edge colors")
        if len(self.corner_colors) != 6:
            raise ValueError("a face must contain six corner colors")


@dataclass(frozen=True, slots=True)
class FaceNeighborhood:
    """A focused face and the six faces geometrically surrounding it."""

    focus: Face
    neighbors: tuple[Face, ...]

    def __post_init__(self) -> None:
        if len(self.neighbors) != 6:
            raise ValueError("a face neighborhood must contain six neighbors")


class PeriodicBoard:
    """Infinite hexagonal plane backed by seven repeating logical faces.

    Faces do not store persistent references to adjacent faces or shared piece
    objects.  Adjacency is calculated from the six axial offsets in
    ``NEIGHBOUR_DIRECTIONS`` whenever it is needed.  Neighbor and face-slot
    indices use the same cyclic order.  For neighbor ``i``, the strip adjoining
    the selected face consists of edge ``(i + 3) % 6`` and corners
    ``(i + 2) % 6`` and ``(i + 3) % 6``.  A turn moves that whole strip to the
    next or previous neighbor while preserving the relative order of its
    colors.
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
        """Build the solved seven-face periodic sticker region."""

        # FaceColor declaration order is the periodic palette.  A coordinate's
        # palette index is calculated by ``(q + 3 * r) % 7`` in ``face_at``.
        palette = tuple(FaceColor)

        # A face owns only the colors visible in its six edge and six corner
        # slots. Its own fixed color identifies the face; connections between
        # faces are expressed by the move permutation rather than persistent
        # shared piece objects.
        self._faces = tuple(Face(color=color) for color in palette)

    @property
    def faces(self) -> tuple[Face, ...]:
        """Return the seven logical faces in palette order."""
        return self._faces

    def face_at(self, coordinate: HexCoordinate) -> Face:
        """Return the logical face repeated at an axial coordinate."""
        index = (coordinate.q + 3 * coordinate.r) % len(self._faces)
        return self._faces[index]

    def neighborhood_at(self, coordinate: HexCoordinate) -> FaceNeighborhood:
        """Return a face and the six differently coloured faces around it."""
        neighbors = tuple(
            self.face_at(HexCoordinate(coordinate.q + dq, coordinate.r + dr))
            for dq, dr in self.NEIGHBOUR_DIRECTIONS
        )
        return FaceNeighborhood(self.face_at(coordinate), neighbors)

    def face_for_color(self, color: FaceColor) -> Face:
        """Return the unique logical face identified by ``color``."""
        return self._faces[tuple(FaceColor).index(color)]

    def turn(self, color: FaceColor, direction: TurnDirection) -> None:
        """Apply an exact 60-degree permutation around one logical face.

        Slot indices follow ``NEIGHBOUR_DIRECTIONS``.  In addition to the
        twelve slots on the selected face, a move carries the inward-facing
        edge and its two endpoint corners from every neighbor to the next
        neighbor.  All assignments are based on one snapshot, so a move is
        atomic and cannot overwrite a value that has not moved yet.
        """
        if not isinstance(direction, TurnDirection):
            raise TypeError("direction must be a TurnDirection")

        # Neighbor and slot indices run around a face in the same cyclic order.
        # Therefore +1 is one counter-clockwise sector and -1 is clockwise.
        step = int(direction)
        neighbors = self._neighbor_faces(color)

        # Read every moved value from a stable snapshot.  The mutable copies
        # collect the complete result and are committed only after the move is
        # calculated, preventing an early assignment from corrupting a later one.
        old_edges = {face.color: face.edge_colors for face in self._faces}
        old_corners = {face.color: face.corner_colors for face in self._faces}
        new_edges = {face.color: list(face.edge_colors) for face in self._faces}
        new_corners = {face.color: list(face.corner_colors) for face in self._faces}

        for source_index in range(6):
            destination_index = (source_index + step) % 6

            # Rotate the selected face's own edge and corner rings by one slot.
            new_edges[color][destination_index] = old_edges[color][source_index]
            new_corners[color][destination_index] = old_corners[color][source_index]

            # Move the strip adjoining the selected face from one neighboring
            # face to the next.  The adjoining edge is opposite the neighbor's
            # position around the selected face, hence the three-slot offset.
            source_neighbor = neighbors[source_index]
            destination_neighbor = neighbors[destination_index]
            source_color = source_neighbor.color
            destination_color = destination_neighbor.color

            source_edge = (source_index + 3) % 6
            destination_edge = (destination_index + 3) % 6
            new_edges[destination_color][destination_edge] = old_edges[source_color][
                source_edge
            ]

            # The two corners at the ends of that adjoining edge travel with
            # the same strip and keep their relative order and orientation.
            for source_corner in ((source_index + 2) % 6, (source_index + 3) % 6):
                destination_corner = (source_corner + step) % 6
                new_corners[destination_color][destination_corner] = old_corners[
                    source_color
                ][source_corner]

        # Publish the fully calculated state atomically, restoring the immutable
        # tuple representation used by Face.
        for face in self._faces:
            face_color = face.color
            face.edge_colors = tuple(new_edges[face_color])
            face.corner_colors = tuple(new_corners[face_color])

    def affected_slots(
        self, color: FaceColor
    ) -> frozenset[tuple[FaceColor, str, int]]:
        """Return every visible color slot moved by a turn of ``color``.

        Each slot is represented by ``(face_color, kind, index)``:

        * ``face_color`` identifies the logical face that owns the slot;
        * ``kind`` is either ``"edge"`` or ``"corner"``;
        * ``index`` is the slot's position from 0 through 5, in the cyclic order
          defined by ``NEIGHBOUR_DIRECTIONS``.

        The result contains all six edges and six corners of the selected face.
        For each neighboring face ``i``, it also contains the inward-facing edge
        ``(i + 3) % 6`` and that edge's endpoint corners ``(i + 2) % 6`` and
        ``(i + 3) % 6``. Thus a move always affects 30 visible slots: 12 on the
        selected face and 3 on each of its 6 neighbors.

        A ``frozenset`` is returned because a slot must occur only once, callers
        must not modify the collection, and the order in which animation colors
        are captured is irrelevant. Its iteration order is intentionally not
        defined.

        Example::

            >>> board = PeriodicBoard()
            >>> slots = board.affected_slots(FaceColor.WHITE)
            >>> len(slots)
            30
            >>> (FaceColor.WHITE, "edge", 0) in slots
            True
            >>> (FaceColor.CYAN, "edge", 3) in slots
            True
            >>> (FaceColor.CYAN, "corner", 2) in slots
            True
        """
        slots: set[tuple[FaceColor, str, int]] = set()
        neighbors = self._neighbor_faces(color)
        for index in range(6):
            slots.add((color, "edge", index))
            slots.add((color, "corner", index))
            neighbor_color = neighbors[index].color
            slots.add((neighbor_color, "edge", (index + 3) % 6))
            slots.add((neighbor_color, "corner", (index + 2) % 6))
            slots.add((neighbor_color, "corner", (index + 3) % 6))
        return frozenset(slots)

    def sticker_state(self) -> tuple[tuple[FaceColor, ...], ...]:
        """Return an immutable snapshot of every movable color slot.

        The outer tuple contains one entry per logical face, ordered exactly like
        ``tuple(FaceColor)``. For a face at index ``face_index``, the corresponding
        inner tuple contains 12 colors in this order:

        ``state[face_index][0:6]``
            The face's six edge colors.

        ``state[face_index][6:12]``
            The face's six corner colors.

        The fixed ``Face.color`` is not repeated in the snapshot because it never
        changes and is already implied by the outer tuple's index. The method
        concatenates each face's edge and corner tuples and then collects those
        seven results into an outer tuple. Consequently, the returned value can
        be safely retained and compared with a later state without being changed
        by subsequent turns.

        Example::

            >>> board = PeriodicBoard()
            >>> state = board.sticker_state()
            >>> len(state)
            7
            >>> all(len(face_state) == 12 for face_state in state)
            True
            >>> white_index = tuple(FaceColor).index(FaceColor.WHITE)
            >>> state[white_index][0:6] == (FaceColor.WHITE,) * 6
            True
            >>> state[white_index][6:12] == (FaceColor.WHITE,) * 6
            True
        """
        return tuple(
            face.edge_colors + face.corner_colors for face in self._faces
        )

    def _neighbor_faces(self, color: FaceColor) -> tuple[Face, ...]:
        """Return the six logical neighbors of a face in slot order.

        ``face_at`` maps an axial coordinate to palette index
        ``(q + 3 * r) % 7``.  Moving by one neighbor offset ``(dq, dr)`` changes
        that index by ``dq + 3 * dr``.  Therefore a face whose palette index is
        ``color_index`` has the neighbor index
        ``(color_index + dq + 3 * dr) % 7``.  This calculation is independent
        of which periodic occurrence of the face is used as the starting point.
        """
        palette = tuple(FaceColor)
        color_index = palette.index(color)
        return tuple(
            self._faces[(color_index + dq + 3 * dr) % len(self._faces)]
            for dq, dr in self.NEIGHBOUR_DIRECTIONS
        )


BOARD = PeriodicBoard()
