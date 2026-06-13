"""Validate PDSL prompt blocks through the PDSL CLI."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STUDIO_PY = REPO_ROOT / "skills" / "studio" / "scripts" / "studio.py"

PROMPT_ROOTS = (
    REPO_ROOT / "skills",
    REPO_ROOT / "workflows",
    REPO_ROOT / "requirements",
    REPO_ROOT / "architecture",
)

RUNTIME_PROMPT_ROOTS = (
    REPO_ROOT / "skills" / "studio",
    REPO_ROOT / "workflows",
    REPO_ROOT / "requirements",
    REPO_ROOT / "architecture" / "specs",
)

CF_PATH_RE = re.compile(r"\{cf-studio-path\}/(?P<path>[A-Za-z0-9_./*{}<>:-]+)")

RUNTIME_ACTION_RE = re.compile(
    r"\b("
    r"LOAD|REQUIRE|CONTINUE|ROUTE|OPEN|FOLLOW|READ|DISPATCH|SEE|SEE_ALSO|Canon|"
    r"canonical|defined in|declared in|from|per|owns|loaded|load|follow|open"
    r")\b"
)

SOURCE_EQUIVALENT_CONTEXT_RE = re.compile(
    r"\b("
    r"source-equivalent|target_paths|prompt_targets|code_targets|artifact_targets|"
    r"paths matching|matching:|It is for files such as|source_paths?|"
    r"loaded_by:|parent:|description:|artifact path|output_files|file:"
    r")\b"
)

ALLOWED_CF_ROOTS = (
    ".core/",
    ".gen/",
    "config/",
    ".cache/",
    ".plans/",
    ".debug-skill/",
)

# Runtime-created adapter namespaces. Concrete files inside these directories
# are materialized only at runtime (cache dumps, generated plans, debug-skill
# dumps), so their existence is not guaranteed in a fresh checkout.
RUNTIME_CREATED_CF_ROOTS = (
    ".cache/",
    ".plans/",
    ".debug-skill/",
)

# Bare allowed-root tokens name a canonical adapter *directory* (not a file),
# e.g. a prose mention like "methodology under {cf-studio-path}/.core".
BARE_ALLOWED_CF_ROOTS = frozenset(root.rstrip("/") for root in ALLOWED_CF_ROOTS)

FENCE_RE = re.compile(r"^```(?P<lang>[A-Za-z0-9_-]+)?\s*$")


def _prompt_files() -> list[Path]:
    files: list[Path] = []
    for root in PROMPT_ROOTS:
        files.extend(sorted(root.rglob("*.md")))
    return files


def _runtime_prompt_files() -> list[Path]:
    files: list[Path] = []
    for root in RUNTIME_PROMPT_ROOTS:
        files.extend(sorted(root.rglob("*.md")))
    files.extend(sorted((REPO_ROOT / "skills" / "studio").glob("*.toml")))
    return files


def _runtime_prompt_source_refs() -> set[str]:
    refs: set[str] = set()
    for path in _runtime_prompt_files():
        refs.add(path.relative_to(REPO_ROOT).as_posix())
    return refs


def _cf_reference_has_existing_static_prefix(ref: str) -> bool:
    """Return true when a `{cf-studio-path}` ref targets a known adapter path.

    Template references such as `config/kits/{slug}/SKILL.md` are validated by
    their static prefix because the concrete runtime path is intentionally
    variable.
    """
    if ref in BARE_ALLOWED_CF_ROOTS:
        # A bare allowed-root token (e.g. `.core`, `config`) names a canonical
        # adapter directory rather than a file, so it is always valid.
        return True
    if not ref.startswith(ALLOWED_CF_ROOTS):
        return False
    if ref.startswith(RUNTIME_CREATED_CF_ROOTS):
        # Cache, plan, and debug-skill references are runtime-created
        # namespaces. Their existence is not guaranteed in a fresh checkout or
        # coverage job.
        return True
    if ref.startswith("config/"):
        # Config references may point at optional project/user files. The
        # namespace is canonical even when a concrete file is materialized only
        # after init/update.
        return True
    if ref == ".gen/AGENTS.md":
        return True
    if ref.startswith(".gen/kits/") and any(token in ref for token in ("{", "}", "<", ">")):
        return True

    if ref.startswith(".core/"):
        source_ref = ref.removeprefix(".core/")
        root = REPO_ROOT
    elif ref.startswith(".gen/"):
        root = REPO_ROOT / ".bootstrap"
        source_ref = ref
    else:
        root = REPO_ROOT / ".bootstrap"
        source_ref = ref

    if any(token in ref for token in ("{", "}", "*", "<", ">")):
        static_prefix = re.split(r"[{*<]", source_ref, maxsplit=1)[0].rstrip("/")
        if not static_prefix:
            return True
        static_path = root / static_prefix
        return static_path.exists() or static_path.parent.exists()
    return (root / source_ref).exists()


def _iter_pdsl_blocks(path: Path) -> list[tuple[int, list[str]]]:
    blocks: list[tuple[int, list[str]]] = []
    in_pdsl = False
    start_line = 0
    current: list[str] = []

    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        fence = FENCE_RE.match(line.strip())
        if fence:
            if in_pdsl:
                blocks.append((start_line, current))
                in_pdsl = False
                current = []
            elif (fence.group("lang") or "").lower() == "pdsl":
                in_pdsl = True
                start_line = line_no + 1
                current = []
            continue
        if in_pdsl:
            current.append(line)

    return blocks


def test_prompt_pdsl_blocks_pass_cfs_pdsl_validate() -> None:
    """Prompt PDSL validation is covered by the production `pdsl validate` command."""
    cmd = [
        sys.executable,
        str(STUDIO_PY),
        "pdsl",
        "validate",
        *_prompt_files(),
        "--json",
    ]
    completed = subprocess.run(
        [str(part) for part in cmd],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["command"] == "pdsl validate"
    assert payload["ok"] is True
    assert payload["summary"]["error_count"] == 0
    assert payload["summary"]["fail_count"] == 0
    assert payload["summary"]["finding_count"] == 0


def test_named_pdsl_units_and_menus_are_not_exact_duplicates() -> None:
    """Exact duplicate named PDSL blocks should be defined once and loaded."""
    blocks_by_body: dict[str, list[str]] = defaultdict(list)

    for path in _prompt_files():
        rel = path.relative_to(REPO_ROOT)
        for block_start, block in _iter_pdsl_blocks(path):
            body = "\n".join(line.rstrip() for line in block).strip()
            if not re.search(r"^(UNIT|MENU)\s+\S+", body, re.MULTILINE):
                continue
            blocks_by_body[body].append(f"{rel}:{block_start}")

    duplicates = [
        f"{locations[0]} duplicated at {', '.join(locations[1:])}"
        for locations in blocks_by_body.values()
        if len(locations) > 1
    ]
    assert not duplicates, "\n".join(sorted(duplicates))


def test_pdsl_unit_and_menu_names_are_unique() -> None:
    """PDSL UNIT/MENU names should have a single authoritative definition."""
    definitions: dict[tuple[str, str], list[str]] = defaultdict(list)

    for path in _prompt_files():
        rel = path.relative_to(REPO_ROOT)
        for block_start, block in _iter_pdsl_blocks(path):
            body = "\n".join(block)
            match = re.search(r"^(UNIT|MENU)\s+([^:\n]+):?", body, re.MULTILINE)
            if not match:
                continue
            definitions[(match.group(1), match.group(2).strip())].append(
                f"{rel}:{block_start}"
            )

    duplicates = [
        f"{kind} {name}: {', '.join(locations)}"
        for (kind, name), locations in definitions.items()
        if len(locations) > 1
    ]
    assert not duplicates, "\n".join(sorted(duplicates))


def test_prompt_runtime_references_use_cf_studio_path() -> None:
    """Runtime prompt references must use `{cf-studio-path}` adapter paths.

    The scanner builds the known prompt/runtime path set from canonical source
    files and verifies that prompt instructions reference those files through
    the adapter mirror (`.core`, `.gen`, `config`, `.cache`, `.plans`) unless the
    line is explicitly describing source-equivalent target matching.
    """
    source_refs = _runtime_prompt_source_refs()
    findings: list[str] = []

    for path in _runtime_prompt_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in CF_PATH_RE.finditer(line):
                ref = match.group("path").rstrip("`'\"),.;:")
                if not _cf_reference_has_existing_static_prefix(ref):
                    findings.append(
                        f"{rel}:{line_no}: invalid {{cf-studio-path}} reference `{ref}`"
                    )

            if "{cf-studio-path}" in line:
                continue
            if SOURCE_EQUIVALENT_CONTEXT_RE.search(line):
                continue
            if not RUNTIME_ACTION_RE.search(line):
                continue

            for source_ref in source_refs:
                if source_ref not in line:
                    continue
                findings.append(
                    f"{rel}:{line_no}: bare runtime prompt reference `{source_ref}`; "
                    "use `{cf-studio-path}/.core/...` or mark the line as "
                    "source-equivalent target context"
                )
                break

    assert not findings, "\n".join(sorted(findings))
