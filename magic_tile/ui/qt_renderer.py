"""QPainter-based rendering for the infinite periodic board."""

from __future__ import annotations

import math
import time
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF

from magic_tile.domain import BOARD, Face, FaceColor, HexCoordinate, PeriodicBoard
from magic_tile.ui.camera import Camera
from magic_tile.ui.hex_grid import HEX_HEIGHT, hex_center, hex_vertices, visible_hexes
from magic_tile.ui.turn_animation import TurnAnimation

BACKGROUND = QColor("#000000")
GRID_COLOR = QColor("#000000")
GRID_WIDTH = 10
PIECE_GRID_WIDTH = 3
TURN_GUIDE_HIGHLIGHT_COLOR = QColor("#ff4040")
TURN_GUIDE_HIGHLIGHT_WIDTH = 2
MACRO_HIGHLIGHT_COLOR = QColor("#37e46f")
MACRO_HIGHLIGHT_WIDTH = 3
PANEL_BACKGROUND = QColor(15, 15, 18, 220)
PANEL_TEXT = QColor("#ffffff")
ERROR_BACKGROUND = QColor(150, 28, 28, 235)
INFO_BACKGROUND = QColor(24, 92, 48, 235)
TURN_GUIDE_DIAMETER_SCALE = 1.55
DIM_COLOR_FACTOR = 0.28


@dataclass(frozen=True, slots=True)
class _CellGeometry:
    vertices: QPolygonF
    edges: tuple[QPolygonF, ...]
    corners: tuple[QPolygonF, ...]
    circle_centers: tuple[tuple[int, int], ...]


_FACE_IMAGE_CACHE: OrderedDict[tuple, QImage] = OrderedDict()
_FACE_IMAGE_CACHE_SIZE = 256


def draw_board(
    painter: QPainter,
    viewport: tuple[int, int],
    board: PeriodicBoard = BOARD,
    camera: Camera | None = None,
    hovered_coordinate: HexCoordinate | None = None,
    animation: TurnAnimation | None = None,
    now: float | None = None,
    macro_face_numbers: dict[Face, int] | None = None,
    static_background: QImage | None = None,
    dim_edges: bool = False,
    dim_corners: bool = False,
) -> None:
    """Draw a complete static or animated frame into an active painter."""
    # Configure high-quality drawing and derive viewport geometry from the camera.
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    offset = camera.offset if camera is not None else (0.0, 0.0)
    zoom = camera.zoom if camera is not None else 1.0
    height = max(1, round(HEX_HEIGHT * zoom))
    visible = list(visible_hexes(viewport, height=HEX_HEIGHT * zoom, offset=offset))

    # Draw or reuse the static board beneath all dynamic layers.
    if static_background is None:
        painter.fillRect(QRectF(0, 0, viewport[0], viewport[1]), BACKGROUND)
        _draw_faces(
            painter,
            board,
            visible,
            height,
            zoom,
            dim_edges=dim_edges,
            dim_corners=dim_corners,
        )
    else:
        painter.drawImage(QPointF(0, 0), static_background)

    # Composite the moving turn disk when a turn is active.
    if animation is not None:
        current = time.monotonic() if now is None else now
        _draw_turn_animation(
            painter,
            board,
            visible,
            animation,
            current,
            height,
            zoom,
            dim_edges=dim_edges,
            dim_corners=dim_corners,
        )

    # Add persistent face numbers used by macro recording and playback.
    guide_radius = round(HEX_HEIGHT * zoom * TURN_GUIDE_DIAMETER_SCALE / 2)
    if macro_face_numbers:
        _draw_macro_markers(painter, board, visible, guide_radius, macro_face_numbers, zoom)

    # Choose logical faces highlighted by animation or pointer hover.
    highlighted: tuple[Face, ...] = ()
    if animation is not None:
        highlighted = animation.turning_faces
    elif hovered_coordinate is not None:
        highlighted = (board.face_at(hovered_coordinate),)

    # Draw the animation seam first, then the red guide above every copy.
    if highlighted:
        if animation is not None:
            # Match the ordinary piece-divider width so starting an animation
            # does not make the circular turn boundary appear thicker.
            seam_width = _piece_grid_width(zoom)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(GRID_COLOR, seam_width))
            highlighted_set = set(highlighted)
            for q, r, center in visible:
                if board.face_at(HexCoordinate(q, r)) in highlighted_set:
                    painter.drawEllipse(QPointF(*center), guide_radius, guide_radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(TURN_GUIDE_HIGHLIGHT_COLOR, TURN_GUIDE_HIGHLIGHT_WIDTH))
        highlighted_set = set(highlighted)
        for q, r, center in visible:
            if board.face_at(HexCoordinate(q, r)) in highlighted_set:
                painter.drawEllipse(QPointF(*center), guide_radius, guide_radius)


