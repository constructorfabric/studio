"""Sanity: all map fixtures exist and have required files."""
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "map"


def test_repo_basic_has_expected_files():
    base = FIXTURES / "repo-basic"
    assert (base / "artifacts.toml").is_file()
    assert (base / "docs" / "architecture.md").is_file()
    assert (base / "docs" / "cli.md").is_file()
    assert (base / "docs" / "overview.md").is_file()
    assert (base / "src" / "runner.py").is_file()
    assert (base / "src" / "lib.rs").is_file()


def test_repo_no_registry():
    base = FIXTURES / "repo-no-registry"
    assert not (base / "artifacts.toml").exists()
    assert (base / "README.md").is_file()
    assert (base / "docs" / "spec.md").is_file()


def test_repo_dangling():
    base = FIXTURES / "repo-dangling"
    assert (base / "artifacts.toml").is_file()
    assert (base / "src" / "bad.py").is_file()


def test_repo_federated():
    base = FIXTURES / "repo-federated"
    assert (base / "main" / ".cypilot-workspace.toml").is_file()
    assert (base / "main" / "artifacts.toml").is_file()
    assert (base / "kits" / "docs" / "shared.md").is_file()
