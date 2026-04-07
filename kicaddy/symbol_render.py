from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def render_symbol_to_svg(library_path: str, symbol_name: str) -> str | None:
    """Render a KiCad symbol to SVG using kicad-cli.

    Returns the SVG string on success, or None if kicad-cli is not found
    or rendering fails.
    """
    kicad_cli = shutil.which("kicad-cli")
    if not kicad_cli:
        logger.warning("symbol_render: kicad-cli not found on PATH")
        return None
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [
                kicad_cli, "sym", "export", "svg",
                "--symbol", symbol_name,
                "--output", tmpdir,
                library_path,
            ],
            capture_output=True,
            timeout=15,
        )
        if result.returncode != 0:
            logger.warning(
                "symbol_render: kicad-cli failed for %s: %s",
                symbol_name,
                result.stderr.decode(errors="replace"),
            )
            return None
        svgs = list(Path(tmpdir).glob("*.svg"))
        if not svgs:
            logger.warning("symbol_render: no SVG output produced for %s", symbol_name)
            return None
        return svgs[0].read_text(encoding="utf-8")
