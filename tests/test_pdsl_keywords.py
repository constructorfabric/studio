"""Validate PDSL keyword positions used in instruction prompts."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PROMPT_ROOTS = (
    REPO_ROOT / "skills",
    REPO_ROOT / "workflows",
    REPO_ROOT / "requirements",
    REPO_ROOT / "architecture",
)

# Mirrors the keyword table in architecture/specs/PDSL.md, plus condition
# operators named in that spec.
KNOWN_PDSL_KEYWORDS = {
    "UNIT",
    "PURPOSE",
    "INPUT",
    "OUTPUT",
    "STATE",
    "WHEN",
    "DO",
    "SET",
    "LOAD",
    "RUN",
    "EMIT",
    "EMIT_MENU",
    "MENU",
    "TITLE",
    "OPTIONS",
    "INVALID",
    "WAIT",
    "STOP_TURN",
    "CONTINUE",
    "DISPATCH",
    "RETURN",
    "REQUIRE",
    "RULES",
    "ON_ERROR",
    "INVARIANTS",
    "NOTES",
    "ALWAYS",
    "NEVER",
    "AND",
    "OR",
    "NOT",
    "PATTERNS",
}

FENCE_RE = re.compile(r"^```(?P<lang>[A-Za-z0-9_-]+)?\s*$")
KEYWORD_RE = re.compile(r"^[A-Z][A-Z_-]*$")
SECTION_HEADERS = {
    "PURPOSE",
    "INPUT",
    "OUTPUT",
    "STATE",
    "WHEN",
    "DO",
    "RULES",
    "ON_ERROR",
    "INVARIANTS",
    "NOTES",
    "PATTERNS",
    "TITLE",
    "OPTIONS",
    "INVALID",
}
ACTION_KEYWORDS = {
    "SET",
    "LOAD",
    "RUN",
    "EMIT",
    "EMIT_MENU",
    "WAIT",
    "STOP_TURN",
    "CONTINUE",
    "DISPATCH",
    "RETURN",
    "REQUIRE",
    "NEVER",
}
STATE_KEYWORDS = {"SET"}
WHEN_KEYWORDS = {"REQUIRE", "AND", "OR", "NOT"}
RULE_KEYWORDS = {"ALWAYS", "NEVER"}
DEPRECATED_RULE_KEYWORDS = {"MUST", "MUST_NOT", "SHOULD", "MAY"}
DEPRECATED_KEYWORDS = {
    "FORBID",
    "PARALLEL_DISPATCH",
    "RE-DISPATCH",
    *DEPRECATED_RULE_KEYWORDS,
}


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


def _candidate_tokens(
    line: str,
    section: str | None,
    *,
    allow_continuation: bool = False,
) -> tuple[str | None, list[str], str | None, bool]:
    stripped = line.strip()
    if not stripped or stripped.startswith("//"):
        return section, [], None, False

    indent_len = len(line) - len(line.lstrip(" "))
    if allow_continuation and indent_len > 2:
        return section, [], None, False

    if stripped.startswith("- "):
        item = stripped[2:].strip()
        head = re.match(r"(?P<token>[A-Z][A-Z0-9_-]*)(?=\b|\s|$)", item)
        token = head.group("token") if head else None
        if section == "STATE":
            return section, [token] if token else [], None if token in STATE_KEYWORDS else "STATE", True
        if section == "WHEN":
            return section, [token] if token else [], None if token in WHEN_KEYWORDS else "WHEN", True
        if section == "DO":
            return section, [token] if token else [], None if token in ACTION_KEYWORDS else "DO", True
        if section == "OPTIONS":
            return section, [], None if re.match(r"\d+\b.*->", item) else "OPTIONS", True
        if section in {"RULES", "INVARIANTS"}:
            return section, [token] if token else [], None if token in RULE_KEYWORDS else section, True
        return section, [], None, False

    candidates: list[str] = []

    unit_or_menu = re.match(r"(?P<token>UNIT|MENU)\s+\S+", stripped)
    if unit_or_menu:
        return None, [unit_or_menu.group("token")], None, False

    section_head = re.match(r"(?P<token>[A-Z][A-Z0-9_-]*):(?P<payload>\s*.*)?$", stripped)
    if section_head:
        token = section_head.group("token")
        if token not in SECTION_HEADERS:
            return section, [], None, False
        section = token
        candidates.append(token)
        payload = (section_head.group("payload") or "").strip()
        if token in {"STATE", "WHEN", "DO", "RULES", "INVARIANTS"} and payload:
            return section, candidates, token, False
        return section, candidates, None, False

    if section == "WHEN":
        for operator in re.findall(r"\b(AND|OR|NOT)\b", stripped):
            candidates.append(operator)
        return section, candidates, "WHEN", False

    action_head = re.match(r"(?P<token>[A-Z][A-Z0-9_-]*)(?=\b|\s|$)", stripped)
    if section == "OPTIONS" and "->" in stripped:
        return section, [], None if re.match(r"\d+\b.*->", stripped) else "OPTIONS", True

    if section in {"DO", "OPTIONS", "INVALID", "ON_ERROR"} and action_head:
        token = action_head.group("token")
        if token in ACTION_KEYWORDS | DEPRECATED_KEYWORDS:
            candidates.append(token)

    if "->" in stripped:
        for action in re.findall(r"->\s*([A-Z][A-Z0-9_-]*)(?=\b|\s|$)", stripped):
            if action in ACTION_KEYWORDS | DEPRECATED_KEYWORDS:
                candidates.append(action)

    if section in {"STATE", "DO", "RULES", "INVARIANTS"}:
        return section, candidates, section, False
    if section is None:
        return section, candidates, "UNIT", False
    return section, candidates, None, False


def test_pdsl_blocks_use_known_keywords() -> None:
    """Report PDSL line/action keywords not declared by the current spec allowlist."""
    unknown: dict[str, list[str]] = defaultdict(list)
    invalid_structure: dict[str, list[str]] = defaultdict(list)

    for root in PROMPT_ROOTS:
        for path in sorted(root.rglob("*.md")):
            rel = path.relative_to(REPO_ROOT)
            for block_start, block in _iter_pdsl_blocks(path):
                section: str | None = None
                previous_item_section: str | None = None
                for offset, line in enumerate(block):
                    section, tokens, structure_error, starts_item = _candidate_tokens(
                        line,
                        section,
                        allow_continuation=previous_item_section == section,
                    )
                    if structure_error:
                        invalid_structure[structure_error].append(f"{rel}:{block_start + offset}")
                    previous_item_section = section if starts_item else previous_item_section
                    for token in tokens:
                        if len(token) <= 1:
                            continue
                        if KEYWORD_RE.match(token) and token not in KNOWN_PDSL_KEYWORDS:
                            unknown[token].append(f"{rel}:{block_start + offset}")

    failures: list[str] = []
    failures.extend(
        f"unknown {token}: {', '.join(locations[:12])}"
        + (f" ... (+{len(locations) - 12})" if len(locations) > 12 else "")
        for token, locations in sorted(unknown.items())
    )
    failures.extend(
        f"invalid {section} item: {', '.join(locations[:12])}"
        + (f" ... (+{len(locations) - 12})" if len(locations) > 12 else "")
        for section, locations in sorted(invalid_structure.items())
    )
    assert not failures, "\n".join(failures)
