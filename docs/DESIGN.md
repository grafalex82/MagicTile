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

The infinite plane is virtual. There are nine unique logical color faces that
repeat periodically across the plane. On-screen copies of the same logical face
represent the same object.

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

The exact key bindings and the mouse gesture for camera panning have not yet
been selected.

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

The following must be defined before the game core is implemented:

1. Which individual pieces make up a face and its outer ring?
2. What is the angle of one move? The likely choice is 60 degrees.
3. What is the exact permutation of corner, edge, and interior pieces produced
   by a move?
4. How are the nine faces arranged in the fundamental periodic region, and how
   do their identifiers repeat along both axes?
5. Can the player rotate any on-screen copy of a face, and how is its keyboard
   identifier selected?
6. What are the scrambling rules: number of moves, immediate inverse moves, and
   random-number seed behavior?
7. How do macros work: live recording or an editor, nesting, length limits, and
   persistence between sessions?
8. What are the setup-move semantics: one stack or multiple named stacks, and
   what happens when ordinary moves occur between setup and undo?
9. Are multiple save slots, autosaving, and portable save files required?
10. Which items and game modes belong in the main menu?

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

