"""End-to-end CLI tests for cfc map.

@cpt-flow:cpt-cypilot-flow-map-cli:p1
"""
import json
import os
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "map"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_map(*args, cwd: Path) -> tuple:
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(REPO_ROOT / "skills" / "cypilot" / "scripts")
        + ":"
        + env.get("PYTHONPATH", "")
    )
    cmd = [sys.executable, "-m", "studio.cli", "map", *args]
    proc = subprocess.run(
        cmd, cwd=cwd, env=env, capture_output=True, text=True, check=False
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_html_output_default(tmp_path):
    out = tmp_path / "out.html"
    code, stdout, stderr = _run_map("--out", str(out), cwd=FIXTURES / "repo-basic")
    assert code == 0, f"stderr: {stderr}"
    assert out.exists()
    # Either inlined data or sidecar must exist
    sidecar = out.with_name(out.name + ".js")
    assert sidecar.exists() or "window.MAP_DATA" in out.read_text(encoding="utf-8")


def test_json_output(tmp_path):
    out = tmp_path / "out.json"
    code, _stdout, stderr = _run_map(
        "--format", "json", "--out", str(out), cwd=FIXTURES / "repo-basic"
    )
    assert code == 0, f"stderr: {stderr}"
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["version"] == "1.0"
    assert any(n["kind"] == "source" for n in data["nodes"])


def test_no_source_flag(tmp_path):
    out = tmp_path / "out.json"
    code, _, stderr = _run_map(
        "--format", "json", "--no-source", "--out", str(out), cwd=FIXTURES / "repo-basic"
    )
    assert code == 0, f"stderr: {stderr}"
    data = json.loads(out.read_text(encoding="utf-8"))
    kinds = {n["kind"] for n in data["nodes"]}
    assert "source" not in kinds


def test_no_artifacts_toml_falls_back_to_markdown_only(tmp_path):
    out = tmp_path / "out.json"
    code, _, stderr = _run_map(
        "--format", "json", "--out", str(out), cwd=FIXTURES / "repo-no-registry"
    )
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    kinds = {n["kind"] for n in data["nodes"]}
    assert kinds == {"markdown"}


def test_inline_data_flag(tmp_path):
    out = tmp_path / "out.html"
    code, _, stderr = _run_map(
        "--inline-data", "--out", str(out), cwd=FIXTURES / "repo-basic"
    )
    assert code == 0, f"stderr: {stderr}"
    text = out.read_text(encoding="utf-8")
    assert "window.MAP_DATA" in text
    assert not (out.with_name(out.name + ".js")).exists()
