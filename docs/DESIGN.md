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

The infinite plane is virtual. The current configuration contains seven logical
face objects that repeat periodically across coordinate-identified cells. A
face itself has no coordinate: cells at different coordinates can resolve to the
same in-memory object. The seven objects form a torus; following any fixed
neighbor direction seven times returns to the starting face.

### Piece terminology

- A cell is identified by its axial coordinate and resolves to a face object.
  The face's object identity distinguishes it from other logical faces.
- A face's fixed center `color` is a visual attribute, just like its movable
  edge and corner colors.
- Every face stores six neighbor references in cyclic slot order. These links
  are connected while the board is built and remain unchanged afterward.
- An edge element is represented by one visible color slot on each of its two
  adjacent faces.
- A corner element is represented by one visible color slot on each of its
  three adjacent faces.
- A `Face` is the set visible around one center: one center, six edges, and six
  corners.

### Moves

A face rotates around its center either clockwise or counterclockwise. The move
area has a radius slightly larger than the hexagon and includes its pieces plus
one outer ring of surrounding pieces.

When a logical face appears in multiple on-screen locations, all of its copies
animate simultaneously. Faces sharing a center color also belong to the same
turn group, while retaining independent coordinate identities and neighborhoods.
Animation must not determine the move result: the model first applies an exact
permutation, while the view only displays the transition.

### Objective

After the puzzle has been scrambled, the player must solve it so that every
face consists entirely of pieces of its own color.

### Controls

- Left mouse button: rotate the selected face counterclockwise when released
  within 5 pixels on both axes; drag it farther to pan the camera.
- Right mouse button: rotate the selected face clockwise.
- Keyboard: alternative face selection and rotation controls.
- Macros: record face-relative move sequences in ten persistent keyboard slots.
- Setup moves: record a preparation sequence and later undo that sequence in
  reverse order.

Keyboard bindings have not yet been selected.

### Saves and menus

The game must save the puzzle state and restore it on a later launch. At a
minimum, the main menu must provide access to continuing the game, saving the
current state, and choosing available actions or modes. The exact menu contents
will be determined later.

## Architectural boundaries

- `domain` has no dependency on PyQt6. It contains coordinates, pieces,
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
4. What are the setup-move semantics: one stack or multiple named stacks, and
   what happens when ordinary moves occur between setup and undo?
5. Are multiple save slots, autosaving, and portable save files required?
6. Which items and game modes belong in the main menu?

## Macros

Ctrl plus a digit begins live recording in that slot. Turns continue to update
the model and use the normal animation. Logical faces receive relative numbers
in first-use order, so a recorded sequence can later be applied to a different
ordered selection of faces. Enter saves the macro to the settings file; Escape
cancels it, restores the previous undo/redo branches, and animates the inverse
sequence.

Recording and ordinary play use the same linear undo/redo history and cursor.
Undo cannot cross the point where recording began; it removes the last active
move from both the board and the macro. Redo restores that move to both. This
keeps the recorded sequence identical to the active history segment.

Shift plus a left click builds an ordered selection of unique logical faces.
A digit plays its macro and Shift plus that digit plays the reversed sequence
with inverted directions. Playback is non-interruptible, keeps its selection,
and rejects selections whose size differs from the macro's required face
count. Escape clears a selection but never exits the application.

## Implemented move geometry

Each logical face owns six visible edge-color slots and six visible corner-color
slots in counterclockwise screen order. A 60-degree turn cycles all twelve
selected-face slots. It also cycles the inward-facing edge and the two endpoint
corners reached through the face's stored neighbor references. Mutable slot
maps and animation snapshots are keyed by references to the owning face object,
never by coordinate or color. This sticker-slot representation records
orientation directly; there are no shared `Edge` or `Corner` object classes in
the mutable model.

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
`Face.corner_colors` for every visible cell. The color-independent contours in
`_CellGeometry` are cached by pixel height. `QPainter` fills the center polygon,
the six circle-clipped edge polygons, and the six consecutive-circle corner
lenses before drawing the dividing arcs and outer border.

The edge and corner indices match the cyclic indices in the domain model.
Qt's antialiased vector painting keeps the geometry smooth at every camera
zoom. A completed image of each distinct logical face is cached and reused for
all of its periodic copies, avoiding repeated vector construction.

### Starting a turn

`TurnAnimation.begin()` receives the selected axial coordinate and first uses
`PeriodicBoard.affected_slots()` to capture the old colors of every slot that
will move. It then immediately calls `PeriodicBoard.turn()`, committing the
exact final permutation to the model.
The model has no intermediate animation state: the transition exists only in
the view.

The widget caches the complete static board for its viewport. Starting a turn
reuses the already visible pre-turn background because every changed sticker is
covered by the animated disk. The background is refreshed after the animation,
between queued turns, or after resize, pan, and zoom. This keeps the first
animated frame responsive without retaining stale pixels after completion.

### Animated turn disk

The animated layer contains the selected cell and its six neighbors, whose
unrotated contours are cached as seven `_CellGeometry` instances.

Each `_CellGeometry` stores an outer hexagon in `vertices`, six edge-region
contours in `edges`, and six corner-region contours in `corners`. Its points are
expressed relative to the selected cell's center, which is the shared rotation
origin. Edge contours are hexagons clipped by the corresponding neighboring
circles; corner contours are clipped circle lenses. The circular arcs are
densely sampled into polygon contours and transformed by `QPainter` on every
frame.

For angle `a`, the painter is translated to each visible occurrence of the
logical face and rotated around that occurrence's center.

This transforms the selected center region, its edge and corner regions, the
adjoining regions of all six neighbors, and their dividing lines together.
The fixed center color does not change in the model, but its visible geometry
participates in the rotation.

The model already contains the completed move, so affected slots are drawn
from `TurnAnimation.source_colors`, which holds their pre-move colors. Slots
outside the move use their current model colors. At exactly 60 degrees the old
colors have arrived at the positions already stored in the model, allowing the
animated layer to disappear without a visual jump.

An antialiased image mask clips the animated layer to a pixel-aligned circular
turn disk. The black turn boundary and red guide are drawn above its edge to
hide sampling seams between moving and stationary geometry. A frame is produced
from each face object's own stored neighborhood at all matching visible
coordinates, making periodic copies and same-colored turn groups animate
synchronously.

The final layer order is:

1. black window background;
2. static board in its completed model state;
3. vector-rendered, circularly clipped turn layer;
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
