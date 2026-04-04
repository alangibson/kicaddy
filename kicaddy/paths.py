from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _detect_version() -> tuple[int, int]:
    """Parse major and minor version from `kicad-cli version` output."""
    try:
        result = subprocess.run(
            ["kicad-cli", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        parts = result.stdout.strip().split(".")
        return int(parts[0]), int(parts[1])
    except Exception:
        return 9, 0


class KiCadPaths:
    """
    Provides KiCad's built-in "Configure Paths" variables as Path properties.

    Variable names containing the major version number (e.g. KICAD9_3DMODEL_DIR)
    are accessible via attribute lookup: paths.KICAD9_3DMODEL_DIR.

    No environment variables are set — these are purely computed values.
    """

    def __init__(self, major: int | None = None, minor: int | None = None) -> None:
        if major is None or minor is None:
            detected_major, detected_minor = _detect_version()
            self._major = major if major is not None else detected_major
            self._minor = minor if minor is not None else detected_minor
        else:
            self._major = major
            self._minor = minor

    @property
    def _ver(self) -> str:
        return f"{self._major}.{self._minor}"

    # ------------------------------------------------------------------
    # Platform helpers
    # ------------------------------------------------------------------

    @property
    def _is_linux(self) -> bool:
        return sys.platform.startswith("linux")

    @property
    def _is_mac(self) -> bool:
        return sys.platform == "darwin"

    @property
    def _is_windows(self) -> bool:
        return sys.platform == "win32"

    @property
    def _appdata(self) -> Path:
        """Windows %APPDATA% as a Path."""
        appdata = os.environ.get("APPDATA", "")
        return Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"

    # ------------------------------------------------------------------
    # Standard KiCad paths
    # ------------------------------------------------------------------

    @property
    def KICAD_CONFIG_HOME(self) -> Path:
        if self._is_windows:
            return self._appdata / "kicad" / self._ver
        if self._is_mac:
            return Path.home() / "Library" / "Preferences" / "kicad" / self._ver
        return Path.home() / ".config" / "kicad" / self._ver

    @property
    def _3DMODEL_DIR(self) -> Path:
        if self._is_windows:
            return Path("C:/Program Files/KiCad") / self._ver / "share" / "kicad" / "3dmodels"
        if self._is_mac:
            return Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels")
        return Path("/usr/share/kicad/3dmodels")

    @property
    def _DESIGN_BLOCK_DIR(self) -> Path:
        if self._is_windows:
            return Path("C:/Program Files/KiCad") / self._ver / "share" / "kicad" / "blocks"
        if self._is_mac:
            return Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/blocks")
        return Path("/usr/share/kicad/blocks")

    @property
    def _FOOTPRINT_DIR(self) -> Path:
        if self._is_windows:
            return Path("C:/Program Files/KiCad") / self._ver / "share" / "kicad" / "footprints"
        if self._is_mac:
            return Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
        return Path("/usr/share/kicad/footprints")

    @property
    def _SYMBOL_DIR(self) -> Path:
        if self._is_windows:
            return Path("C:/Program Files/KiCad") / self._ver / "share" / "kicad" / "symbols"
        if self._is_mac:
            return Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols")
        return Path("/usr/share/kicad/symbols")

    @property
    def _TEMPLATE_DIR(self) -> Path:
        if self._is_windows:
            return Path("C:/Program Files/KiCad") / self._ver / "share" / "kicad" / "template"
        if self._is_mac:
            return Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/template")
        return Path("/usr/share/kicad/template")

    @property
    def _3RD_PARTY(self) -> Path:
        if self._is_windows:
            return self._appdata / "kicad" / self._ver / "3rdparty"
        if self._is_mac:
            return Path.home() / "Library" / "Application Support" / "kicad" / self._ver / "3rdparty"
        return Path.home() / ".local" / "share" / "kicad" / self._ver / "3rdparty"

    @property
    def KICAD_USER_TEMPLATE_DIR(self) -> Path:
        if self._is_windows:
            return self._appdata / "kicad" / self._ver / "template"
        if self._is_mac:
            return Path.home() / "Library" / "Application Support" / "kicad" / self._ver / "template"
        return Path.home() / ".local" / "share" / "kicad" / self._ver / "template"

    @property
    def KIPRJMOD(self) -> Path:
        return Path.cwd()

    # ------------------------------------------------------------------
    # Dynamic attribute lookup for KICAD{major}_* names
    # ------------------------------------------------------------------

    _VERSIONED_SUFFIXES = {
        "3DMODEL_DIR",
        "DESIGN_BLOCK_DIR",
        "FOOTPRINT_DIR",
        "SYMBOL_DIR",
        "TEMPLATE_DIR",
        "3RD_PARTY",
    }

    def __getattr__(self, name: str) -> Path:
        prefix = f"KICAD{self._major}_"
        if name.startswith(prefix):
            suffix = name[len(prefix):]
            if suffix in self._VERSIONED_SUFFIXES:
                return getattr(self, f"_{suffix}")
        raise AttributeError(f"{type(self).__name__!r} has no attribute {name!r}")

    # ------------------------------------------------------------------
    # Bulk export
    # ------------------------------------------------------------------

    def as_dict(self) -> dict[str, str]:
        """Return all path variables as a string dict for ${VAR} expansion."""
        major = self._major
        return {
            "KICAD_CONFIG_HOME": str(self.KICAD_CONFIG_HOME),
            f"KICAD{major}_3DMODEL_DIR": str(self._3DMODEL_DIR),
            f"KICAD{major}_DESIGN_BLOCK_DIR": str(self._DESIGN_BLOCK_DIR),
            f"KICAD{major}_FOOTPRINT_DIR": str(self._FOOTPRINT_DIR),
            f"KICAD{major}_SYMBOL_DIR": str(self._SYMBOL_DIR),
            f"KICAD{major}_TEMPLATE_DIR": str(self._TEMPLATE_DIR),
            f"KICAD{major}_3RD_PARTY": str(self._3RD_PARTY),
            "KICAD_USER_TEMPLATE_DIR": str(self.KICAD_USER_TEMPLATE_DIR),
            "KIPRJMOD": str(self.KIPRJMOD),
        }


paths = KiCadPaths()
