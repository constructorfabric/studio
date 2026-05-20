"""Federation behavior: cross-repo cpt edges + source prefixing."""
import json
import os
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "map"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_map(*args, cwd: Path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "skills" / "cypilot" / "scripts") + ":" + env.get("PYTHONPATH", "")
    cmd = [sys.executable, "-m", "cypilot.cli", "map", *args]
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, check=False)


def test_federated_resolves_cross_repo_cpt(tmp_path):
    out = tmp_path / "out.json"
    proc = _run_map("--format", "json", "--out", str(out), cwd=FIXTURES / "repo-federated" / "main")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text(encoding="utf-8"))

    edges = [(e["from"], e["to"], e["type"], e["cross_repo"]) for e in data["edges"]]
    assert ("local:src/consumer.py", "kits:docs/shared.md", "cpt-impl", True) in edges


def test_federated_workspace_sources_include_kits(tmp_path):
    out = tmp_path / "out.json"
    proc = _run_map("--format", "json", "--out", str(out), cwd=FIXTURES / "repo-federated" / "main")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text(encoding="utf-8"))

    sources = {s["name"] for s in data["workspace"]["sources"]}
    assert "local" in sources
    assert "kits" in sources


def test_local_only_disables_federation(tmp_path):
    out = tmp_path / "out.json"
    proc = _run_map("--format", "json", "--local-only", "--out", str(out),
                    cwd=FIXTURES / "repo-federated" / "main")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    sources = {s["name"] for s in data["workspace"]["sources"]}
    assert sources == {"local"}
    assert any("phantom:" in n["id"] for n in data["nodes"])


def test_local_only_cpt_becomes_dangling(tmp_path):
    out = tmp_path / "out.json"
    proc = _run_map("--format", "json", "--local-only", "--out", str(out),
                    cwd=FIXTURES / "repo-federated" / "main")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text(encoding="utf-8"))

    # With --local-only, the kits markdown is not scanned, so cpt-fed-flow-shared:p1
    # has no definition — the edge must be dangling and point to a phantom node.
    dangling_edges = [e for e in data["edges"] if e.get("dangling")]
    assert len(dangling_edges) >= 1
    assert any("phantom:" in e["to"] for e in dangling_edges)


def test_federated_no_phantom_nodes(tmp_path):
    out = tmp_path / "out.json"
    proc = _run_map("--format", "json", "--out", str(out), cwd=FIXTURES / "repo-federated" / "main")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text(encoding="utf-8"))

    # In federated mode, all cpt-ids from kits are resolved — no phantom nodes.
    phantom_nodes = [n for n in data["nodes"] if n["kind"] == "phantom-cpt"]
    assert phantom_nodes == []


def test_federated_kits_nodes_present(tmp_path):
    out = tmp_path / "out.json"
    proc = _run_map("--format", "json", "--out", str(out), cwd=FIXTURES / "repo-federated" / "main")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text(encoding="utf-8"))

    node_ids = {n["id"] for n in data["nodes"]}
    assert "kits:docs/shared.md" in node_ids
    assert "local:src/consumer.py" in node_ids
