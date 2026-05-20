"""HTML rendering smoke tests."""
from pathlib import Path

from cypilot.commands.map.render_html import RenderHtmlInput, render_html


def test_inline_html_embeds_data():
    payload = '{"version": "1.0", "nodes": []}'
    html, sidecar = render_html(RenderHtmlInput(
        json_payload=payload, inline_data=True, sidecar_basename="",
    ))
    assert sidecar is None
    assert "window.MAP_DATA" in html
    assert payload in html
    assert "<!doctype html>" in html


def test_sidecar_mode_returns_separate_js():
    payload = '{"version": "1.0"}'
    html, sidecar = render_html(RenderHtmlInput(
        json_payload=payload, inline_data=False, sidecar_basename="md-map.html.js",
    ))
    assert sidecar is not None
    assert payload in sidecar
    assert 'src="md-map.html.js"' in html
    assert payload not in html


def test_viewer_assets_present():
    base = Path(__file__).resolve().parents[1] / "skills" / "cypilot" / "scripts" / "cypilot" / "commands" / "map" / "assets"
    assert (base / "viewer.js").stat().st_size > 100
    assert (base / "viewer.css").stat().st_size > 50