def render_board(viewport: tuple[int, int], **kwargs) -> QImage:
    """Render a board to an image for tests, previews, and snapshots."""
    image = QImage(viewport[0], viewport[1], QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(BACKGROUND)
    painter = QPainter(image)
    try:
        draw_board(painter, viewport, **kwargs)
    finally:
        painter.end()
    return image


def render_static_board(
    viewport: tuple[int, int],
    board: PeriodicBoard,
    camera: Camera,
    *,
    dim_edges: bool = False,
    dim_corners: bool = False,
) -> QImage:
    """Render the cacheable board layer without animation or overlays."""
    # Allocate and clear an image matching the current viewport.
    image = QImage(viewport[0], viewport[1], QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(BACKGROUND)
    painter = QPainter(image)
    try:
        # Resolve visible cells and paint only the reusable static layer.
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        height = max(1, round(HEX_HEIGHT * camera.zoom))
        visible = list(visible_hexes(viewport, height=HEX_HEIGHT * camera.zoom, offset=camera.offset))
        _draw_faces(
            painter,
            board,
            visible,
            height,
            camera.zoom,
            dim_edges=dim_edges,
            dim_corners=dim_corners,
        )
    finally:
        # Release the image painter even if rendering fails.
        painter.end()
    return image


def _draw_faces(
    painter,
    board,
    visible,
    height: int,
    zoom: float,
    *,
    dim_edges: bool = False,
    dim_corners: bool = False,
) -> None:
    for q, r, center in visible:
        # Resolve the logical face and reuse its cached raster image.
        occurrence = board.occurrence_at(HexCoordinate(q, r))
        face_image = _render_face_image(
            height,
            occurrence.face,
            zoom,
            occurrence.mirrored,
            dim_edges,
            dim_corners,
        )

        # Center the face image on this periodic screen-space occurrence.
        painter.drawImage(
            QPointF(
                round(center[0]) - face_image.width() // 2,
                round(center[1]) - face_image.height() // 2,
            ),
            face_image,
        )


def _render_face_image(
    height: int,
    face: Face,
    zoom: float,
    mirrored: bool = False,
    dim_edges: bool = False,
    dim_corners: bool = False,
) -> QImage:
    """Render one reusable static face image for all of its periodic copies."""
    # Include current colors in the internal key because Face is mutable.
    cache_key = (
        height,
        face,
        face.color,
        face.edge_colors,
        face.corner_colors,
        zoom,
        mirrored,
        dim_edges,
        dim_corners,
    )
    cached_image = _FACE_IMAGE_CACHE.get(cache_key)
    if cached_image is not None:
        _FACE_IMAGE_CACHE.move_to_end(cache_key)
        return cached_image

    # Calculate an odd-sized canvas that includes the complete outer stroke.
    geometry = _cell_geometries(height)[0]
    grid_width = max(1, round(GRID_WIDTH * zoom))
    horizontal_radius = max(abs(point.x()) for point in geometry.vertices)
    padding = max(3, math.ceil(grid_width / 2) + 2)
    half_width = math.ceil(horizontal_radius) + padding
    half_height = math.ceil(height / 2) + padding
    image = QImage(
        2 * half_width + 1,
        2 * half_height + 1,
        QImage.Format.Format_ARGB32_Premultiplied,
    )

    # Paint the face around the exact center of a transparent image.
    image.fill(Qt.GlobalColor.transparent)
    image_painter = QPainter(image)
    try:
        image_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        image_painter.translate(half_width, half_height)
        _draw_cell(
            image_painter,
            face,
            geometry,
            zoom,
            mirrored=mirrored,
            dim_edges=dim_edges,
            dim_corners=dim_corners,
        )
    finally:
        # Finalize the cached image on both success and failure.
        image_painter.end()

    # Retain the newest face states and discard the least recently used one.
    _FACE_IMAGE_CACHE[cache_key] = image
    if len(_FACE_IMAGE_CACHE) > _FACE_IMAGE_CACHE_SIZE:
        _FACE_IMAGE_CACHE.popitem(last=False)
    return image


def _draw_cell(
    painter: QPainter,
    face: Face,
    geometry: _CellGeometry,
    zoom: float,
    overrides: dict[tuple[Face, str, int], FaceColor] | None = None,
    *,
    mirrored: bool = False,
    dim_edges: bool = False,
    dim_corners: bool = False,
) -> None:
    # Fill the fixed center color as the base of the cell.
    overrides = overrides or {}
    vertices = geometry.vertices
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_color(face.color))
    painter.drawPolygon(vertices)

    # Overlay edge pieces, using pre-turn colors during animation.
    for screen_index, points in enumerate(geometry.edges):
        if len(points) >= 3:
            index = (1 - screen_index) % 6 if mirrored else screen_index
            painter.setBrush(
                _color(
                    overrides.get((face, "edge", index), face.edge_colors[index]),
                    dimmed=dim_edges,
                )
            )
            painter.drawPolygon(points)

    # Overlay corner pieces after edges so their intersections stay visible.
    for screen_index, points in enumerate(geometry.corners):
        if len(points) >= 3:
            index = (-screen_index) % 6 if mirrored else screen_index
            painter.setBrush(
                _color(
                    overrides.get((face, "corner", index), face.corner_colors[index]),
                    dimmed=dim_corners,
                )
            )
            painter.drawPolygon(points)

    # Clip and draw the six curved internal piece boundaries inside the hexagon.
    path = QPainterPath()
    path.addPolygon(vertices)
    painter.save()
    painter.setClipPath(path)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(GRID_COLOR, _piece_grid_width(zoom)))
    radius = round(HEX_HEIGHT * zoom * TURN_GUIDE_DIAMETER_SCALE / 2)
    for center in geometry.circle_centers:
        painter.drawEllipse(QPointF(*center), radius, radius)
    painter.restore()

    # Draw the heavier outer grid border last.
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(GRID_COLOR, max(1, round(GRID_WIDTH * zoom))))
    painter.drawPolygon(vertices)


