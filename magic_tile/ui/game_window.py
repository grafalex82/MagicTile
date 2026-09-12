"""Pygame window, board rendering, input, and face-turn animation."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from functools import lru_cache

import pygame
import pygame.gfxdraw

from magic_tile.domain import (
    BOARD,
    Face,
    FaceColor,
    HexCoordinate,
    PeriodicBoard,
    TurnDirection,
)
from magic_tile.input import TurnCommand, TurnHistory
from magic_tile.persistence import Settings
from magic_tile.ui.camera import Camera
from magic_tile.ui.hex_grid import (
    HEX_HEIGHT,
    hex_at_point,
    hex_center,
    hex_vertices,
    visible_hexes,
)
from magic_tile.ui.turn_animation import TurnAnimation

WINDOW_SIZE = (1280, 800)
WINDOW_TITLE = "MagicTile"

BACKGROUND = pygame.Color("#000000")
GRID_COLOR = pygame.Color("#000000")
GRID_WIDTH = 10
PIECE_GRID_WIDTH = 3
TURN_GUIDE_HIGHLIGHT_COLOR = pygame.Color("#ff4040")
TURN_GUIDE_HIGHLIGHT_WIDTH = 2
# The hover indicator reaches beyond every corner and into the moving ring.
TURN_GUIDE_DIAMETER_SCALE = 1.55
# A left-button movement must pass this distance on either screen axis before
# it becomes a camera drag instead of a face turn.
PAN_START_DISTANCE_PX = 5


def _left_drag_started(
    button_down_at: tuple[int, int], current_position: tuple[int, int]
) -> bool:
    """Return whether a left-button gesture has become a camera drag."""
    return any(
        abs(current - initial) > PAN_START_DISTANCE_PX
        for initial, current in zip(button_down_at, current_position, strict=True)
    )


@dataclass(slots=True)
class _TurnRenderCache:
    """Screen-space data reused while one logical face is turning.

    One logical face occurs at several coordinates on the periodic board, so a
    each turning face is mapped to every visible coordinate resolving to that
    object. ``centers`` stores the face reference with each destination.

    ``key`` maps the cached data to the viewport state in which it was created:
    ``(surface_size, camera_offset, zoom)``. A resize, pan, or zoom produces a
    different key and forces the background and centers to be calculated again.

    ``background`` is the complete, non-animated board image for that viewport.
    It is restored before every animation frame so pixels drawn during the
    preceding frame cannot remain on screen.
    """

    # ((viewport width, height), (camera x, y), camera zoom)
    key: tuple[tuple[int, int], tuple[float, float], float]
    # Static full-window image matching ``key``.
    background: pygame.Surface
    # Logical face object and screen center for every animated occurrence.
    centers: tuple[tuple[Face, tuple[int, int]], ...]


@dataclass(slots=True)
class _CurvedFaceGeometry:
    """Precomputed masks and strokes used to render one static face.

    The geometry is built at twice the requested resolution for antialiasing;
    all masks and ``boundaries`` therefore use the high-resolution ``size``.
    After the masks have been filled with model colors, the composed surface is
    downscaled to ``final_size`` for display.

    ``hex_mask`` maps to the complete hexagonal cell and supplies its base,
    center color. ``edge_masks[i]`` maps to the part of that hexagon covered by
    exactly neighboring circle ``i``. ``corner_masks[i]`` maps to the part
    covered by neighboring circles ``i`` and ``(i + 1) % 6``. These indices are
    the same indices used by ``Face.edge_colors`` and ``Face.corner_colors``.

    ``boundaries`` contains only the transparent overlay of six circular
    dividing arcs and the outer hexagon border. It is drawn after all color
    masks, keeping line widths and joins independent of the fill order.
    """

    # High-resolution (width, height), including padding for boundary strokes.
    size: tuple[int, int]
    # Display size after the supersampled composition is downscaled.
    final_size: tuple[int, int]
    # Entire hexagonal fill region, initially painted with Face.color.
    hex_mask: pygame.mask.Mask
    # Six single-circle regions, mapped by index to Face.edge_colors.
    edge_masks: tuple[pygame.mask.Mask, ...]
    # Six consecutive-circle intersections, mapped to Face.corner_colors.
    corner_masks: tuple[pygame.mask.Mask, ...]
    # Transparent high-resolution surface containing all dividing lines.
    boundaries: pygame.Surface


@dataclass(slots=True)
class _TurnCellGeometry:
    """Unrotated vector contours for one cell inside a moving turn disk.

    One instance describes either the selected cell or one of its six neighbors.
    Every point is expressed in pixels relative to the selected cell's center,
    which is the rotation origin. Consequently, contours belonging to neighbor
    cells are already offset from that origin. For each animation frame,
    ``_render_turn_frame`` rotates all points by the current angle and then
    translates them to the center of the output surface.

    ``vertices`` is the cell's outer hexagon. ``edges[i]`` is that hexagon
    clipped by neighboring circle ``i``; ``corners[i]`` is clipped by the lens
    formed by circles ``i`` and ``(i + 1) % 6``. The tuple indices map directly
    to ``Face.edge_colors[i]`` and ``Face.corner_colors[i]``. Unlike
    ``_CurvedFaceGeometry``, this structure stores polygon contours rather than
    raster masks because its points must be rotated afresh on every frame.
    """

    # Six outer-hexagon points in turn-origin coordinates.
    vertices: tuple[tuple[int, int], ...]
    # Six edge-region polygons, in Face.edge_colors slot order.
    edges: tuple[tuple[tuple[int, int], ...], ...]
    # Six corner-region polygons, in Face.corner_colors slot order.
    corners: tuple[tuple[tuple[int, int], ...], ...]


def draw_board(
    surface: pygame.Surface,
    board: PeriodicBoard = BOARD,
    camera: Camera | None = None,
    hovered_coordinate: HexCoordinate | None = None,
    animation: TurnAnimation | None = None,
    now: float | None = None,
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

    piece_width = max(1, round(PIECE_GRID_WIDTH * zoom))
    cache_key = (surface.get_size(), offset, zoom)
    cache = animation.render_cache if animation is not None else None
    if isinstance(cache, _TurnRenderCache) and cache.key == cache_key:
        surface.blit(cache.background, (0, 0))
    else:
        _draw_faces(surface, board, visible, hex_height, zoom, piece_width)

    if animation is not None:
        _draw_turn_animation(
            surface,
            board,
            visible,
            camera,
            animation,
            time.monotonic() if now is None else now,
        )

    # Keep the solid outline above the rotating layer. During a turn it follows
    # the selected logical face rather than the current cursor position.
    guide_radius = round(hex_height * TURN_GUIDE_DIAMETER_SCALE / 2)
    highlighted_faces = ()
    if animation is not None:
        highlighted_faces = animation.turning_faces
    elif hovered_coordinate is not None:
        highlighted_faces = (board.face_at(hovered_coordinate),)

    if highlighted_faces:
        # pygame draws a circle's stroke inward from its nominal radius.
        # Place the highlight on the middle of that dividing stroke rather
        # than on its outer boundary.
        highlight_radius = round(
            guide_radius
            + (TURN_GUIDE_HIGHLIGHT_WIDTH - 1) / 2
        )
        for q, r, center in visible:
            if board.face_at(HexCoordinate(q, r)) in highlighted_faces:
                pygame.draw.circle(
                    surface,
                    TURN_GUIDE_HIGHLIGHT_COLOR,
                    (round(center[0]), round(center[1])),
                    highlight_radius,
                    width=TURN_GUIDE_HIGHLIGHT_WIDTH,
                )


def _draw_faces(
    surface: pygame.Surface,
    board: PeriodicBoard,
    visible: list[tuple[int, int, tuple[float, float]]],
    hex_height: float,
    zoom: float,
    piece_width: int,
    color_overrides: dict[tuple[Face, str, int], FaceColor] | None = None,
) -> None:
    """Draw complete faces from circle-intersection piece geometry."""
    overrides = color_overrides or {}
    for q, r, center in visible:
        face = board.face_at(HexCoordinate(q, r))
        edge_colors = tuple(
            overrides.get((face, "edge", index), color)
            for index, color in enumerate(face.edge_colors)
        )
        corner_colors = tuple(
            overrides.get((face, "corner", index), color)
            for index, color in enumerate(face.corner_colors)
        )
        face_surface = _render_curved_face(
            max(1, round(hex_height)),
            face.color,
            edge_colors,
            corner_colors,
            piece_width,
            max(1, round(GRID_WIDTH * zoom)),
        )
        surface.blit(
            face_surface,
            face_surface.get_rect(center=(round(center[0]), round(center[1]))),
        )


@lru_cache(maxsize=256)
def _render_curved_face(
    height: int,
    center_color: FaceColor,
    edge_colors: tuple[FaceColor, ...],
    corner_colors: tuple[FaceColor, ...],
    piece_width: int,
    grid_width: int,
) -> pygame.Surface:
    """Render one face whose pieces are bounded by neighboring circles."""
    geometry = _curved_face_geometry(height, piece_width, grid_width)
    rendered = pygame.Surface(geometry.size, pygame.SRCALPHA)
    _blit_mask_color(rendered, geometry.hex_mask, center_color)
    for mask, color in zip(geometry.edge_masks, edge_colors):
        _blit_mask_color(rendered, mask, color)
    for mask, color in zip(geometry.corner_masks, corner_colors):
        _blit_mask_color(rendered, mask, color)
    rendered.blit(geometry.boundaries, (0, 0))
    return pygame.transform.smoothscale(rendered, geometry.final_size)


@lru_cache(maxsize=32)
def _curved_face_geometry(
    height: int, piece_width: int, grid_width: int
) -> _CurvedFaceGeometry:
    """Build circle-intersection masks once for a size and line width."""
    supersampling = 2
    render_height = height * supersampling
    render_width = round(2 * render_height / 3**0.5)
    padding = grid_width * supersampling + 4
    size = (render_width + 2 * padding, render_height + 2 * padding)
    center = (size[0] // 2, size[1] // 2)
    vertices = hex_vertices(center, render_height)

    hex_alpha = pygame.Surface(size, pygame.SRCALPHA)
    pygame.draw.polygon(hex_alpha, (255, 255, 255, 255), vertices)
    hex_mask = pygame.mask.from_surface(hex_alpha)

    radius = round(render_height * TURN_GUIDE_DIAMETER_SCALE / 2)
    circle_masks: list[pygame.mask.Mask] = []
    circle_centers: list[tuple[int, int]] = []
    for dq, dr in board_directions():
        offset_x, offset_y = hex_center(dq, dr, render_height)
        circle_center = (round(center[0] + offset_x), round(center[1] + offset_y))
        circle_centers.append(circle_center)
        circle_alpha = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.circle(
            circle_alpha,
            (255, 255, 255, 255),
            circle_center,
            radius,
        )
        circle_masks.append(pygame.mask.from_surface(circle_alpha))

    # Exactly one neighboring circle identifies an edge region. Intersections
    # of two consecutive circles identify corner regions.
    edge_masks: list[pygame.mask.Mask] = []
    for index, circle_mask in enumerate(circle_masks):
        edge_mask = circle_mask.overlap_mask(hex_mask, (0, 0))
        for other_index, other_mask in enumerate(circle_masks):
            if other_index != index:
                edge_mask.erase(other_mask, (0, 0))
        edge_masks.append(edge_mask)

    corner_masks: list[pygame.mask.Mask] = []
    for index, first_mask in enumerate(circle_masks):
        second_mask = circle_masks[(index + 1) % 6]
        corner_mask = first_mask.overlap_mask(second_mask, (0, 0))
        corner_mask = corner_mask.overlap_mask(hex_mask, (0, 0))
        corner_masks.append(corner_mask)

    # Every internal boundary is an actual circle arc. Draw the six defining
    # circumferences and clip them to the outer hexagonal cell.
    boundaries = pygame.Surface(size, pygame.SRCALPHA)
    boundary_width = max(1, piece_width * supersampling)
    # pygame.draw.circle grows its stroke inward. Increase its nominal radius
    # so the stroke center coincides with the geometric circle used by fills
    # and by the procedural animation.
    centered_boundary_radius = round(radius + (boundary_width - 1) / 2)
    for circle_center in circle_centers:
        pygame.draw.circle(
            boundaries,
            GRID_COLOR,
            circle_center,
            centered_boundary_radius,
            width=boundary_width,
        )
    boundaries.blit(hex_alpha, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    pygame.draw.polygon(
        boundaries,
        GRID_COLOR,
        vertices,
        width=max(1, grid_width * supersampling),
    )

    final_size = (
        max(1, round(size[0] / supersampling)),
        max(1, round(size[1] / supersampling)),
    )
    return _CurvedFaceGeometry(
        size,
        final_size,
        hex_mask,
        tuple(edge_masks),
        tuple(corner_masks),
        boundaries,
    )


def _blit_mask_color(
    surface: pygame.Surface, mask: pygame.mask.Mask, color: FaceColor
) -> None:
    """Fill one precomputed geometric mask with a model color."""
    mask.to_surface(
        surface=surface,
        setcolor=(*color.rgb, 255),
        unsetcolor=None,
    )


def board_directions() -> tuple[tuple[int, int], ...]:
    """Expose the model's shared slot order to cached rendering."""
    return PeriodicBoard.NEIGHBOUR_DIRECTIONS


