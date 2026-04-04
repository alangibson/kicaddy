"""Integration tests for kicaddy.render.

These tests use a real STEP file from the KiCad system library so they exercise
the full cadquery import + SVG export path, catching API mismatches like
wrong method names or passing a Workplane where a Shape is expected.
"""
import os
import pytest

STEP_FILE = "/usr/share/kicad/3dmodels/Resistor_SMD.3dshapes/R_0402_1005Metric.step"


@pytest.fixture(autouse=True)
def clean_cache(tmp_path, monkeypatch):
    """Redirect cache dir to a temp directory so tests don't pollute ~/3dmodel.cache."""
    import kicaddy.render as render
    monkeypatch.setattr(render, "_CACHE_DIR", str(tmp_path))


@pytest.mark.skipif(not os.path.isfile(STEP_FILE), reason="KiCad 3D models not installed")
def test_render_step_to_svg_returns_path():
    from kicaddy.render import render_step_to_svg
    result = render_step_to_svg(STEP_FILE)
    assert result is not None, "render_step_to_svg returned None — check WARNING log for cause"
    assert os.path.isfile(result)


@pytest.mark.skipif(not os.path.isfile(STEP_FILE), reason="KiCad 3D models not installed")
def test_render_step_to_svg_produces_valid_svg():
    from kicaddy.render import render_step_to_svg
    result = render_step_to_svg(STEP_FILE)
    assert result is not None
    with open(result) as f:
        content = f.read()
    assert "<svg" in content, "Output file does not contain SVG content"


@pytest.mark.skipif(not os.path.isfile(STEP_FILE), reason="KiCad 3D models not installed")
def test_render_step_to_svg_caches(tmp_path):
    from kicaddy.render import render_step_to_svg
    first = render_step_to_svg(STEP_FILE)
    mtime = os.path.getmtime(first)
    second = render_step_to_svg(STEP_FILE)
    assert first == second
    assert os.path.getmtime(second) == mtime, "Cache was not used on second call"


def test_render_step_to_svg_missing_file_returns_none():
    from kicaddy.render import render_step_to_svg
    result = render_step_to_svg("/nonexistent/path/model.step")
    assert result is None