def _draw_turn_animation(
    painter,
    board,
    visible,
    animation,
    now,
    height,
    zoom,
    *,
    dim_edges: bool = False,
    dim_corners: bool = False,
) -> None:
    # Resolve the moving faces and current eased rotation geometry.
    turning_faces = set(animation.turning_faces)
    radius = round(HEX_HEIGHT * zoom * TURN_GUIDE_DIAMETER_SCALE / 2)
    angle = animation.angle_degrees(now)
    occurrences: dict[tuple[Face, bool], tuple[HexCoordinate, list[tuple[float, float]]]] = {}

    # Group every visible periodic occurrence by its logical face.
    for q, r, center in visible:
        coordinate = HexCoordinate(q, r)
        occurrence = board.occurrence_at(coordinate)
        if occurrence.face in turning_faces:
            key = (occurrence.face, occurrence.mirrored)
            if key not in occurrences:
                occurrences[key] = (coordinate, [])
            occurrences[key][1].append(center)

    # Render each logical orientation once and reuse it at matching centers.
    for (_, mirrored), (coordinate, centers) in occurrences.items():
        visual_angle = -angle if mirrored else angle
        turn_image = _render_turn_image(
            animation,
            board,
            coordinate,
            visual_angle,
            height,
            zoom,
            radius,
            dim_edges=dim_edges,
            dim_corners=dim_corners,
        )
        half_width = turn_image.width() // 2
        half_height = turn_image.height() // 2
        for center in centers:
            painter.drawImage(
                QPointF(round(center[0]) - half_width, round(center[1]) - half_height),
                turn_image,
            )


def _render_turn_image(
    animation,
    board,
    coordinate,
    angle,
    height,
    zoom,
    radius,
    *,
    dim_edges: bool = False,
    dim_corners: bool = False,
) -> QImage:
    """Render one moving disk for reuse at every visible periodic copy."""
    # Create a transparent odd-sized canvas with room for boundary strokes.
    padding = max(3, round(GRID_WIDTH * zoom / 2) + 1)
    size = 2 * (radius + padding) + 1
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        # Rotate the selected face and its six neighbors around the disk center.
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.translate(size // 2, size // 2)
        painter.rotate(angle)
        geometries = _cell_geometries(height)
        coordinates = (coordinate,) + tuple(
            coordinate.translated(dq, dr) for dq, dr in board.NEIGHBOUR_DIRECTIONS
        )
        for cell_coordinate, geometry in zip(coordinates, geometries, strict=True):
            occurrence = board.occurrence_at(cell_coordinate)
            _draw_cell(
                painter,
                occurrence.face,
                geometry,
                zoom,
                animation.source_colors,
                mirrored=occurrence.mirrored,
                dim_edges=dim_edges,
                dim_corners=dim_corners,
            )

        # Apply a pixel-aligned alpha mask after drawing the full moving region.
        painter.resetTransform()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.drawImage(QPointF(0, 0), _circular_alpha_mask(size, radius))
    finally:
        # Complete the image before it is composited onto the board.
        painter.end()
    return image


@lru_cache(maxsize=32)
def _circular_alpha_mask(size: int, radius: int) -> QImage:
    """Return an antialiased disk mask aligned to the turn image's pixel grid."""
    mask = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    mask.fill(Qt.GlobalColor.transparent)
    painter = QPainter(mask)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.GlobalColor.white)
        center = size // 2
        painter.drawEllipse(QPointF(center, center), radius, radius)
    finally:
        painter.end()
    return mask


