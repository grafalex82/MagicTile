"""Command-line entry point for MagicTile."""

from magic_tile.ui.game_window import run


def main() -> int:
    """Start the main game window."""
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
