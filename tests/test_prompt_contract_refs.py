"""Prompt contracts must not depend on definitions the release does not ship.

Six review agents once required an "AP-001..AP-008 self-check" whose definitions lived in
`requirements/agent-compliance.md`, a file deleted before the first tag. Every release then
shipped the requirement without the definitions, and nothing failed. These tests pin both
halves of that gap: every cited AP id is defined in `requirements/review-anti-patterns.md`,
and every `{cf-studio-path}/.core/<path>` reference in a prompt names a file that exists.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

CATALOG = Path("requirements/review-anti-patterns.md")

#: Prompt surfaces this repository authors and ships.
AUTHORED_ROOTS = ("skills", "workflows", "requirements", "architecture")

#: The installed SDLC kit is vendored from `constructorfabric/studio-kit-sdlc`; it is fixed
#: there, not here, so it is checked against a known-debt list instead of strictly.
KIT_ROOT = Path(".bootstrap/config/kits")

#: Dangling `.core` references in the vendored kit, as `(file, target)`. Remove an entry
#: when the kit release that fixes it is installed; the stale-entry test enforces that.
KNOWN_KIT_DANGLING = frozenset({
    ("sdlc/artifacts/DESIGN/checklist.md", "requirements/agent-compliance.md"),
    ("sdlc/workflows/pr-review.md", "skills/cf-studio/SKILL.md"),
    ("sdlc/workflows/pr-status.md", "skills/cf-studio/SKILL.md"),
    ("sdlc/workflows/migrate-openspec.md", "skills/cf-studio/scripts/cfs.py"),
})

AP_RANGE = re.compile(r"\bAP-(\d{3})\s*\.\.\s*AP-(\d{3})\b")
AP_SINGLE = re.compile(r"\bAP-(\d{3})\b")
CATALOG_ROW = re.compile(r"^\|\s*AP-(\d{3})\s*\|\s*([A-Z_]+)\s*\|", re.MULTILINE)
CORE_REF = re.compile(r"\{cf-studio-path\}/\.core/([A-Za-z0-9_./-]*[A-Za-z0-9_-])")


def _markdown(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.md") if p.is_file())


def _cited_ap_ids(text: str) -> set[int]:
    ids: set[int] = set()
    for low, high in AP_RANGE.findall(text):
        ids.update(range(int(low), int(high) + 1))
    ids.update(int(n) for n in AP_SINGLE.findall(text))
    return ids


def _defined_ap_ids(root: Path) -> set[int]:
    return {int(n) for n, _ in CATALOG_ROW.findall((root / CATALOG).read_text(encoding="utf-8"))}


def _dangling_core_refs(root: Path, scan_root: Path) -> set[tuple[str, str]]:
    dangling = set()
    for path in _markdown(root / scan_root):
        for target in CORE_REF.findall(path.read_text(encoding="utf-8")):
            # A trailing `-` is a filename prefix such as `requirements/storytelling-*`.
            if target.endswith("-") or (root / target).exists():
                continue
            dangling.add((path.relative_to(root / scan_root).as_posix(), target))
    return dangling


def _undefined_ap_citations(root: Path, scan_roots: list[Path]) -> list[str]:
    defined = _defined_ap_ids(root)
    problems = []
    for scan_root in scan_roots:
        for path in _markdown(root / scan_root):
            missing = _cited_ap_ids(path.read_text(encoding="utf-8")) - defined
            if missing:
                ids = ", ".join(f"AP-{n:03d}" for n in sorted(missing))
                problems.append(f"{path.relative_to(root).as_posix()}: {ids}")
    return problems


def _agents_citing_ap_without_catalog(root: Path) -> list[str]:
    return [
        path.relative_to(root).as_posix()
        for path in _markdown(root / "skills")
        if _cited_ap_ids(path.read_text(encoding="utf-8"))
        and CATALOG.as_posix() not in path.read_text(encoding="utf-8")
    ]


# ------------------------------------------------------------------ the shipped tree
def test_catalog_defines_exactly_ap_001_to_008() -> None:
    assert _defined_ap_ids(REPO_ROOT) == set(range(1, 9))


def test_every_cited_ap_id_is_defined_in_the_catalog() -> None:
    roots = [Path(r) for r in AUTHORED_ROOTS] + [Path("tests/prompts"), KIT_ROOT]
    assert _undefined_ap_citations(REPO_ROOT, roots) == []


def test_every_skill_citing_an_ap_id_names_the_catalog_as_its_source() -> None:
    assert _agents_citing_ap_without_catalog(REPO_ROOT) == []


@pytest.mark.parametrize("scan_root", AUTHORED_ROOTS)
def test_authored_core_references_resolve(scan_root: str) -> None:
    assert _dangling_core_refs(REPO_ROOT, Path(scan_root)) == set()


def test_kit_core_references_resolve_or_are_known_debt() -> None:
    assert _dangling_core_refs(REPO_ROOT, KIT_ROOT) - KNOWN_KIT_DANGLING == set()


def test_known_kit_debt_has_no_stale_entries() -> None:
    assert KNOWN_KIT_DANGLING - _dangling_core_refs(REPO_ROOT, KIT_ROOT) == set()


# ------------------------------------------------- the checks fail on the original defect
def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def catalog_tree(tmp_path: Path) -> Path:
    _write(tmp_path, CATALOG.as_posix(),
           "| AP-001 | SKIP_SEMANTIC | d | s |\n| AP-002 | MEMORY_VALIDATION | d | s |\n")
    return tmp_path


def test_a_range_beyond_the_catalog_is_reported(catalog_tree: Path) -> None:
    _write(catalog_tree, "skills/a.md", "ALWAYS perform AP-001..AP-003 self-check\n")
    assert _undefined_ap_citations(catalog_tree, [Path("skills")]) == ["skills/a.md: AP-003"]


def test_a_skill_citing_ap_ids_without_the_catalog_is_reported(catalog_tree: Path) -> None:
    _write(catalog_tree, "skills/a.md", "ALWAYS perform AP-001..AP-002 self-check\n")
    _write(catalog_tree, "skills/b.md", f"AP-001 per `{CATALOG.as_posix()}`\n")
    assert _agents_citing_ap_without_catalog(catalog_tree) == ["skills/a.md"]


def test_a_core_reference_in_prose_to_a_deleted_file_is_reported(tmp_path: Path) -> None:
    _write(tmp_path, "skills/a.md",
           "per `{cf-studio-path}/.core/requirements/agent-compliance.md`):\n"
           "LOAD {cf-studio-path}/.core/requirements/storytelling-\n"
           "LOAD {cf-studio-path}/.core/skills/a.md\n")
    assert _dangling_core_refs(tmp_path, Path("skills")) == {
        ("a.md", "requirements/agent-compliance.md"),
    }