def _draw_macro_markers(painter, board, visible, radius, face_numbers, zoom) -> None:
    # Configure the shared ring and label style for every marker.
    painter.setFont(_font(max(22, round(42 * zoom)), bold=True))
    painter.setPen(QPen(MACRO_HIGHLIGHT_COLOR, MACRO_HIGHLIGHT_WIDTH))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    label_radius = max(15, round(24 * zoom))

    # Draw a ring and centered ordinal label on each selected face copy.
    for q, r, center in visible:
        number = face_numbers.get(board.face_at(HexCoordinate(q, r)))
        if number is None:
            continue
        point = QPointF(*center)

        # Paint the outer selection ring.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(point, radius, radius)

        # Paint the dark badge and its green number.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(PANEL_BACKGROUND)
        painter.drawEllipse(point, label_radius, label_radius)
        painter.setPen(MACRO_HIGHLIGHT_COLOR)
        rect = QRectF(center[0] - label_radius, center[1] - label_radius, 2 * label_radius, 2 * label_radius)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(number))

        # Restore the ring pen for the next visible copy.
        painter.setPen(QPen(MACRO_HIGHLIGHT_COLOR, MACRO_HIGHLIGHT_WIDTH))


def draw_recording_panel(painter, slot, move_count, face_count) -> None:
    """Draw the active macro-recording panel above the board."""
    # Build the panel text and measure the width required by both lines.
    title = f"RECORDING MACRO {slot}"
    detail = f"Moves: {move_count}   Faces: {face_count}   Enter: save   Esc: cancel"
    title_font = _font(28, bold=True)
    detail_font = _font(21)
    painter.setFont(title_font)
    title_width = painter.fontMetrics().horizontalAdvance(title)
    painter.setFont(detail_font)
    detail_width = painter.fontMetrics().horizontalAdvance(detail)
    width = max(title_width, detail_width) + 52

    # Draw the translucent panel and red recording indicator.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(PANEL_BACKGROUND)
    painter.drawRect(QRectF(16, 16, width, 82))
    painter.setBrush(QColor("#ff3b30"))
    painter.drawEllipse(QPointF(38, 40), 8, 8)

    # Draw the title and the current move/face counters.
    painter.setPen(PANEL_TEXT)
    painter.setFont(title_font)
    painter.drawText(QPointF(54, 49), title)
    painter.setFont(detail_font)
    painter.drawText(QPointF(32, 84), detail)


def draw_status_message(painter, viewport, message, is_error) -> None:
    """Draw a temporary success or error message above the board."""
    painter.setFont(_font(24, bold=True))
    metrics = painter.fontMetrics()
    width = metrics.horizontalAdvance(message) + 32
    height = metrics.height() + 20
    left = (viewport[0] - width) / 2
    top = viewport[1] - height - 18
    rect = QRectF(left, top, width, height)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ERROR_BACKGROUND if is_error else INFO_BACKGROUND)
    painter.drawRect(rect)
    painter.setPen(PANEL_TEXT)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, message)


def _font(size: int, *, bold: bool = False) -> QFont:
    font = QFont("Arial", size)
    font.setBold(bold)
    return font


def _piece_grid_width(zoom: float) -> int:
    """Return one shared divider width for static and animated layers."""
    return max(1, round(PIECE_GRID_WIDTH * zoom))


def _color(color: FaceColor, *, dimmed: bool = False) -> QColor:
    """Return a display color, optionally reduced to a subdued dark tone."""
    if not dimmed:
        return QColor(*color.rgb)
    return QColor(*(round(component * DIM_COLOR_FACTOR) for component in color.rgb))


def _polygon(points) -> QPolygonF:
    return QPolygonF([QPointF(x, y) for x, y in points])


