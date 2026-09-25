"""Tests for cfc map scan layer."""
from pathlib import Path

from studio.commands.map.scan import ScanOptions, scan_repo

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "map"


def _by_id(nodes):
    return {n.id: n for n in nodes}


def test_scan_basic_finds_markdown_and_source():
    nodes = scan_repo(ScanOptions(project_root=FIXTURES / "repo-basic", source_name="local"))
    ids = _by_id(nodes)
    assert "local:docs/architecture.md" in ids
    assert "local:docs/cli.md" in ids
    assert "local:docs/overview.md" in ids
    assert "local:src/runner.py" in ids
    assert "local:src/lib.rs" in ids
    assert ids["local:src/runner.py"].kind == "source"
    assert ids["local:docs/cli.md"].kind == "markdown"


def test_scan_basic_extracts_cpt_defs_and_uses():
    nodes = scan_repo(ScanOptions(project_root=FIXTURES / "repo-basic", source_name="local"))
    ids = _by_id(nodes)
    cli_md = ids["local:docs/cli.md"]
    arch_md = ids["local:docs/architecture.md"]
    assert "cpt-basic-flow-cli:p1" in cli_md.cpt_defs
    assert "cpt-basic-flow-arch:p1" in arch_md.cpt_defs

    runner = ids["local:src/runner.py"]
    use_ids = {u.cpt_id for u in runner.cpt_uses}
    assert "cpt-basic-flow-cli:p1" in use_ids


def test_scan_no_registry_falls_back_to_markdown_only():
    nodes = scan_repo(ScanOptions(project_root=FIXTURES / "repo-no-registry", source_name="local"))
    kinds = {n.kind for n in nodes}
    assert kinds == {"markdown"}
    ids = _by_id(nodes)
    assert "local:README.md" in ids
    assert "local:docs/spec.md" in ids


def test_scan_no_source_flag_skips_source_files():
    nodes = scan_repo(ScanOptions(
        project_root=FIXTURES / "repo-basic", source_name="local", no_source=True,
    ))
    kinds = {n.kind for n in nodes}
    assert kinds == {"markdown"}


def test_scan_respects_registry_extensions():
    base = FIXTURES / "repo-basic"
    stray = base / "src" / "ignored.txt"
    stray.write_text("not source", encoding="utf-8")
    try:
        nodes = scan_repo(ScanOptions(project_root=base, source_name="local"))
        rel_paths = {n.rel_path for n in nodes}
        assert "src/ignored.txt" not in rel_paths
    finally:
        stray.unlink()


def test_scan_ignores_a_link_form_definition(tmp_path):
    """It defines nothing and uses nothing — `cfs validate` reports the line instead.

    Counting it as a use is what the map did while the scan filed such a line as a
    reference to the very id it meant to declare.
    """
    from studio.commands.map.scan import _split_md_cpt

    doc = tmp_path / "PRD.md"
    doc.write_text(
        "# PRD\n\n**ID**: [`cpt-x-flow-login`](spec.md)\n\n`cpt-x-flow-logout`\n",
        encoding="utf-8",
    )
    cpt_defs, cpt_uses = _split_md_cpt(doc)
    assert cpt_defs == []
    assert [u.cpt_id for u in cpt_uses] == ["cpt-x-flow-logout"]
