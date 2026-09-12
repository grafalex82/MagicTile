# MagicTile concept and design

This document records the current project concept. Statements under “Confirmed
concept” are treated as initial requirements. The questions listed later must
be resolved before the corresponding systems are implemented.

## Confirmed concept

### Board

The game board is a flat tiling of regular hexagons. Every hexagon shares its
edges with neighboring hexagons, and three hexagons meet at each vertex.

The player sees a finite viewport onto an infinite plane and can:

- pan the camera up, down, left, and right;
- zoom in and out;
- select any visible face for rotation.

The infinite plane is virtual. There are seven unique logical color faces that
repeat periodically across the plane. On-screen copies of the same logical face
represent the same object.

### Piece terminology

- A face's fixed `color` identifies it; only its edge and corner color slots move.
- An edge element is represented by one visible color slot on each of its two
  adjacent faces.
- A corner element is represented by one visible color slot on each of its
  three adjacent faces.
- A `Face` is the set visible around one center: one center, six edges, and six
  corners.
- A `FaceNeighborhood` is only a geometric helper containing one focused face
  and the six faces around it; it is not a puzzle element.

### Moves

A face rotates around its center either clockwise or counterclockwise. The move
area has a radius slightly larger than the hexagon and includes its pieces plus
one outer ring of surrounding pieces.

When a logical face appears in multiple on-screen locations, all of its copies
animate simultaneously. Animation must not determine the move result: the model
first applies an exact permutation, while the view only displays the transition.

### Objective

After the puzzle has been scrambled, the player must solve it so that every
face consists entirely of pieces of its own color.

### Controls

- Left mouse button: rotate the selected face counterclockwise.
- Right mouse button: rotate the selected face clockwise.
- Keyboard: alternative face selection and rotation controls.
- Macros: bind repeatable move sequences to keyboard shortcuts.
- Setup moves: record a preparation sequence and later undo that sequence in
  reverse order.

Middle-button dragging pans the camera. Keyboard bindings have not yet been
selected.

### Saves and menus

The game must save the puzzle state and restore it on a later launch. At a
minimum, the main menu must provide access to continuing the game, saving the
current state, and choosing available actions or modes. The exact menu contents
will be determined later.

## Architectural boundaries

- `domain` has no dependency on Pygame. It contains coordinates, pieces,
  permutations, move history, and solved-state validation.
- `ui` renders the model and manages the camera and animation.
- `input` translates mouse and keyboard events into commands and owns macro and
  setup-move behavior.
- `persistence` serializes versioned game state.

This separation allows pytest to verify all game rules without opening a
graphics window or processing system events.

## Open questions

The following remain to be defined:

1. Which identifiers and controls should be assigned to the seven logical
   faces?
2. How is a face's keyboard identifier selected?
3. What are the scrambling rules: number of moves, immediate inverse moves,
   and random-number seed behavior?
4. How do macros work: live recording or an editor, nesting, length limits, and
   persistence between sessions?
5. What are the setup-move semantics: one stack or multiple named stacks, and
   what happens when ordinary moves occur between setup and undo?
6. Are multiple save slots, autosaving, and portable save files required?
7. Which items and game modes belong in the main menu?

## Implemented move geometry

Each logical face owns six visible edge-color slots and six visible
corner-color slots in counterclockwise screen order. A 60-degree turn cycles
all twelve selected-face slots. It also cycles the inward-facing edge and the
two endpoint corners of each neighboring face to the corresponding slots on
the next neighbor. This sticker-slot representation records orientation
directly; there are no shared `Edge` or `Corner` object classes in the mutable
model.

Any visible periodic copy can be clicked, and all copies of its logical face
animate together. The model permutation is committed atomically before the
0.5-second view transition begins.

## Rendering pipeline

`draw_board()` is the common entry point for static and animated frames. It
clears the window, converts the camera zoom and offset to screen-space hexagon
dimensions, and materializes the visible cells as `(q, r, screen_center)`
tuples. Each axial coordinate is resolved to its repeating logical `Face`
through `PeriodicBoard.face_at()`.

### Static hexagons

`_draw_faces()` obtains `Face.color`, `Face.edge_colors`, and
`Face.corner_colors` for every visible cell. `_render_curved_face()` then
composes one transparent face surface from the masks stored in
`_CurvedFaceGeometry`.

