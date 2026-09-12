import json

import pytest

from magic_tile.persistence.settings import (
    DEFAULT_TURN_ANIMATION_DURATION_SECONDS,
    SETTINGS_FILENAME,
    Settings,
    load_settings,
)


def test_missing_settings_file_is_created_with_defaults(tmp_path) -> None:
    settings = load_settings(tmp_path)

    settings_path = tmp_path / SETTINGS_FILENAME
    assert settings_path.exists()
    assert settings.turn_animation_duration_seconds == (DEFAULT_TURN_ANIMATION_DURATION_SECONDS)
    assert json.loads(settings_path.read_text(encoding="utf-8")) == {"turn_animation_duration_seconds": 0.5}


def test_settings_file_overrides_animation_duration(tmp_path) -> None:
    (tmp_path / SETTINGS_FILENAME).write_text('{"turn_animation_duration_seconds": 1.25}', encoding="utf-8")

    settings = load_settings(tmp_path)

    assert settings.turn_animation_duration_seconds == 1.25


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
