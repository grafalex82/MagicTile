# Roadmap

## 0. Formalize the rules

- Draw one face and its outer ring with identifiers for every piece.
- Describe the result of a turn as an explicit permutation.
- Define the nine-face fundamental region and its periodicity rules.
- Prepare several reference states for automated tests.

Completion criterion: the result of any single move can be calculated
unambiguously without a graphical interface.

## 1. Domain model

- Board coordinates and topology.
- Puzzle colors and pieces.
- Moves in both directions and inverse moves.
- Move history, scrambling, and solved-state validation.
- Unit and property-based tests for key invariants.

Key invariants: a move followed by its inverse restores the original state; six
60-degree turns restore the original state; no piece is lost or duplicated.

## 2. Graphics prototype

- Pygame window and main loop.
- Rendering of the repeating hexagonal board.
- Camera panning and zooming.
- Mouse face selection and turn animation.

## 3. Interaction

- Configurable keyboard controls.
- Scramble generator.
- Move history and undo.
- Macros.
- Setup moves and reverse playback.

## 4. Saves and menus

- Versioned save format.
- Automatic loading and safe atomic writes.
- Main menu, continue, new game, and save slots.
- Handling of damaged or incompatible save files.

## 5. Completion

- Sound, graphics, and control settings.
- Art, sound, and visual polish.
- Performance profiling at distant zoom levels and with many visible copies.
- Distribution builds for the target operating systems.

