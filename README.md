# MagicTile

MagicTile is a computer puzzle played on an infinite periodic plane of
hexagonal faces. Its core idea is similar to a Rubik's Cube: the player rotates
a selected face together with a surrounding ring of pieces and tries to return
every face to a single color.

The project is at an early stage. The periodic board, sticker model, mouse
turns, and exact 60-degree move permutation are implemented; macros, saving,
and the remaining game flow are still planned.

## Core concept

- The board appears infinite but is currently backed by seven logical face
  objects repeated across coordinate-identified cells.
- Hexagons tile the plane without gaps: adjacent faces share an edge, and three
  faces meet at every vertex.
- A turn affects the selected hexagon's pieces and one surrounding outer ring.
- All visible copies of the same logical face rotate simultaneously.
- The player can pan and zoom the camera.
- A left click turns a face counterclockwise; a right click turns it clockwise.
  Keyboard controls will also be available.
- Planned features include macros, setup moves, and reverse playback of setup
  sequences.
- The game state can be saved and restored between sessions.

See the [design document](docs/DESIGN.md) for details and unresolved questions,
and the [roadmap](docs/ROADMAP.md) for the planned implementation stages.

## Repository structure

```text
MagicTile/
├── assets/                  # Images, fonts, and sounds
├── docs/
│   ├── DESIGN.md            # Rules, controls, and open questions
│   └── ROADMAP.md           # Implementation stages
├── magic_tile/
│   ├── domain/              # Board model, pieces, and moves
│   ├── input/               # Mouse, keyboard, and macros
│   ├── persistence/         # Saving and loading
│   └── ui/                  # Pygame, camera, rendering, and menus
└── tests/                   # Automated tests
```

Each logical face has a center color, six edge-color slots, six corner-color
slots, and six permanent neighbor references. A face does not own a coordinate:
multiple cells in the repeating plane may resolve to the same object. Colors are
visual attributes rather than identifiers. This lets future board configurations
contain repeated colors with different local neighborhoods.

## Requirements

- Python 3.11 or newer
- pygame
- pytest for development

`pyenv` is not required. Dependencies are listed in `requirements.txt`, and the
test configuration lives in `pytest.ini`.

## Running the project

Launch the graphics prototype with:

```bash
python -m magic_tile
```

Install or update the dependencies when needed:

```bash
python -m pip install -r requirements.txt
```

The prototype displays a resizable pygame window with a periodically coloured
flat-top hexagonal grid. Every hexagon is 200 pixels high. Left-click a face to
turn every copy of that logical face counterclockwise; right-click to turn it
clockwise. A turn lasts for the configured duration and locks other board
controls. Drag with
the left mouse button more than 5 pixels on either axis to pan. Releasing it
within that threshold turns the face. Scroll up to zoom in or down to zoom out;
zoom is limited to 50% through 250%. Use Ctrl+Z to undo and Ctrl+Y (or
Ctrl+Shift+Z) to redo; both play the normal turn animation. Press Escape or
close the window to exit.

On startup, the game loads `settings.json` from the current directory. If the
file does not exist, it creates one with the default settings. The currently
supported option is `turn_animation_duration_seconds`, which defaults to 0.5
seconds:

```json
{
  "turn_animation_duration_seconds": 0.5
}
```

## Tests

```bash
pytest
```

## Code style

Source code uses a maximum line length of 110 characters. Keep calls with
several arguments on one line when they fit within that limit; wrap them only
when they do not. 

Leave two blank lines between module-level functions and Sclasses. 

## License

The source code is available under the [MIT License](LICENSE). It is a short,
widely recognized permissive license that allows anyone to use, copy, modify,
distribute, sublicense, and sell copies of the software. Their main obligation
is to retain the copyright and license notice. The software is provided without
warranty, which limits the authors' liability.

MIT is a good fit if the goal is broad adoption, easy contribution, and minimal
restrictions—including allowing closed-source or commercial derivative games.
It does **not** require improvements or derivative works to remain open source.
If that requirement is important, a copyleft license such as GPL-3.0 would be a
better choice. If patent protection is a significant concern, Apache-2.0 offers
an explicit patent grant that MIT does not spell out.

Art, fonts, music, and other assets may have separate licenses. Any such license
must be documented alongside the relevant asset.
