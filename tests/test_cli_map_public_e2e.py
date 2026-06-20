"""Public CLI end-to-end coverage for `cfs map`."""

from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.cli import main


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "map"
REPO_BASIC = FIXTURES / "repo-basic"
REPO_NO_REGISTRY = FIXTURES / "repo-no-registry"
REPO_DANGLING = FIXTURES / "repo-dangling"
REPO_FEDERATED_MAIN = FIXTURES / "repo-federated" / "main"


def _run_main(argv: list[str], *, cwd: Path) -> tuple[int, str, str, bool]:
    from studio.utils.ui import is_json_mode, set_json_mode

    stdout = io.StringIO()
    stderr = io.StringIO()
    old_cwd = Path.cwd()
    saved_json_mode = is_json_mode()
    try:
        set_json_mode(False)
        os.chdir(cwd)
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                exit_code = main(argv)
                exited = False
            except SystemExit as exc:
                exit_code = int(exc.code)
                exited = True
        return exit_code, stdout.getvalue(), stderr.getvalue(), exited
    finally:
        set_json_mode(saved_json_mode)
        os.chdir(old_cwd)


def _snapshot_tree(root: Path) -> dict[str, tuple[str, bytes | None]]:
    snapshot: dict[str, tuple[str, bytes | None]] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            snapshot[rel] = ("dir", None)
        elif path.is_file():
            snapshot[rel] = ("file", path.read_bytes())
    return snapshot


def _changed_paths(
    before: dict[str, tuple[str, bytes | None]],
    after: dict[str, tuple[str, bytes | None]],
) -> set[str]:
    return {path for path in set(before) | set(after) if before.get(path) != after.get(path)}