def _draw_turn_animation(
    surface: pygame.Surface,
    board: PeriodicBoard,
    visible: list[tuple[int, int, tuple[float, float]]],
    camera: Camera | None,
    animation: TurnAnimation,
    now: float,
) -> None:
    """Rotate anti-aliased circular snapshots of every matching face copy."""
    offset = camera.offset if camera is not None else (0.0, 0.0)
    zoom = camera.zoom if camera is not None else 1.0
    radius = _turn_circle_radius(zoom)
    cache_key = (surface.get_size(), offset, zoom)
    cache = animation.render_cache
    if not isinstance(cache, _TurnRenderCache) or cache.key != cache_key:
        cache = _prepare_turn_cache(
            surface,
            board,
            visible,
            animation,
            cache_key,
        )
        animation.render_cache = cache

    render_zoom = max(1.0, zoom)
    source_radius = _turn_circle_radius(render_zoom)
    turn_frames: dict[Face, pygame.Surface] = {}
    for face, turn_center in cache.centers:
        turn_frame = turn_frames.get(face)
        if turn_frame is None:
            turn_frame = _render_turn_frame(
                animation,
                face,
                animation.angle_degrees(now),
                render_zoom,
            )
            turn_frame = _scale_turn_frame(turn_frame, source_radius, radius)
            turn_frames[face] = turn_frame
        surface.blit(turn_frame, turn_frame.get_rect(center=turn_center))


