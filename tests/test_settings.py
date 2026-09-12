import json

import pytest

from magic_tile.input import parse_macro, serialize_macro
from magic_tile.persistence.settings import (
    DEFAULT_TURN_ANIMATION_DURATION_SECONDS,
    SETTINGS_FILENAME,
    Settings,
    load_settings,
    save_settings,
)


def test_missing_settings_file_is_created_with_defaults(tmp_path) -> None:
    settings = load_settings(tmp_path)

    settings_path = tmp_path / SETTINGS_FILENAME
    assert settings_path.exists()
    assert settings.turn_animation_duration_seconds == (DEFAULT_TURN_ANIMATION_DURATION_SECONDS)
    assert json.loads(settings_path.read_text(encoding="utf-8")) == {
        "turn_animation_duration_seconds": 0.5,
        "macros": {},
    }


def test_settings_file_overrides_animation_duration(tmp_path) -> None:
    (tmp_path / SETTINGS_FILENAME).write_text('{"turn_animation_duration_seconds": 1.25}', encoding="utf-8")

    settings = load_settings(tmp_path)

    assert settings.turn_animation_duration_seconds == 1.25
    assert settings.macros == (None,) * 10


def test_macros_are_loaded_and_saved_in_canonical_notation(tmp_path) -> None:
    (tmp_path / SETTINGS_FILENAME).write_text(
        json.dumps(
            {
                "turn_animation_duration_seconds": 0.5,
                "macros": {"0": "1 2' 1' 2", "9": "1'"},
            }
        ),
        encoding="utf-8",
    )

    settings = load_settings(tmp_path)

    assert serialize_macro(settings.macros[0]) == "1-2'-1'-2"
    assert serialize_macro(settings.macros[9]) == "1'"
    updated = settings.with_macro(4, parse_macro("1-1'"))
    save_settings(updated, tmp_path)
    persisted = json.loads((tmp_path / SETTINGS_FILENAME).read_text(encoding="utf-8"))
    assert persisted["macros"] == {"0": "1-2'-1'-2", "4": "1-1'", "9": "1'"}


@pytest.mark.parametrize(
    "macros",
    ([], {"10": "1"}, {"slot": "1"}, {"0": ""}, {"0": "1-3"}, {"0": None}),
)
def test_invalid_macro_settings_are_rejected(tmp_path, macros) -> None:
    (tmp_path / SETTINGS_FILENAME).write_text(
        json.dumps({"turn_animation_duration_seconds": 0.5, "macros": macros}), encoding="utf-8"
    )

    with pytest.raises(ValueError):
        load_settings(tmp_path)


def test_application_loads_settings_before_opening_window(monkeypatch) -> None:
    from magic_tile import __main__ as application

    expected_settings = Settings(turn_animation_duration_seconds=1.25)
    monkeypatch.setattr(application, "load_settings", lambda: expected_settings)
    received_settings = None

    def run(settings: Settings) -> int:
        nonlocal received_settings
        received_settings = settings
        return 7

    monkeypatch.setattr(application, "run", run)

    assert application.main() == 7
    assert received_settings is expected_settings


@pytest.mark.parametrize("duration", (0, -0.5, True, "fast"))
def test_invalid_animation_duration_is_rejected(tmp_path, duration) -> None:
    (tmp_path / SETTINGS_FILENAME).write_text(
        json.dumps({"turn_animation_duration_seconds": duration}), encoding="utf-8"
    )

    with pytest.raises(ValueError):
        load_settings(tmp_path)