def test_map_html_default_writes_sidecar_and_summary(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out_file = out_dir / "map.html"
    before = _snapshot_tree(out_dir)

    exit_code, stdout, stderr, exited = _run_main(["map", "--out", str(out_file)], cwd=REPO_BASIC)

    after = _snapshot_tree(out_dir)
    assert exited is False
    assert exit_code == 0
    assert stderr == ""
    assert _changed_paths(before, after) == {"map.html", "map.html.js"}

    html_text = out_file.read_text(encoding="utf-8")
    sidecar_path = out_dir / "map.html.js"
    sidecar_text = sidecar_path.read_text(encoding="utf-8")
    assert '<script src="map.html.js"></script>' in html_text
    assert "window.MAP_DATA =" not in html_text
    assert sidecar_text.startswith("window.MAP_DATA = ")
    payload = json.loads(sidecar_text.removeprefix("window.MAP_DATA = ").rstrip(";\n"))
    assert payload["version"] == "1.0"
    assert {node["kind"] for node in payload["nodes"]} == {"markdown", "source"}

    expected_stdout = "\n".join(
        [
            "Config       : (none)",
            "Mode         : single-repo (1 reachable, 0 unreachable)",
            "Source scan  : artifacts.toml: 1 systems, 0 DOCS-ONLY",
            "Scanned      : 3 markdown, 2 source files",
            "Edges        : 2 file-link, 1 cpt-doc, 2 cpt-impl",
            "Phantom IDs  : 0 dangling cpt uses",
            f"Wrote        : {out_file}",
            f"               {sidecar_path}",
            "",
        ]
    )
    assert stdout == expected_stdout


def test_map_html_inline_data_avoids_sidecar_and_limits_writes(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out_file = out_dir / "inline.html"
    before = _snapshot_tree(out_dir)

    exit_code, stdout, stderr, exited = _run_main(
        ["map", "--inline-data", "--out", str(out_file)],
        cwd=REPO_BASIC,
    )

    after = _snapshot_tree(out_dir)
    assert exited is False
    assert exit_code == 0
    assert stderr == ""
    assert _changed_paths(before, after) == {"inline.html"}

    html_text = out_file.read_text(encoding="utf-8")
    assert "window.MAP_DATA =" in html_text
    assert '<script src="inline.html.js"></script>' not in html_text
    assert not (out_dir / "inline.html.js").exists()
    assert stdout.endswith(f"Wrote        : {out_file}\n")
    assert "map.html.js" not in stdout


def test_map_json_no_registry_warns_and_writes_only_json(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out_file = out_dir / "noreg.json"
    before = _snapshot_tree(out_dir)

    exit_code, stdout, stderr, exited = _run_main(
        ["map", "--format", "json", "--out", str(out_file)],
        cwd=REPO_NO_REGISTRY,
    )

    after = _snapshot_tree(out_dir)
    assert exited is False
    assert exit_code == 0
    assert stderr == "map: no artifacts.toml found via adapter resolution; source scanning disabled\n"
    assert _changed_paths(before, after) == {"noreg.json"}

    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert payload["version"] == "1.0"
    assert {node["kind"] for node in payload["nodes"]} == {"markdown"}
    assert payload["scan"]["artifacts_toml"] is None
    assert [source["name"] for source in payload["workspace"]["sources"]] == ["local"]
    assert stdout == "\n".join(
        [
            "Config       : (none)",
            "Mode         : single-repo (1 reachable, 0 unreachable)",
            "Source scan  : artifacts.toml: 0 systems, 0 DOCS-ONLY",
            "Scanned      : 2 markdown, 0 source files",
            "Edges        : 1 file-link, 0 cpt-doc, 0 cpt-impl",
            "Phantom IDs  : 0 dangling cpt uses",
            f"Wrote        : {out_file}",
            "",
        ]
    )


def test_map_json_federated_includes_workspace_source_nodes(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out_file = out_dir / "fed.json"
    before = _snapshot_tree(out_dir)

    exit_code, stdout, stderr, exited = _run_main(
        ["map", "--format", "json", "--out", str(out_file)],
        cwd=REPO_FEDERATED_MAIN,
    )

    after = _snapshot_tree(out_dir)
    assert exited is False
    assert exit_code == 0
    assert stderr == ""
    assert _changed_paths(before, after) == {"fed.json"}

    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert payload["version"] == "1.0"
    assert [source["name"] for source in payload["workspace"]["sources"]] == ["local", "kits"]
    assert {node["source"] for node in payload["nodes"]} == {"local", "kits"}
    assert stdout == "\n".join(
        [
            "Config       : (none)",
            "Mode         : federated (2 reachable, 0 unreachable)",
            "Source scan  : artifacts.toml: 1 systems, 0 DOCS-ONLY",
            "Scanned      : 1 markdown, 1 source files",
            "Edges        : 0 file-link, 0 cpt-doc, 1 cpt-impl",
            "Phantom IDs  : 0 dangling cpt uses",
            f"Wrote        : {out_file}",
            "",
        ]
    )


def test_map_json_dangling_reports_phantom_ids(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out_file = out_dir / "dangling.json"
    before = _snapshot_tree(out_dir)

    exit_code, stdout, stderr, exited = _run_main(
        ["map", "--format", "json", "--out", str(out_file)],
        cwd=REPO_DANGLING,
    )

    after = _snapshot_tree(out_dir)
    assert exited is False
    assert exit_code == 0
    assert stderr == ""
    assert _changed_paths(before, after) == {"dangling.json"}

    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert any(node["kind"] == "phantom-cpt" for node in payload["nodes"])
    assert sum(1 for edge in payload["edges"] if edge["type"] == "cpt-impl") == 1
    assert stdout == "\n".join(
        [
            "Config       : (none)",
            "Mode         : single-repo (1 reachable, 0 unreachable)",
            "Source scan  : artifacts.toml: 1 systems, 0 DOCS-ONLY",
            "Scanned      : 1 markdown, 1 source files",
            "Edges        : 0 file-link, 0 cpt-doc, 1 cpt-impl",
            "Phantom IDs  : 1 dangling cpt uses",
            f"Wrote        : {out_file}",
            "",
        ]
    )


def test_map_invalid_config_exits_2_without_output_mutation(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    config_path = out_dir / "bad.toml"
    config_path.write_bytes(b"\xff\xfe invalid toml [[[\n")
    out_file = out_dir / "bad.json"
    before = _snapshot_tree(out_dir)

    exit_code, stdout, stderr, exited = _run_main(
        ["map", "--format", "json", "--config", str(config_path), "--out", str(out_file)],
        cwd=REPO_BASIC,
    )

    after = _snapshot_tree(out_dir)
    assert exited is True
    assert exit_code == 2
    assert stdout == ""
    assert not out_file.exists()
    assert _changed_paths(before, after) == set()
    assert stderr.startswith(f"map: invalid {config_path}: ")

