from __future__ import annotations

import hashlib
import logging
import os

import cadquery as cq
from cadquery import exporters

logger = logging.getLogger(__name__)

_CACHE_DIR = os.path.expanduser("~/3dmodel.cache")


def render_step_to_svg(step_path: str, width: int = 300, height: int = 300) -> str | None:
    """Render a STEP file to SVG and return the absolute cache file path.

    Returns the path on success (whether rendered now or already cached).
    Returns None if rendering fails.
    """
    os.makedirs(_CACHE_DIR, exist_ok=True)
    dest = os.path.join(_CACHE_DIR, hashlib.md5(step_path.encode()).hexdigest() + ".svg")
    if os.path.isfile(dest):
        logger.debug("render: cache hit %s -> %s", step_path, dest)
        return dest
    logger.info("render: %s -> %s", step_path, dest)
    if not os.path.isfile(step_path):
        logger.warning("render: file not found: %s", step_path)
        return None
    try:
        shape = cq.importers.importStep(step_path)
        svg_str = exporters.getSVG(shape.val())
        with open(dest, "w") as f:
            f.write(svg_str)
        logger.info("render: wrote %s", dest)
        return dest
    except Exception as exc:
        logger.warning("render: cadquery error for %s: %s", step_path, exc, exc_info=True)
        return None