The geometry is generated at twice the requested resolution and downscaled at
the end for antialiasing. It consists of:

- `hex_mask`, which covers the whole hexagon and is initially filled with the
  face's fixed center color;
- `edge_masks[i]`, the part of the hexagon covered by exactly neighboring
  circle `i`;
- `corner_masks[i]`, the intersection of neighboring circles `i` and
  `(i + 1) % 6` inside the hexagon;
- `boundaries`, a transparent overlay containing the six circular dividing
  arcs and the outer hexagon border.

The edge and corner indices match the cyclic indices in the domain model.
Colors are applied in the order center, edges, corners, and finally boundary
lines. Thus the static edge and corner regions are cut from circle masks rather
than defined as hand-authored polygon shapes. The resulting supersampled image
is smoothly reduced to its display size and blitted with its center aligned to
the cell's `screen_center`.

Both the color-composed face surface and its color-independent geometry are
cached. Faces with the same dimensions, line widths, and colors therefore do
not need to be reconstructed on every frame.

### Starting a turn

`TurnAnimation.begin()` first uses `PeriodicBoard.affected_slots()` to capture
the old colors of every slot that will move. It then immediately calls
`PeriodicBoard.turn()`, committing the exact final permutation to the model.
The model has no intermediate animation state: the transition exists only in
the view.

The first animation frame creates a `_TurnRenderCache`. Its `background` is a
complete static rendering of the board in the final model state, while
`centers` contains the screen-pixel centers of every visible periodic copy of
the turning logical face. The cache is keyed by window size, camera offset, and
zoom. It is rebuilt after a resize, pan, or zoom; otherwise its background is
restored before every frame so no pixels from the preceding frame remain.

### Animated turn disk

`_render_turn_frame()` procedurally rasterizes the moving region for the
current angle. It does not rotate a previously rendered bitmap. The frame
contains the selected cell and its six neighbors, whose unrotated contours are
cached as seven `_TurnCellGeometry` instances.

Each `_TurnCellGeometry` stores an outer hexagon in `vertices`, six edge-region
contours in `edges`, and six corner-region contours in `corners`. Its points are
expressed relative to the selected cell's center, which is the shared rotation
origin. Edge contours are hexagons clipped by the corresponding neighboring
circles; corner contours are clipped circle lenses. The circular arcs are
densely sampled into polygon contours because Pygame must transform their
individual points on every frame.

For angle `a`, every contour point is rotated and translated to the turn-frame
center using:

```text
x' = center_x + x * cos(a) - y * sin(a)
y' = center_y + x * sin(a) + y * cos(a)
```

This transforms the selected center region, its edge and corner regions, the
adjoining regions of all six neighbors, and their dividing lines together.
The fixed center color does not change in the model, but its visible geometry
participates in the rotation.

The model already contains the completed move, so affected slots are drawn
from `TurnAnimation.source_colors`, which holds their pre-move colors. Slots
outside the move use their current model colors. At exactly 60 degrees the old
colors have arrived at the positions already stored in the model, allowing the
animated layer to disappear without a visual jump.

After rasterization, a circular alpha mask removes every pixel outside the
turn disk. At zoom levels below 100%, the disk is first rendered at 100% and
then smoothly reduced to the exact target radius before the circular mask is
reapplied. This keeps small-scale lines and curves stable. The same finished
turn frame is centered on every point in `_TurnRenderCache.centers`, making all
visible copies of one logical face animate synchronously.

The final layer order is:

1. black window background;
2. static board or cached animation background;
3. procedurally rendered turn disk;
4. red turn-guide highlight.

Drawing the highlight last keeps it visible above the moving disk for the
entire animation.

## Preliminary technical decisions

- Logical positions use integer axial or cube coordinates for the hexagonal
  grid. Screen coordinates are calculated only during rendering.
- State is stored for the fundamental region, not for an infinite number of
  on-screen copies.
- A move is represented by an immutable command containing a face identifier
  and direction.
- Save files use versioned JSON rather than Python-specific serialization.
- Animation progress is kept separate from the completed model state.

These are working proposals and may change after the geometry is prototyped.