def _prepare_turn_cache(
    surface: pygame.Surface,
    board: PeriodicBoard,
    visible: list[tuple[int, int, tuple[float, float]]],
    animation: TurnAnimation,
    cache_key: tuple[tuple[int, int], tuple[float, float], float],
) -> _TurnRenderCache:
    """Collect periodic target centers and retain the completed background."""
    turning_faces = set(animation.turning_faces)
    centers: list[tuple[Face, tuple[int, int]]] = []
    for q, r, turn_center in visible:
        face = board.face_at(HexCoordinate(q, r))
        if face not in turning_faces:
            continue
        centers.append(
            (face, (round(turn_center[0]), round(turn_center[1])))
        )
    return _TurnRenderCache(cache_key, surface.copy(), tuple(centers))


def _render_turn_frame(
    animation: TurnAnimation,
    focus: Face,
    angle_degrees: float,
    zoom: float,
) -> pygame.Surface:
    """Procedurally rasterize one frame from analytic circle intersections."""
    height = max(1, round(HEX_HEIGHT * zoom))
    piece_width = max(1, round(PIECE_GRID_WIDTH * zoom))
    grid_width = max(1, round(GRID_WIDTH * zoom))
    boundary_radius = round(height * TURN_GUIDE_DIAMETER_SCALE / 2)
    turn_radius = _turn_circle_radius(zoom)
    padding = 3
    size = 2 * (turn_radius + padding) + 1
    turn_center = (size // 2, size // 2)
    rendered = pygame.Surface((size, size), pygame.SRCALPHA)

    faces = (focus,) + focus.neighbors
    angle = math.radians(angle_degrees)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    # 96 segments keep chord error below a quarter pixel even at 250% zoom.
    cells = _turn_vector_geometry(height)

    def rotated_point(point: tuple[int, int]) -> tuple[int, int]:
        return (
            round(
                turn_center[0]
                + point[0] * cosine
                - point[1] * sine
            ),
            round(
                turn_center[1]
                + point[0] * sine
                + point[1] * cosine
            ),
        )

    for face, cell in zip(faces, cells):
        vertices = tuple(rotated_point(point) for point in cell.vertices)

        edge_colors = tuple(
            animation.source_colors.get(
                (face, "edge", index), color
            )
            for index, color in enumerate(face.edge_colors)
        )
        corner_colors = tuple(
            animation.source_colors.get(
                (face, "corner", index), color
            )
            for index, color in enumerate(face.corner_colors)
        )
        pygame.draw.polygon(rendered, face.color.rgb, vertices)

        edge_polygons: list[list[tuple[int, int]]] = []
        for index, edge in enumerate(cell.edges):
            edge_polygon = [rotated_point(point) for point in edge]
            edge_polygons.append(edge_polygon)
            if len(edge_polygon) >= 3:
                pygame.draw.polygon(rendered, edge_colors[index].rgb, edge_polygon)

        corner_polygons: list[list[tuple[int, int]]] = []
        for index, corner in enumerate(cell.corners):
            corner_polygon = [rotated_point(point) for point in corner]
            corner_polygons.append(corner_polygon)
            if len(corner_polygon) >= 3:
                pygame.draw.polygon(
                    rendered, corner_colors[index].rgb, corner_polygon
                )

        for polygon in edge_polygons + corner_polygons:
            if len(polygon) >= 3:
                pygame.draw.lines(
                    rendered,
                    GRID_COLOR,
                    True,
                    polygon,
                    width=piece_width,
                )
        pygame.draw.polygon(
            rendered,
            GRID_COLOR,
            vertices,
            width=grid_width,
        )

    rendered.blit(
        _circular_alpha_mask(turn_radius),
        (0, 0),
        special_flags=pygame.BLEND_RGBA_MULT,
    )
    return rendered


def _turn_circle_radius(zoom: float) -> int:
    """Return the moving radius at the center of its dividing stroke."""
    height = HEX_HEIGHT * zoom
    return round(height * TURN_GUIDE_DIAMETER_SCALE / 2)


def _scale_turn_frame(
    frame: pygame.Surface,
    source_radius: int,
    target_radius: int,
) -> pygame.Surface:
    """Scale disk contents by radius, independently of transparent padding."""
    target_size = _circular_alpha_mask(target_radius).get_size()
    if source_radius == target_radius and frame.get_size() == target_size:
        return frame

    scale = target_radius / source_radius
    scaled_size = (
        max(1, round(frame.get_width() * scale)),
        max(1, round(frame.get_height() * scale)),
    )
    scaled = pygame.transform.smoothscale(frame, scaled_size)
    result = pygame.Surface(target_size, pygame.SRCALPHA)
    result.blit(scaled, scaled.get_rect(center=result.get_rect().center))
    result.blit(
        _circular_alpha_mask(target_radius),
        (0, 0),
        special_flags=pygame.BLEND_RGBA_MULT,
    )
    return result


@lru_cache(maxsize=32)
def _turn_vector_geometry(height: int) -> tuple[_TurnCellGeometry, ...]:
    """Build reusable analytic piece contours for the seven moving cells."""
    boundary_radius = round(height * TURN_GUIDE_DIAMETER_SCALE / 2)
    # Chord deviation stays below half a pixel while keeping high-zoom frame
    # construction within a 60 Hz budget.
    circle_segments = min(64, max(36, round(boundary_radius * 0.25)))
    coordinates = ((0, 0),) + PeriodicBoard.NEIGHBOUR_DIRECTIONS
    cells: list[_TurnCellGeometry] = []
    for q, r in coordinates:
        center = hex_center(q, r, height)
        vertices = tuple(hex_vertices(center, height))
        neighbor_centers = tuple(
            (
                round(hex_center(q + dq, r + dr, height)[0]),
                round(hex_center(q + dq, r + dr, height)[1]),
            )
            for dq, dr in PeriodicBoard.NEIGHBOUR_DIRECTIONS
        )
        edges = tuple(
            tuple(
                _clip_convex_polygon(
                    _circle_polygon(
                        neighbor_center,
                        boundary_radius,
                        circle_segments,
                    ),
                    vertices,
                )
            )
            for neighbor_center in neighbor_centers
        )
        corners = tuple(
            tuple(
                _clip_convex_polygon(
                    _circle_lens_polygon(
                        neighbor_centers[index],
                        neighbor_centers[(index + 1) % 6],
                        boundary_radius,
                        circle_segments // 3,
                    ),
                    vertices,
                )
            )
            for index in range(6)
        )
        cells.append(_TurnCellGeometry(vertices, edges, corners))
    return tuple(cells)


def _circle_polygon(
    center: tuple[int, int], radius: int, segments: int
) -> list[tuple[int, int]]:
    """Approximate a circle densely enough for a smooth filled boundary."""
    return [
        (
            round(center[0] + radius * math.cos(2 * math.pi * index / segments)),
            round(center[1] + radius * math.sin(2 * math.pi * index / segments)),
        )
        for index in range(segments)
    ]


def _circle_lens_polygon(
    first: tuple[int, int],
    second: tuple[int, int],
    radius: int,
    segments: int,
) -> list[tuple[int, int]]:
    """Return the convex lens formed by two equal intersecting circles."""
    delta_x = second[0] - first[0]
    delta_y = second[1] - first[1]
    distance = math.hypot(delta_x, delta_y)
    if distance == 0 or distance >= 2 * radius:
        return []
    half_angle = math.acos(distance / (2 * radius))
    first_direction = math.atan2(delta_y, delta_x)
    second_direction = math.atan2(-delta_y, -delta_x)
    points: list[tuple[int, int]] = []
    for center, direction in (
        (first, first_direction),
        (second, second_direction),
    ):
        for index in range(segments + 1):
            arc_angle = direction - half_angle + 2 * half_angle * index / segments
            points.append(
                (
                    round(center[0] + radius * math.cos(arc_angle)),
                    round(center[1] + radius * math.sin(arc_angle)),
                )
            )
    midpoint = ((first[0] + second[0]) / 2, (first[1] + second[1]) / 2)
    return sorted(
        set(points),
        key=lambda point: math.atan2(
            point[1] - midpoint[1], point[0] - midpoint[0]
        ),
    )


def _clip_convex_polygon(
    subject: list[tuple[int, int]],
    clip: tuple[tuple[int, int], ...],
) -> list[tuple[int, int]]:
    """Clip a polygon to a clockwise convex polygon."""
    output = [(float(x), float(y)) for x, y in subject]
    for clip_start, clip_end in zip(clip, clip[1:] + clip[:1]):
        input_points = output
        output = []
        if not input_points:
            break

        def inside(point: tuple[float, float]) -> bool:
            return (
                (clip_end[0] - clip_start[0]) * (point[1] - clip_start[1])
                - (clip_end[1] - clip_start[1]) * (point[0] - clip_start[0])
            ) >= 0

        def intersection(
            first: tuple[float, float], second: tuple[float, float]
        ) -> tuple[float, float]:
            segment_x = second[0] - first[0]
            segment_y = second[1] - first[1]
            clip_x = clip_end[0] - clip_start[0]
            clip_y = clip_end[1] - clip_start[1]
            denominator = segment_x * clip_y - segment_y * clip_x
            if denominator == 0:
                return second
            amount = (
                (clip_start[0] - first[0]) * clip_y
                - (clip_start[1] - first[1]) * clip_x
            ) / denominator
            return first[0] + amount * segment_x, first[1] + amount * segment_y

        previous = input_points[-1]
        for current in input_points:
            if inside(current):
                if not inside(previous):
                    output.append(intersection(previous, current))
                output.append(current)
            elif inside(previous):
                output.append(intersection(previous, current))
            previous = current
    return [(round(x), round(y)) for x, y in output]


@lru_cache(maxsize=32)
def _circular_alpha_mask(radius: int, padding: int = 3) -> pygame.Surface:
    """Return a reusable smooth mask with no opaque pixels outside the disk."""
    size = 2 * (radius + padding) + 1
    circle_center = radius + padding
    mask = pygame.Surface((size, size), pygame.SRCALPHA)
    mask.fill((255, 255, 255, 0))
    pygame.gfxdraw.filled_circle(
        mask,
        circle_center,
        circle_center,
        radius,
        (255, 255, 255, 255),
    )
    pygame.gfxdraw.aacircle(
        mask,
        circle_center,
        circle_center,
        radius,
        (255, 255, 255, 255),
    )
    return mask


def run(settings: Settings) -> int:
    """Open the main window and run its event/render loop using *settings*."""
    pygame.init()
    try:
        screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
        pygame.display.set_caption(WINDOW_TITLE)
        clock = pygame.time.Clock()
        camera = Camera()
        board = PeriodicBoard()
        turn_history = TurnHistory()
        panning = False
        left_button_down_at: tuple[int, int] | None = None
        animation: TurnAnimation | None = None
        mouse_inside = pygame.mouse.get_focused()
        running = True

        while running:
            now = time.monotonic()
            if animation is not None and animation.is_finished(now):
                if animation.completion_frame_shown:
                    animation = None
                else:
                    # Keep one clamped 60-degree frame before switching to
                    # the separately rasterized final model.
                    animation.completion_frame_shown = True

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.WINDOWLEAVE:
                    mouse_inside = False
                elif event.type == pygame.WINDOWENTER:
                    mouse_inside = True
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                elif animation is not None:
                    # Quit and Escape remain available, but puzzle/camera input
                    # is locked until the half-second turn finishes.
                    continue
                elif event.type == pygame.KEYDOWN:
                    shortcut_modifiers = pygame.KMOD_CTRL | pygame.KMOD_META
                    has_undo_modifier = bool(event.mod & shortcut_modifiers)
                    command: TurnCommand | None = None
                    if has_undo_modifier and event.key == pygame.K_z:
                        if event.mod & pygame.KMOD_SHIFT:
                            command = turn_history.redo()
                        else:
                            command = turn_history.undo()
                    elif has_undo_modifier and event.key == pygame.K_y:
                        command = turn_history.redo()
                    if command is not None:
                        animation = TurnAnimation.begin(
                            board,
                            command.coordinate,
                            command.direction,
                            now,
                            duration_seconds=settings.turn_animation_duration_seconds,
                        )
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    left_button_down_at = event.pos
                    panning = False
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if left_button_down_at is not None and not panning:
                        q, r = hex_at_point(
                            left_button_down_at,
                            height=HEX_HEIGHT * camera.zoom,
                            offset=camera.offset,
                        )
                        command = TurnCommand(
                            HexCoordinate(q, r), TurnDirection.COUNTERCLOCKWISE
                        )
                        turn_history.record(command)
                        animation = TurnAnimation.begin(
                            board,
                            command.coordinate,
                            command.direction,
                            now,
                            duration_seconds=settings.turn_animation_duration_seconds,
                        )
                    left_button_down_at = None
                    panning = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                    q, r = hex_at_point(
                        event.pos,
                        height=HEX_HEIGHT * camera.zoom,
                        offset=camera.offset,
                    )
                    command = TurnCommand(HexCoordinate(q, r), TurnDirection.CLOCKWISE)
                    turn_history.record(command)
                    animation = TurnAnimation.begin(
                        board,
                        command.coordinate,
                        command.direction,
                        now,
                        duration_seconds=settings.turn_animation_duration_seconds,
                    )
                elif event.type == pygame.MOUSEMOTION:
                    mouse_inside = True
                    if left_button_down_at is not None:
                        if panning or _left_drag_started(
                            left_button_down_at, event.pos
                        ):
                            panning = True
                            camera.pan(*event.rel)
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
                board=board,
                camera=camera,
                hovered_coordinate=hovered_coordinate,
                animation=animation,
                now=now,
            )
            pygame.display.flip()
            clock.tick(60)
    finally:
        pygame.quit()

    return 0
