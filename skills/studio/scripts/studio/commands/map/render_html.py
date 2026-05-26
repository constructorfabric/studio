"""Self-contained HTML output.

@cpt-algo:cpt-studio-algo-map-render-html:p1
@cpt-dod:cpt-studio-dod-dependency-mapping-html:p1
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

ASSETS = Path(__file__).resolve().parent / "assets"
VENDOR = ASSETS / "vendor"


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
    # @cpt-begin:cpt-studio-algo-map-render-html:p1:inst-render-html
    viewer_js = (ASSETS / "viewer.js").read_text(encoding="utf-8")
    viewer_css = (ASSETS / "viewer.css").read_text(encoding="utf-8")
    marked_js = (VENDOR / "marked.min.js").read_text(encoding="utf-8")
    purify_js = (VENDOR / "purify.min.js").read_text(encoding="utf-8")

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
        marked_js=marked_js,
        purify_js=purify_js,
    )
    return html, sidecar_js
    # @cpt-end:cpt-studio-algo-map-render-html:p1:inst-render-html


# @cpt-begin:cpt-studio-algo-map-render-html:p1:inst-html-template
_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>cfs map</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<script>
{marked_js}
</script>
<script>
{purify_js}
</script>
<style>
{css}
</style>
</head>
<body>
<div id="app">
  <aside id="sidebar"></aside>
  <div id="graph-wrap">
    <button id="sidebar-toggle" title="Toggle category panel" aria-pressed="false">☰</button>
    <main id="graph"></main>
    <div id="hand-overlay"></div>
    <div id="toolbar">
      <button id="tb-back"     title="Back (previous node)">◀</button>
      <button id="tb-fwd"      title="Forward (next node)">▶</button>
      <button id="tb-zoom-in"  title="Zoom in">+</button>
      <button id="tb-zoom-out" title="Zoom out">−</button>
      <button id="tb-fit"      title="Fit all">⛶</button>
      <button id="tb-hand"     title="Hand tool — drag anywhere to pan">✋</button>
    </div>
  </div>
  <section id="inspector">
    <div id="inspector-resize-handle" aria-label="Resize inspector"></div>
  </section>
</div>
{data_script}
<script>
{viewer_js}
</script>
</body>
</html>
"""
# @cpt-end:cpt-studio-algo-map-render-html:p1:inst-html-template
