"""Command-line entry point for MagicTile."""

from magic_tile.persistence import load_settings
from magic_tile.ui.game_window import run


def main() -> int:
    """Start the main game window."""
    settings = load_settings()
    return run(settings)


if __name__ == "__main__":
    raise SystemExit(main())
