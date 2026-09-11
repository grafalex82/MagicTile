"""Data model for the seven-face periodic hexagonal plane."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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


@dataclass(frozen=True, slots=True)
class Center:
    """Fixed center element that identifies a face by its colour."""

    color: FaceColor


@dataclass(frozen=True, slots=True)
class Edge:
    """Edge element shared by two adjacent faces."""

    colors: tuple[FaceColor, FaceColor]

    def __post_init__(self) -> None:
        if len(set(self.colors)) != 2:
            raise ValueError("an edge must contain two different colors")


@dataclass(frozen=True, slots=True)
class Corner:
    """Corner element shared by three mutually adjacent faces."""

    colors: tuple[FaceColor, FaceColor, FaceColor]

    def __post_init__(self) -> None:
        if len(set(self.colors)) != 3:
            raise ValueError("a corner must contain three different colors")


@dataclass(frozen=True, slots=True)
class Face:
    """One board face: a center, six edges, and six corners."""

    center: Center
    edges: tuple[Edge, ...]
    corners: tuple[Corner, ...]

    def __post_init__(self) -> None:
        if len(self.edges) != 6:
            raise ValueError("a face must contain six edges")
        if len(self.corners) != 6:
            raise ValueError("a face must contain six corners")


@dataclass(frozen=True, slots=True)
class FaceNeighborhood:
    """A focused face and the six faces geometrically surrounding it."""

    focus: Face
    neighbors: tuple[Face, ...]

    def __post_init__(self) -> None:
        if len(self.neighbors) != 6:
            raise ValueError("a face neighborhood must contain six neighbors")


class PeriodicBoard:
    """Infinite hexagonal plane backed by seven repeating logical faces."""

    _NEIGHBOUR_DIRECTIONS = (
        (1, 0),
        (1, -1),
        (0, -1),
        (-1, 0),
        (-1, 1),
        (0, 1),
    )

    def __init__(self) -> None:
        """Build the solved seven-face periodic region and its shared pieces."""

        # FaceColor declaration order is the periodic palette.  A coordinate's
        # palette index is calculated by ``(q + 3 * r) % 7`` in ``face_at``.
        palette = tuple(FaceColor)

        # Every logical face has exactly one fixed center.  Centers identify
        # faces even after movable edge and corner pieces are later permuted.
        centers = {color: Center(color) for color in palette}

        # Keys are unordered color sets because an Edge(WHITE, CYAN) is the
        # same physical piece when reached from either the white or cyan face.
        # Corner identity works the same way for its three adjacent faces.
        edges: dict[frozenset[FaceColor], Edge] = {}
        corners: dict[frozenset[FaceColor], Corner] = {}

        # Remember the six neighboring colors of each center in the cyclic
        # order defined by _NEIGHBOUR_DIRECTIONS.  The order is later reused
        # to place edges and corners consistently around each Face.
        neighbor_colors_by_color: dict[FaceColor, tuple[FaceColor, ...]] = {}
        for color_index, color in enumerate(palette):
            # Moving by (dq, dr) changes the periodic palette index by
            # dq + 3*dr.  Consequently every center sees all six other colors.
            neighbor_colors = tuple(
                palette[(color_index + dq + 3 * dr) % len(palette)]
                for dq, dr in self._NEIGHBOUR_DIRECTIONS
            )
            neighbor_colors_by_color[color] = neighbor_colors

            # Create each shared edge only once.  setdefault returns the
            # already-created object when the opposite face reaches it later.
            for neighbor_color in neighbor_colors:
                key = frozenset((color, neighbor_color))
                edges.setdefault(key, Edge(self._ordered_colors(key, palette)))

            # Two consecutive neighbors and the current center meet at one
            # corner.  Appending the first neighbor closes the six-item ring.
            adjacent_pairs = zip(
                neighbor_colors,
                neighbor_colors[1:] + neighbor_colors[:1],
            )
            for first_color, second_color in adjacent_pairs:
                key = frozenset((color, first_color, second_color))
                corners.setdefault(key, Corner(self._ordered_colors(key, palette)))

        # Assemble every Face from its center and references to the shared
        # pieces.  Adjacent faces therefore contain the exact same Edge or
        # Corner object rather than independent copies of that piece.
        self._faces = tuple(
            Face(
                center=centers[color],
                edges=tuple(
                    edges[frozenset((color, neighbor_color))]
                    for neighbor_color in neighbor_colors_by_color[color]
                ),
                corners=tuple(
                    corners[frozenset((color, first_color, second_color))]
                    for first_color, second_color in zip(
                        neighbor_colors_by_color[color],
                        neighbor_colors_by_color[color][1:]
                        + neighbor_colors_by_color[color][:1],
                    )
                ),
            )
            for color in palette
        )

        # Keep direct collections for future move permutations and persistence.
        # Seven hexagonal faces produce 21 unique edges and 14 unique corners.
        self._edges = tuple(edges.values())
        self._corners = tuple(corners.values())

    @staticmethod
    def _ordered_colors(
        colors: frozenset[FaceColor], palette: tuple[FaceColor, ...]
    ) -> tuple[FaceColor, ...]:
        """Give an otherwise unordered piece identity a stable representation."""
        return tuple(color for color in palette if color in colors)

    @property
    def faces(self) -> tuple[Face, ...]:
        """Return the seven logical faces in palette order."""
        return self._faces

    @property
    def edges(self) -> tuple[Edge, ...]:
        """Return the 21 edge elements in one periodic region."""
        return self._edges

    @property
    def corners(self) -> tuple[Corner, ...]:
        """Return the 14 corner elements in one periodic region."""
        return self._corners

    def face_at(self, coordinate: HexCoordinate) -> Face:
        """Return the logical face repeated at an axial coordinate."""
        index = (coordinate.q + 3 * coordinate.r) % len(self._faces)
        return self._faces[index]

    def neighborhood_at(self, coordinate: HexCoordinate) -> FaceNeighborhood:
        """Return a face and the six differently coloured faces around it."""
        neighbors = tuple(
            self.face_at(HexCoordinate(coordinate.q + dq, coordinate.r + dr))
            for dq, dr in self._NEIGHBOUR_DIRECTIONS
        )
        return FaceNeighborhood(self.face_at(coordinate), neighbors)


BOARD = PeriodicBoard()
