"""Self-contained HTML output.

@cpt-flow:cpt-cypilot-flow-map-render-html:p1
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

ASSETS = Path(__file__).resolve().parent / "assets"


@dataclass(frozen=True)
class RenderHtmlInput:
    json_payload: str
    inline_data: bool
    sidecar_basename: str


def render_html(inp: RenderHtmlInput) -> Tuple[str, Optional[str]]:
    """Return (html_text, js_sidecar_or_None).

    When inline_data=True: returns (html with embedded data, None).
    When inline_data=False: returns (html referencing sidecar, js sidecar content).
    """
    viewer_js = (ASSETS / "viewer.js").read_text(encoding="utf-8")
    viewer_css = (ASSETS / "viewer.css").read_text(encoding="utf-8")

    if inp.inline_data:
        data_script = f"<script>window.MAP_DATA = {inp.json_payload};</script>"
        sidecar_js = None
    else:
        data_script = f'<script src="{inp.sidecar_basename}"></script>'
        sidecar_js = f"window.MAP_DATA = {inp.json_payload};\n"

    html = _TEMPLATE.format(
        css=viewer_css,
        data_script=data_script,
        viewer_js=viewer_js,
    )
    return html, sidecar_js


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>cfc map</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
{css}
</style>
</head>
<body>
<div id="app">
  <aside id="sidebar"></aside>
  <main id="graph"></main>
  <section id="inspector"></section>
</div>
{data_script}
<script>
{viewer_js}
</script>
</body>
</html>
"""
