from __future__ import annotations

import configparser
import os
from pathlib import Path

_CONFIG_FILE = Path(__file__).parent / "kicaddy.ini"
_SECTION = "kicaddy"


def get_db_path() -> str:
    """Return the configured database path.

    Priority: KICADDY_DB environment variable > kicaddy.ini > empty string.
    """
    env = os.environ.get("KICADDY_DB", "")
    if env:
        return env
    cfg = configparser.ConfigParser()
    cfg.read(_CONFIG_FILE)
    return cfg.get(_SECTION, "db_path", fallback="")


def set_db_path(path: str) -> None:
    """Persist the database path to kicaddy.ini next to this file."""
    cfg = configparser.ConfigParser()
    cfg.read(_CONFIG_FILE)
    if not cfg.has_section(_SECTION):
        cfg.add_section(_SECTION)
    cfg.set(_SECTION, "db_path", path)
    with open(_CONFIG_FILE, "w") as f:
        cfg.write(f)


def get_lib_tables() -> list[str]:
    """Return the configured list of library table file paths."""
    cfg = configparser.ConfigParser()
    cfg.read(_CONFIG_FILE)
    raw = cfg.get(_SECTION, "lib_tables", fallback="")
    return [p.strip() for p in raw.splitlines() if p.strip()]


def set_lib_tables(paths: list[str]) -> None:
    """Persist library table file paths (newline-separated) to kicaddy.ini."""
    cfg = configparser.ConfigParser()
    cfg.read(_CONFIG_FILE)
    if not cfg.has_section(_SECTION):
        cfg.add_section(_SECTION)
    cfg.set(_SECTION, "lib_tables", "\n".join(paths))
    with open(_CONFIG_FILE, "w") as f:
        cfg.write(f)
