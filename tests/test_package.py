from magic_tile import __version__
from magic_tile.__main__ import main


def test_package_has_version() -> None:
    assert __version__ == "0.1.0"


def test_placeholder_entry_point(capsys) -> None:
    assert main() == 0
    assert capsys.readouterr().out == "MagicTile: project skeleton is ready.\n"

