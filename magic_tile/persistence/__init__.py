"""Versioned game-state storage, loading, and application settings."""

from magic_tile.persistence.settings import Settings, load_settings, save_settings

__all__ = ["Settings", "load_settings", "save_settings"]