@lru_cache(maxsize=32)
def _cell_geometries(height: int) -> tuple[_CellGeometry, ...]:
    # Select a circle resolution that stays smooth without excessive sampling.
    boundary_radius = round(height * TURN_GUIDE_DIAMETER_SCALE / 2)
    segments = min(64, max(36, round(boundary_radius * 0.25)))
    cells = []

    # Build geometry for the center cell followed by its six neighbors.
    for q, r in ((0, 0),) + PeriodicBoard.NEIGHBOUR_DIRECTIONS:
        # Calculate the outer hexagon and adjacent circle centers.
        center = hex_center(q, r, height)
        vertices = tuple(hex_vertices(center, height))
        neighbor_centers = tuple(
            tuple(round(value) for value in hex_center(q + dq, r + dr, height))
            for dq, dr in PeriodicBoard.NEIGHBOUR_DIRECTIONS
        )

        # Clip each neighboring circle to form the six edge regions.
        edges = tuple(
            tuple(_clip_convex_polygon(_circle_polygon(item, boundary_radius, segments), vertices))
            for item in neighbor_centers
        )

        # Intersect consecutive circles and clip their corner lenses.
        corners = tuple(
            tuple(
                _clip_convex_polygon(
                    _circle_lens_polygon(
                        neighbor_centers[index],
                        neighbor_centers[(index + 1) % 6],
                        boundary_radius,
                        segments // 3,
                    ),
                    vertices,
                )
            )
            for index in range(6)
        )

        # Convert calculated contours to Qt-native cached polygons.
        cells.append(
            _CellGeometry(
                _polygon(vertices),
                tuple(_polygon(edge) for edge in edges),
                tuple(_polygon(corner) for corner in corners),
                neighbor_centers,
            )
        )
    return tuple(cells)


def _circle_polygon(center, radius, segments):
    return [
        (
            round(center[0] + radius * math.cos(2 * math.pi * index / segments)),
            round(center[1] + radius * math.sin(2 * math.pi * index / segments)),
        )
        for index in range(segments)
    ]


def _circle_lens_polygon(first, second, radius, segments):
    # Reject coincident or non-intersecting circles.
    dx, dy = second[0] - first[0], second[1] - first[1]
    distance = math.hypot(dx, dy)
    if distance == 0 or distance >= 2 * radius:
        return []

    # Sample the two opposing arcs that bound their shared lens.
    half_angle = math.acos(distance / (2 * radius))
    points = []
    for center, direction in ((first, math.atan2(dy, dx)), (second, math.atan2(-dy, -dx))):
        for index in range(segments + 1):
            angle = direction - half_angle + 2 * half_angle * index / segments
            points.append(
                (round(center[0] + radius * math.cos(angle)), round(center[1] + radius * math.sin(angle)))
            )

    # Order unique samples around the lens midpoint to form a convex polygon.
    midpoint = ((first[0] + second[0]) / 2, (first[1] + second[1]) / 2)
    return sorted(
        set(points),
        key=lambda point: math.atan2(point[1] - midpoint[1], point[0] - midpoint[0]),
    )


def _clip_convex_polygon(subject, clip):
    # Start with the complete subject polygon in floating-point coordinates.
    output = [(float(x), float(y)) for x, y in subject]

    # Clip the current output against each edge of the convex clip polygon.
    for clip_start, clip_end in zip(clip, clip[1:] + clip[:1]):
        input_points, output = output, []
        if not input_points:
            break

        # Classify points relative to the active clockwise clip edge.
        def inside(point):
            return (
                (clip_end[0] - clip_start[0]) * (point[1] - clip_start[1])
                - (clip_end[1] - clip_start[1]) * (point[0] - clip_start[0])
            ) >= 0

        # Find where a subject segment crosses the active clip edge.
        def intersection(first, second):
            sx, sy = second[0] - first[0], second[1] - first[1]
            cx, cy = clip_end[0] - clip_start[0], clip_end[1] - clip_start[1]
            denominator = sx * cy - sy * cx
            if denominator == 0:
                return second
            amount = (
                (clip_start[0] - first[0]) * cy - (clip_start[1] - first[1]) * cx
            ) / denominator
            return first[0] + amount * sx, first[1] + amount * sy

        # Emit inside vertices and crossing points using Sutherland-Hodgman.
        previous = input_points[-1]
        for current in input_points:
            if inside(current):
                if not inside(previous):
                    output.append(intersection(previous, current))
                output.append(current)
            elif inside(previous):
                output.append(intersection(previous, current))
            previous = current

    # Snap the final contour back to the integer pixel grid.
    return [(round(x), round(y)) for x, y in output]
