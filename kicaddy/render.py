from __future__ import annotations

import logging

import cadquery as cq
from cadquery import exporters

logger = logging.getLogger(__name__)


def render_step_to_svg(step_path: str, width: int = 300, height: int = 300) -> str | None:
    """Render a STEP file to SVG and return the SVG content as a string.

    Returns the SVG string on success, or None if rendering fails.
    """
    import os
    if not os.path.isfile(step_path):
        logger.warning("render: file not found: %s", step_path)
        return None
    logger.info("render: %s", step_path)
    try:
        shape = cq.importers.importStep(step_path)
        svg_str = exporters.getSVG(shape.val())
        return svg_str
    except Exception as exc:
        logger.warning("render: cadquery error for %s: %s", step_path, exc, exc_info=True)
        return None
