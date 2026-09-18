"""Validate PDSL prompt blocks through the PDSL CLI."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from unittest import mock

import pytest

from studio.utils import pdsl

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
PDSL_SECTION_RE = re.compile(
    r"^\s*(UNIT|PURPOSE|INPUT|OUTPUT|STATE|WHEN|DO|MENU\b.*|TITLE|OPTIONS|INVALID|RULES|ON_ERROR|INVARIANTS|NOTES|PATTERNS)\b"
)
PDSL_RULE_ITEM_RE = re.compile(r"^\s*-\s+(ALWAYS|NEVER)\b.*$")
CONDITIONAL_RULE_MARKER_RE = re.compile(
    r"\b("
    r"ONLY\s+WHEN|WHENEVER|WHEN|IF|UNLESS|OTHERWISE|PROVIDED\s+THAT|AS\s+LONG\s+AS|"
    r"only\s+when|whenever|when|if|unless|otherwise|provided\s+that|as\s+long\s+as"
    r")\b"
)

CONDITIONAL_RULE_ROOTS = (
    REPO_ROOT / "workflows",
    REPO_ROOT / "skills" / "studio" / "modules",
)

CONDITIONAL_RULE_EXEMPTIONS = {
    REPO_ROOT / "skills" / "studio" / "modules" / "runtime" / "pdsl-execution-card.md",
    REPO_ROOT / "workflows" / "code-planning.md",
    REPO_ROOT / "workflows" / "coding-gen.md",
    REPO_ROOT / "workflows" / "planning.md",
}

PDSL_EXECUTION_CARD_LOAD = (
    "LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/pdsl-execution-card.md"
)
PDSL_EXECUTION_CARD_REMEMBER_LOAD = (
    "LOAD and REMEMBER rules from "
    "{cf-studio-path}/.core/skills/studio/modules/runtime/pdsl-execution-card.md"
)
PDSL_EXECUTION_CARD_BOOTSTRAP_HELPERS = (
    "RUN WorkflowBootstrapRouterPrelude",
    "RUN WorkflowBootstrapCoreSession",
    "RUN WorkflowBootstrapSimpleModeGate",
)

THIN_ENTRYPOINT_EXECUTION_CARD_EXEMPTIONS = {
    REPO_ROOT / "workflows" / "code-planning.md",
    REPO_ROOT / "workflows" / "coding-fix.md",
    REPO_ROOT / "workflows" / "coding-review.md",
    REPO_ROOT / "workflows" / "coding-tests.md",
    REPO_ROOT / "workflows" / "coding.md",
    REPO_ROOT / "workflows" / "docs-ci.md",
    REPO_ROOT / "workflows" / "docs-planning.md",
    REPO_ROOT / "workflows" / "docs-review.md",
    REPO_ROOT / "workflows" / "documenting-fix.md",
    REPO_ROOT / "workflows" / "documenting-planning.md",
    REPO_ROOT / "workflows" / "documenting-review.md",
    REPO_ROOT / "workflows" / "kit-ci.md",
    REPO_ROOT / "workflows" / "kit-fix.md",
    REPO_ROOT / "workflows" / "kit-planning.md",
    REPO_ROOT / "workflows" / "kit-review.md",
    REPO_ROOT / "workflows" / "prompting-fix.md",
    REPO_ROOT / "workflows" / "prompting-planning.md",
    REPO_ROOT / "workflows" / "prompting-review.md",
    REPO_ROOT / "workflows" / "skills-ci.md",
    REPO_ROOT / "workflows" / "skills-planning.md",
    REPO_ROOT / "workflows" / "skills-review.md",
    REPO_ROOT / "workflows" / "testing.md",
    REPO_ROOT / "workflows" / "write-docs.md",
    REPO_ROOT / "workflows" / "write-skills.md",
}

ALLOWED_DUPLICATE_PDLS = {
    ("UNIT", "CodingReviewFixGate"),
    ("UNIT", "CodingValidate"),
    ("UNIT", "ThinSkillAssumptionContract"),
    ("UNIT", "ThinSkillBlockedContract"),
    ("UNIT", "ThinSkillModuleFirstLaw"),
    ("UNIT", "ThinSkillResultEnvelopeContract"),
    ("UNIT", "WriteDocsReviewFixGate"),
    ("UNIT", "WriteDocsValidate"),
    ("UNIT", "WriteSkillsFixGate"),
    ("UNIT", "WriteSkillsValidate"),
}


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


def _conditional_rules_in_block(path: Path, block_start: int, block: list[str]) -> list[str]:
    failures: list[str] = []
    in_rules = False
    current: list[tuple[int, str]] = []

    def is_rules_start(line: str) -> bool:
        section = PDSL_SECTION_RE.match(line)
        if not section or line.lstrip().startswith("-"):
            return False
        return section.group(1).split()[0] == "RULES"

    def is_non_rules_section(line: str) -> bool:
        section = PDSL_SECTION_RE.match(line)
        if not section or line.lstrip().startswith("-"):
            return False
        return section.group(1).split()[0] in {
            "UNIT", "PURPOSE", "INPUT", "OUTPUT", "STATE", "WHEN", "DO", "MENU",
            "TITLE", "OPTIONS", "INVALID", "ON_ERROR", "INVARIANTS", "NOTES", "PATTERNS",
        }

    def flush_current() -> None:
        if not current:
            return
        text = " ".join(line.strip() for _, line in current)
        match = CONDITIONAL_RULE_MARKER_RE.search(text)
        if match:
            line_no = next(
                (line_no for line_no, line in current if CONDITIONAL_RULE_MARKER_RE.search(line)),
                current[0][0],
            )
            rel = path.relative_to(REPO_ROOT)
            failures.append(f"{rel}:{line_no}: conditional marker `{match.group(0)}` in RULES item: {text}")

    def start_rule_item(line_no: int, line: str) -> None:
        nonlocal current
        flush_current()
        current = [(line_no, line)]

    def extend_or_flush_current(line_no: int, line: str) -> None:
        nonlocal current
        if current and (not line.strip() or line.startswith((" ", "\t"))):
            current.append((line_no, line))
            return
        if current:
            flush_current()
            current = []

    for offset, line in enumerate(block):
        line_no = block_start + offset
        if is_rules_start(line):
            flush_current()
            current = []
            in_rules = True
            continue
        if is_non_rules_section(line):
            if in_rules:
                flush_current()
            current = []
            in_rules = False
            continue
        if not in_rules:
            continue
        if PDSL_RULE_ITEM_RE.match(line):
            start_rule_item(line_no, line)
            continue
        extend_or_flush_current(line_no, line)

    if in_rules:
        flush_current()
    return failures


# Known PDSL600/PDSL601 (DO/RULES compactness cap) and PDSL200 (dashless
# starter-keyword) findings across pre-existing prompt content. TK-02 made the
# cap and starter-keyword check apply uniformly regardless of dash usage,
# which surfaced that the current thresholds/vocabulary don't fit this corpus
# yet — tracked in https://github.com/constructorfabric/studio/issues/87.
#
# Only the rule_ids listed here are tolerated, and only for the listed file:
# any new file, or any new rule_id on an already-listed file, still fails this
# test. As files get fixed (narrower units, or a threshold/vocabulary change
# lands), remove their entries so this map keeps shrinking toward empty.
KNOWN_PDSL_CAP_VIOLATIONS: dict[str, set[str]] = {
    "requirements/auto-config.md": {'PDSL600', 'PDSL601'},
    "requirements/bug-finding.md": {'PDSL601'},
    "requirements/code-checklist.md": {'PDSL601'},
    "requirements/plan-decomposition.md": {'PDSL601'},
    "requirements/plan-template.md": {'PDSL601'},
    "requirements/prompt-bug-finding.md": {'PDSL600', 'PDSL601'},
    "requirements/prompt-engineering.md": {'PDSL601'},
    "requirements/storytelling-dimensions.md": {'PDSL601'},
    "requirements/storytelling-modes.md": {'PDSL600', 'PDSL601'},
    "requirements/storytelling-phases.md": {'PDSL601'},
    "requirements/storytelling-preferences.md": {'PDSL600', 'PDSL601'},
    "requirements/storytelling-shared.md": {'PDSL600', 'PDSL601'},
    "requirements/storytelling.md": {'PDSL601'},
    "skills/studio/SKILL.md": {'PDSL200', 'PDSL600', 'PDSL601'},
    "skills/studio/agents/author-production-rules.md": {'PDSL601'},
    "skills/studio/agents/cf-analyze-planner.md": {'PDSL601'},
    "skills/studio/agents/cf-brainstorm-expert.md": {'PDSL601'},
    "skills/studio/agents/cf-brainstorm-facilitator.md": {'PDSL601'},
    "skills/studio/agents/cf-brainstorm-panel.md": {'PDSL601'},
    "skills/studio/agents/cf-codegen.md": {'PDSL601'},
    "skills/studio/agents/cf-diff-scope-resolver.md": {'PDSL600'},
    "skills/studio/agents/cf-explorer.md": {'PDSL601'},
    "skills/studio/agents/cf-generate-author-worker.md": {'PDSL601'},
    "skills/studio/agents/cf-generate-author.md": {'PDSL601'},
    "skills/studio/agents/cf-generate-planner.md": {'PDSL601'},
    "skills/studio/agents/cf-migrate-scanner.md": {'PDSL601'},
    "skills/studio/agents/cf-migrate-verifier.md": {'PDSL600'},
    "skills/studio/agents/cf-pdsl-author.md": {'PDSL601'},
    "skills/studio/agents/cf-pdsl-reviewer.md": {'PDSL601'},
    "skills/studio/agents/cf-pdsl-transformer.md": {'PDSL601'},
    "skills/studio/agents/cf-phase-compiler.md": {'PDSL601'},
    "skills/studio/agents/cf-phase-runner.md": {'PDSL601'},
    "skills/studio/agents/cf-pr-review.md": {'PDSL601'},
    "skills/studio/agents/cf-ralphex.md": {'PDSL601'},
    "skills/studio/agents/cf-semantic-reviewer-artifact.md": {'PDSL600', 'PDSL601'},
    "skills/studio/agents/cf-semantic-reviewer-code.md": {'PDSL601'},
    "skills/studio/agents/cf-semantic-reviewer-consistency.md": {'PDSL601'},
    "skills/studio/agents/cf-semantic-reviewer-freeform.md": {'PDSL600', 'PDSL601'},
    "skills/studio/agents/cf-semantic-reviewer-prompt.md": {'PDSL601'},
    "skills/studio/agents/storytelling-context-pack.md": {'PDSL601'},
    "skills/studio/agents/storytelling-export.md": {'PDSL600', 'PDSL601'},
    "skills/studio/agents/storytelling-gate.md": {'PDSL600'},
    "skills/studio/agents/storytelling-preflight.md": {'PDSL601'},
    "skills/studio/agents/storytelling-wrap.md": {'PDSL600', 'PDSL601'},
    "skills/studio/migrate-from-cypilot.md": {'PDSL600', 'PDSL601'},
    "skills/studio/modules/auto-config-scan-docs.md": {'PDSL200', 'PDSL600'},
    "skills/studio/modules/brainstorm-rounds.md": {'PDSL600', 'PDSL601'},
    "skills/studio/modules/brainstorm-wrap.md": {'PDSL601'},
    "skills/studio/modules/brave-new-world-choice.md": {'PDSL601'},
    "skills/studio/modules/brave-new-world-eligibility.md": {'PDSL601'},
    "skills/studio/modules/ci-discovery-run.md": {'PDSL200', 'PDSL601'},
    "skills/studio/modules/coding-review-setup-run.md": {'PDSL600'},
    "skills/studio/modules/debug-prompts-locators.md": {'PDSL601'},
    "skills/studio/modules/explain-export-completion.md": {'PDSL601'},
    "skills/studio/modules/explain-gates.md": {'PDSL200', 'PDSL600', 'PDSL601'},
    "skills/studio/modules/explore-entry.md": {'PDSL600', 'PDSL601'},
    "skills/studio/modules/explore-next-dispatch.md": {'PDSL601'},
    "skills/studio/modules/explore-run.md": {'PDSL601'},
    "skills/studio/modules/explore-save.md": {'PDSL600', 'PDSL601'},
    "skills/studio/modules/gates/plan-first.md": {'PDSL600', 'PDSL601'},
    "skills/studio/modules/gates/simple-mode-rules.md": {'PDSL601'},
    "skills/studio/modules/gates/simple-mode.md": {'PDSL600'},
    "skills/studio/modules/gates/workflow-prep.md": {'PDSL600'},
    "skills/studio/modules/kit-bootstrap-runtime.md": {'PDSL600'},
    "skills/studio/modules/kit-discovery-proposal.md": {'PDSL601'},
    "skills/studio/modules/kit-discovery-run.md": {'PDSL200'},
    "skills/studio/modules/kit-edit-flow.md": {'PDSL601'},
    "skills/studio/modules/kit-entry-router.md": {'PDSL600'},
    "skills/studio/modules/kit-legacy-preview-flow.md": {'PDSL601'},
    "skills/studio/modules/kit-target-validation.md": {'PDSL600'},
    "skills/studio/modules/kit-thin-domain-routing.md": {'PDSL600'},
    "skills/studio/modules/map-config-assist.md": {'PDSL600'},
    "skills/studio/modules/map-preflight.md": {'PDSL600'},
    "skills/studio/modules/plan-assess-decompose.md": {'PDSL600'},
    "skills/studio/modules/plan-compiler-dispatch.md": {'PDSL600'},
    "skills/studio/modules/plan-native-dispatch.md": {'PDSL200', 'PDSL600', 'PDSL601'},
    "skills/studio/modules/plan-validate-finalize.md": {'PDSL600'},
    "skills/studio/modules/planning-runtime.md": {'PDSL200'},
    "skills/studio/modules/review/finding-contract.md": {'PDSL601'},
    "skills/studio/modules/review/fix-approval.md": {'PDSL601'},
    "skills/studio/modules/review/semantic-loop-skeleton.md": {'PDSL601'},
    "skills/studio/modules/routing/companion-skills.md": {'PDSL601'},
    "skills/studio/modules/routing/root-intent-routing.md": {'PDSL601'},
    "skills/studio/modules/runtime/active-workflow-state-law.md": {'PDSL601'},
    "skills/studio/modules/runtime/artifact-contract-load.md": {'PDSL601'},
    "skills/studio/modules/runtime/blocked-next-actions.md": {'PDSL601'},
    "skills/studio/modules/runtime/blocked-report.md": {'PDSL601'},
    "skills/studio/modules/runtime/ci-report-render.md": {'PDSL601'},
    "skills/studio/modules/runtime/commit-preflight-check.md": {'PDSL601'},
    "skills/studio/modules/runtime/context-memory.md": {'PDSL601'},
    "skills/studio/modules/runtime/design-input-check.md": {'PDSL600'},
    "skills/studio/modules/runtime/findings-render.md": {'PDSL600', 'PDSL601'},
    "skills/studio/modules/runtime/pdsl-execution-card.md": {'PDSL601'},
    "skills/studio/modules/runtime/prerequisite-check.md": {'PDSL601'},
    "skills/studio/modules/runtime/required-bootstrap.md": {'PDSL600', 'PDSL601'},
    "skills/studio/modules/runtime/resource-context-check.md": {'PDSL600'},
    "skills/studio/modules/runtime/skill-io-contract-load.md": {'PDSL600'},
    "skills/studio/modules/runtime/thin-skill-contracts.md": {'PDSL600', 'PDSL601'},
    "skills/studio/modules/runtime/workflow-resolution.md": {'PDSL200', 'PDSL601'},
    "skills/studio/modules/session/shutdown.md": {'PDSL601'},
    "skills/studio/modules/subagents/dispatch.md": {'PDSL601'},
    "skills/studio/modules/subagents/git-commit-mode.md": {'PDSL601'},
    "skills/studio/modules/ui/next-actions.md": {'PDSL601'},
    "skills/studio/modules/ui/skill-invocation-art.md": {'PDSL200', 'PDSL601'},
    "skills/studio/modules/workspace-router-quick.md": {'PDSL600', 'PDSL601'},
    "skills/studio/modules/workspace-validate.md": {'PDSL600'},
    "skills/studio/modules/write-docs-author-dispatch.md": {'PDSL600'},
    "skills/studio/modules/write-docs-completion.md": {'PDSL600', 'PDSL601'},
    "skills/studio/modules/write-docs-execution-refs.md": {'PDSL600'},
    "skills/studio/modules/write-docs-review-setup.md": {'PDSL200', 'PDSL600'},
    "skills/studio/modules/write-docs-write-policy-fix.md": {'PDSL200'},
    "skills/studio/modules/write-skills-author-dispatch.md": {'PDSL200'},
    "skills/studio/modules/write-skills-completion.md": {'PDSL600', 'PDSL601'},
    "skills/studio/modules/write-skills-fix-outcomes.md": {'PDSL600'},
    "skills/studio/modules/write-skills-review-run-fix.md": {'PDSL600'},
    "workflows/analyze.md": {'PDSL600'},
    "workflows/auto-config.md": {'PDSL600', 'PDSL601'},
    "workflows/brainstorm.md": {'PDSL600', 'PDSL601'},
    "workflows/brave-new-world.md": {'PDSL600', 'PDSL601'},
    "workflows/coding-ci.md": {'PDSL600'},
    "workflows/coding-fix.md": {'PDSL600', 'PDSL601'},
    "workflows/coding-review.md": {'PDSL200'},
    "workflows/documenting-ci.md": {'PDSL600'},
    "workflows/documenting-fix.md": {'PDSL600', 'PDSL601'},
    "workflows/documenting-gen.md": {'PDSL600'},
    "workflows/explain.md": {'PDSL600', 'PDSL601'},
    "workflows/explore.md": {'PDSL600', 'PDSL601'},
    "workflows/generate.md": {'PDSL600'},
    "workflows/git-commit.md": {'PDSL200', 'PDSL600'},
    "workflows/help.md": {'PDSL200'},
    "workflows/kit-ci.md": {'PDSL600'},
    "workflows/kit-fix.md": {'PDSL600'},
    "workflows/kit-gen.md": {'PDSL600'},
    "workflows/kit-planning.md": {'PDSL600'},
    "workflows/kit-review.md": {'PDSL600'},
    "workflows/kit.md": {'PDSL600', 'PDSL601'},
    "workflows/map.md": {'PDSL600', 'PDSL601'},
    "workflows/plan.md": {'PDSL600', 'PDSL601'},
    "workflows/prompting-ci.md": {'PDSL600'},
    "workflows/prompting-fix.md": {'PDSL600', 'PDSL601'},
    "workflows/prompting-gen.md": {'PDSL600'},
    "workflows/prompting-review.md": {'PDSL600'},
    "workflows/studio.md": {'PDSL200'},
    "workflows/workspace.md": {'PDSL600', 'PDSL601'},
}


def test_prompt_pdsl_blocks_pass_cfs_pdsl_validate() -> None:
    """Prompt PDSL validation is covered by the production `pdsl validate` command.

    Findings already tracked in KNOWN_PDSL_CAP_VIOLATIONS (see issue #87) are
    excluded from the pass/fail decision below, but only for the exact
    (file, rule_id) pairs already recorded — anything else still fails.
    """
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

    payload = json.loads(completed.stdout)
    assert payload["command"] == "pdsl validate"
    assert payload["summary"]["error_count"] == 0, completed.stdout

    unexpected: list[str] = []
    for result in payload["results"]:
        rel = Path(result["source"]).relative_to(REPO_ROOT).as_posix()
        allowed = KNOWN_PDSL_CAP_VIOLATIONS.get(rel, set())
        for finding in result["findings"]:
            if finding["rule_id"] not in allowed:
                unexpected.append(f"{rel}:{finding['line']} {finding['rule_id']} {finding['message']}")

    assert not unexpected, (
        "New/unexpected PDSL findings not tracked in issue #87:\n" + "\n".join(unexpected)
    )


def test_workflow_and_module_rules_are_unconditional() -> None:
    """RULES in workflow/module prompts should not encode IF/WHEN-style branches."""
    failures: list[str] = []

    for root in CONDITIONAL_RULE_ROOTS:
        for path in sorted(root.rglob("*.md")):
            if path in CONDITIONAL_RULE_EXEMPTIONS:
                continue
            for block_start, block in _iter_pdsl_blocks(path):
                failures.extend(_conditional_rules_in_block(path, block_start, block))

    assert not failures, "\n".join(failures)


def test_pdsl_workflows_load_execution_card_during_bootstrap() -> None:
    """Every PDSL workflow must load the runtime semantics card in bootstrap."""
    failures: list[str] = []

    for path in sorted((REPO_ROOT / "workflows").glob("*.md")):
        if path in THIN_ENTRYPOINT_EXECUTION_CARD_EXEMPTIONS:
            continue
        blocks = _iter_pdsl_blocks(path)
        if not blocks:
            continue
        executable_blocks = [
            (block_start, block)
            for block_start, block in blocks
            if re.search(r"^DO:", "\n".join(block), re.MULTILINE)
        ]
        if not executable_blocks:
            continue
        block_start, block = executable_blocks[0]
        body = "\n".join(block)
        if (
            PDSL_EXECUTION_CARD_LOAD not in body
            and not any(helper in body for helper in PDSL_EXECUTION_CARD_BOOTSTRAP_HELPERS)
        ):
            rel = path.relative_to(REPO_ROOT)
            failures.append(
                f"{rel}:{block_start}: first executable PDSL block must load "
                "modules/runtime/pdsl-execution-card.md during bootstrap or run a bootstrap helper that loads it"
            )

    root_skill = REPO_ROOT / "skills" / "studio" / "SKILL.md"
    root_blocks = _iter_pdsl_blocks(root_skill)
    root_body = "\n".join(root_blocks[0][1]) if root_blocks else ""
    if PDSL_EXECUTION_CARD_REMEMBER_LOAD not in root_body:
        failures.append(
            "skills/studio/SKILL.md: first PDSL block must load and remember "
            "modules/runtime/pdsl-execution-card.md during router bootstrap"
        )

    assert not failures, "\n".join(failures)


def test_mode_change_trigger_is_disjoint_from_brave_new_world_phrases() -> None:
    """ADR-0023 prerequisite 1: the declared mode-change trigger set must
    never overlap the Brave New World overlay's open-ended activation
    phrases, or a user saying one could be silently read as the other.

    Checked case-insensitively and for substring/superset overlap in either
    direction, not just exact list membership -- SimpleModeChangeTrigger's own
    contract rejects "a paraphrase, synonym, punctuation-padded variant, or
    superset phrase", so this test rejects the same shapes of collision. The
    activation-phrase and exclusion lines are both read only from inside
    BraveNewWorldActivate's own PDSL block, not a flat file-wide scan.
    """
    simple_mode_path = REPO_ROOT / "skills/studio/modules/gates/simple-mode.md"
    bnw_path = REPO_ROOT / "workflows/brave-new-world.md"
    simple_mode_text = simple_mode_path.read_text()

    trigger = "change mode"
    assert f'"{trigger}"' in simple_mode_text, (
        "Expected the literal mode-change trigger phrase to still be declared "
        "in gates/simple-mode.md; update this test if the wording changed."
    )

    bnw_activate_block = next(
        (
            block for _, block in _iter_pdsl_blocks(bnw_path)
            if block and block[0].strip() == "UNIT BraveNewWorldActivate"
        ),
        None,
    )
    assert bnw_activate_block is not None, (
        "Expected a UNIT BraveNewWorldActivate PDSL block in "
        "workflows/brave-new-world.md; update this test if it moved or was renamed."
    )

    activation_line = next(
        (line for line in bnw_activate_block if "ALWAYS resolve semantically equivalent phrases" in line),
        None,
    )
    assert activation_line is not None, (
        "Expected BraveNewWorldActivate's activation-phrase rule inside its own "
        "block; update this test if the wording moved."
    )
    bnw_phrases = [phrase.lower() for phrase in re.findall(r"'([^']+)'", activation_line)]
    assert bnw_phrases, "Expected quoted activation phrases on that rule line"

    exclusion_line = next(
        (
            line for line in bnw_activate_block
            if "NEVER treat the exact phrase" in line and trigger in line.lower()
        ),
        None,
    )
    assert exclusion_line is not None, (
        "Expected an explicit NEVER rule in BraveNewWorldActivate excluding the "
        "literal mode-change trigger phrase from BNW activation; update this "
        "test if that exclusion moved or was reworded."
    )

    for phrase in bnw_phrases:
        assert trigger != phrase, (
            f"Mode-change trigger {trigger!r} exactly matches a BNW activation phrase {phrase!r}."
        )
        assert trigger not in phrase, (
            f"Mode-change trigger {trigger!r} is a substring of BNW phrase {phrase!r}; "
            "ADR-0023 requires these trigger sets to be disjoint, including supersets."
        )
        assert phrase not in trigger, (
            f"BNW phrase {phrase!r} is a substring of the mode-change trigger {trigger!r}."
        )


def test_declared_gate_type_carveout_is_defined_once_and_cross_referenced() -> None:
    """The declared mode/gate-type carve-out is defined canonically in
    pdsl-execution-card.md; active-workflow-state-law.md must reference that
    definition rather than silently restate it, so the two wordings can't
    drift apart unnoticed (PR #162 review finding).
    """
    card_text = (REPO_ROOT / "skills/studio/modules/runtime/pdsl-execution-card.md").read_text()
    law_text = (REPO_ROOT / "skills/studio/modules/runtime/active-workflow-state-law.md").read_text()

    assert "a gate's declared risk type" in card_text
    assert "NEVER treat a runtime-derived eligibility or risk classification" in card_text
    assert "cpt-studio-adr-autonomous-default-and-gate-risk" in card_text, (
        "Expected the carve-out's NOTES to cite ADR-0023, so a reader knows "
        "this rule is a currently-inert prerequisite, not an implemented "
        "resolution mechanism (PR #162 review finding)."
    )
    assert "restated for workflow-state law in\n  `runtime/active-workflow-state-law.md`" in card_text

    assert (
        "the canonical definition of that carve-out lives in `runtime/pdsl-execution-card.md`"
        in law_text
    ), (
        "Expected active-workflow-state-law.md's declared-type carve-out to "
        "cross-reference pdsl-execution-card.md rather than restate it with no link."
    )


def test_active_workflow_state_law_skip_audit_and_mode_persistence_rules_present() -> None:
    """Regression lock for the normative additions to active-workflow-state-law.md
    that otherwise had zero test coverage: the skip redefinition, the
    audit-record requirement, and the mode-persistence rule -- which must both
    name and actually dispatch to SimpleModeChangeTrigger, or the rule points
    at a unit nothing ever reaches (PR #162 review findings).
    """
    law_text = (REPO_ROOT / "skills/studio/modules/runtime/active-workflow-state-law.md").read_text()

    assert "A skip is bypassing a gate without a resolution" in law_text
    assert "permitted by its statically declared type" in law_text
    assert "ALWAYS produce the required audit record for every permitted autonomous" in law_text
    assert "NEVER treat a reply as a mode reset" in law_text
    assert "SimpleModeChangeTrigger" in law_text, (
        "Expected the mode-persistence rule to name SimpleModeChangeTrigger "
        "specifically (not the SimpleModeChoice menu) -- that unit is what "
        "actually implements the declared trigger set."
    )
    assert "RUN SimpleModeChangeTrigger from `gates/simple-mode.md`" in law_text, (
        "Expected the message-mapping rule to explicitly dispatch to "
        "SimpleModeChangeTrigger; otherwise it is declared but unreachable "
        "from any active workflow state (PR #162 review finding)."
    )


def test_simple_mode_change_trigger_contract_is_fully_declared() -> None:
    """Regression lock for SimpleModeChangeTrigger's full matching contract --
    exact match, ASCII case-folding, whitespace trimming, and rejection of
    paraphrases/synonyms/superset phrases -- not just its trigger phrase
    (PR #162 review finding: the prior test covered only BNW disjointness).
    """
    simple_mode_text = (REPO_ROOT / "skills/studio/modules/gates/simple-mode.md").read_text()

    unit_start = simple_mode_text.index("UNIT SimpleModeChangeTrigger")
    unit_text = simple_mode_text[unit_start:]

    assert "folding ASCII case" in unit_text
    assert "trimming leading/trailing whitespace" in unit_text
    assert "not a paraphrase, synonym, punctuation-padded variant, or superset phrase" in unit_text
    assert (
        "NEVER treat semantically similar phrases, synonyms, or partial matches as satisfying it"
        in unit_text
    )


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
        and (kind, name) not in ALLOWED_DUPLICATE_PDLS
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


# Every MENU that does not yet declare a gate risk TYPE, frozen 2026-09-07.
# `blocking` is the *intended* contract for an undeclared gate, not what happens
# today: three shipped paths still resolve one by runtime judgement, so this set
# freezes the existing untyped inventory rather than recording a fail-closed
# default. The surface migrates gate by gate and must not grow -- anything not in
# this set has to declare a TYPE.
# Shrink this set as menus are typed; never add to it.
UNTYPED_MENU_BASELINE: frozenset[str] = frozenset({
    "architecture/specs/PDSL.md#13::SubAgentApprovalMenu",
    "architecture/specs/PDSL.md#7::ApprovalMenu",
    "requirements/auto-config.md#2::ExistingRulesRefreshMenu",
    "requirements/storytelling-modes.md#0::ModeSelectionMenu",
    "requirements/storytelling-modes.md#5::ChallengePostRoundMenu",
    "requirements/storytelling-modes.md#5::ChallengeReactionMenu",
    "skills/studio/agents/cf-code-bug-finder.md#3::TerminalStates",
    "skills/studio/agents/cf-generate-author.md#1::DomainClassification",
    "skills/studio/agents/cf-migrate-migrator.md#3::SpecialCaseAItems",
    "skills/studio/agents/cf-migrate-planner.md#0::FindingClassification",
    "skills/studio/agents/cf-prompt-bug-finder.md#3::TerminalStates",
    "skills/studio/agents/cf-ralphex.md#2::DelegationOutcomeMenu",
    "skills/studio/agents/cf-ralphex.md#4::BootstrapApprovalMenu",
    "skills/studio/agents/cf-ralphex.md#4::RetryOrAbortMenu",
    "skills/studio/agents/cf-semantic-reviewer-code.md#2::OutputShape",
    "skills/studio/agents/cf-semantic-reviewer-consistency.md#3::FindingClassificationRules",
    "skills/studio/agents/storytelling-gate.md#4::GenerateRoutingMenu",
    "skills/studio/agents/storytelling-gate.md#6::PlanApprovalMenu",
    "skills/studio/migrate-from-cypilot.md#4::E1_ScannerMenu",
    "skills/studio/migrate-from-cypilot.md#5::E2_PlannerMenu",
    "skills/studio/migrate-from-cypilot.md#6::E3_MigratorMenu",
    "skills/studio/migrate-from-cypilot.md#7::E4_VerifierMenu",
    "skills/studio/migrate-from-cypilot.md#8::E5_MigratorMenu",
    "skills/studio/modules/analyze-routing-menus.md#1::AnalyzeIntentOffer",
    "skills/studio/modules/analyze-routing-menus.md#2::AnalyzeLoadOffer",
    "skills/studio/modules/analyze-skill-fallbacks.md#0::AnalyzeOtherSkillsMenu",
    "skills/studio/modules/analyze-skill-fallbacks.md#1::AnalyzeNoMatchMenu",
    "skills/studio/modules/auto-config-detect.md#0::DetectConfirmMenu",
    "skills/studio/modules/auto-config-docs.md#0::DocsConfirmMenu",
    "skills/studio/modules/auto-config-generate.md#0::GenerateConfirmMenu",
    "skills/studio/modules/auto-config-integrate-validate.md#0::IntegrateConfirmMenu",
    "skills/studio/modules/auto-config-precheck.md#0::ExistingRulesRefreshMenu",
    "skills/studio/modules/auto-config-scan-docs.md#0::ScanConfirmMenu",
    "skills/studio/modules/brainstorm-panel-render.md#0::PanelEditMenu",
    "skills/studio/modules/brainstorm-rounds.md#0::PostRoundMenu",
    "skills/studio/modules/brainstorm-rounds.md#0::QuestionMenu",
    "skills/studio/modules/brainstorm-wrap.md#0::WrapMenu",
    "skills/studio/modules/ci-discovery-run.md#0::CiDiscoveryFailureMenu",
    "skills/studio/modules/ci-discovery-run.md#0::CiDiscoverySkipMenu",
    "skills/studio/modules/coding-prep-gates.md#0::CodingExploreMenu",
    "skills/studio/modules/coding-prep-gates.md#1::CodingBrainstormMenu",
    "skills/studio/modules/debug-prompts-command-menu-nav.md#0::DebuggerMenu",
    "skills/studio/modules/debug-prompts-failures.md#0::DebugRunFailureMenu",
    "skills/studio/modules/debug-prompts-failures.md#0::DebugStepFailureMenu",
    "skills/studio/modules/explain-intent-explore.md#2::ExplainExploreMenu",
    "skills/studio/modules/explore-clarify.md#0::ExploreClarifyMenu",
    "skills/studio/modules/explore-save.md#0::ExploreSaveMenu",
    "skills/studio/modules/gates/migrate-from-cypilot-offer.md#0::MigrateFromCypilotConfirm",
    "skills/studio/modules/gates/plan-first.md#0::PlanFirstConfirm",
    "skills/studio/modules/gates/plan-first.md#1::PlanStorageChoice",
    "skills/studio/modules/gates/simple-mode-simple.md#2::SimpleModeBraveNewWorldChoice",
    "skills/studio/modules/gates/simple-mode.md#0::SimpleModeChoice",
    "skills/studio/modules/gates/workflow-prep.md#1::WorkflowPrepExploreRepeatMenu",
    "skills/studio/modules/generate-routing-menus.md#1::GenerateIntentOffer",
    "skills/studio/modules/generate-routing-menus.md#2::GenerateLoadOffer",
    "skills/studio/modules/generate-skill-fallbacks.md#0::GenerateOtherSkillsMenu",
    "skills/studio/modules/generate-skill-fallbacks.md#1::GenerateNoMatchMenu",
    "skills/studio/modules/kit-discovery-proposal.md#0::KitInitDiscoveryApprovalMenu",
    "skills/studio/modules/kit-discovery-run.md#0::KitInitDiscoveryFailureMenu",
    "skills/studio/modules/kit-edit-render.md#0::KitInitEditRetryMenu",
    "skills/studio/modules/kit-existing-manifest.md#0::KitInitExistingManifestMenu",
    "skills/studio/modules/kit-legacy-preview-menus.md#0::KitInitLegacyApprovalMenu",
    "skills/studio/modules/kit-legacy-preview-menus.md#0::KitInitPreviewFailureMenu",
    "skills/studio/modules/kit-manual-guidance-preview.md#0::KitInitManualGuidanceRetryMenu",
    "skills/studio/modules/kit-target-entry.md#0::KitInitTargetMenu",
    "skills/studio/modules/kit-target-preflight-route.md#0::KitInitTargetRetryMenu",
    "skills/studio/modules/kit-target-validation.md#0::KitInitValidationFailureMenu",
    "skills/studio/modules/map-config-palette.md#0::ConfigAssistActionMenu",
    "skills/studio/modules/map-config-palette.md#0::PaletteMenu",
    "skills/studio/modules/map-config-palette.md#0::UncategorizedMenu",
    "skills/studio/modules/map-execute.md#0::ConfigAssistOfferMenu",
    "skills/studio/modules/map-execute.md#0::MapConfigMenu",
    "skills/studio/modules/map-intent.md#0::MapIntentMenu",
    "skills/studio/modules/map-next.md#0::MapNextStepsMenu",
    "skills/studio/modules/map-preflight.md#2::MapScopeMenu",
    "skills/studio/modules/plan-compiler-dispatch.md#2::PlanCompilerFailureMenu",
    "skills/studio/modules/plan-discovery.md#1::PlanGateMenu",
    "skills/studio/modules/plan-validate-finalize.md#0::OversizedPhaseRecoveryMenu",
    "skills/studio/modules/plan-validate-finalize.md#1::Phase4NextStepsMenu",
    "skills/studio/modules/planning-runtime.md#8::PlanSaveGateMenu",
    "skills/studio/modules/review/fix-approval.md#0::ReviewFindingsNavigation",
    "skills/studio/modules/review/fix-approval.md#12::ReviewFixPartialIdsRetryMenu",
    "skills/studio/modules/review/fix-approval.md#3::ReviewFixScope",
    "skills/studio/modules/review/semantic-loop-skeleton.md#0::ReviewGranularityMenu",
    "skills/studio/modules/routing/companion-skills.md#1::CompanionSkillOfferMenu",
    "skills/studio/modules/routing/companion-skills.md#2::CompanionRoutingMenuOptions",
    "skills/studio/modules/routing/root-intent-routing.md#1::IntentSkillMenu",
    "skills/studio/modules/routing/root-intent-routing.md#1::MatchedIntentSkillMenu",
    "skills/studio/modules/routing/root-intent-routing.md#9::AllCfSkillsMenu",
    "skills/studio/modules/runtime/blocked-next-actions.md#2::BlockedNextActionsMenu",
    "skills/studio/modules/session/shutdown.md#0::StudioShutdownConfirm",
    "skills/studio/modules/subagents/dispatch.md#1::SubAgentApprovalRequest",
    "skills/studio/modules/subagents/dispatch.md#1::SubAgentFallbackLimitRequest",
    "skills/studio/modules/subagents/dispatch.md#1::SubAgentFallbackRequest",
    "skills/studio/modules/subagents/git-commit-mode.md#5::GitCommitModeMenu",
    "skills/studio/modules/ui/next-actions.md#0::NextActionsMenu",
    "skills/studio/modules/workspace-configure.md#0::SourceConfirmMenu",
    "skills/studio/modules/workspace-discover.md#0::RepoSelectionMenu",
    "skills/studio/modules/workspace-discover.md#0::StorageModeMenu",
    "skills/studio/modules/workspace-discover.md#0::ZeroResultsMenu",
    "skills/studio/modules/workspace-generate.md#2::GenerateFailureMenu",
    "skills/studio/modules/workspace-next-dispatch.md#0::WorkspaceNextStepsMenu",
    "skills/studio/modules/workspace-router-quick.md#0::WorkspaceIntentMenu",
    "skills/studio/modules/workspace-router-quick.md#3::WorkspaceForceSyncConfirm",
    "skills/studio/modules/workspace-validate.md#1::ValidationFailureMenu",
    "skills/studio/modules/write-docs-author-dispatch.md#2::WriteDocsAuthorTargetMissingMenu",
    "skills/studio/modules/write-docs-prep-gates.md#0::WriteDocsExploreMenu",
    "skills/studio/modules/write-docs-prep-gates.md#1::WriteDocsBrainstormMenu",
    "skills/studio/modules/write-skills-author-dispatch.md#2::WriteSkillsNoOutputMenu",
    "skills/studio/modules/write-skills-prep-gates.md#0::WriteSkillsExploreMenu",
    "skills/studio/modules/write-skills-prep-gates.md#1::WriteSkillsBrainstormMenu",
})

# The untyped surface may only shrink. Raising this is a deliberate, reviewable
# act; a rename does not need it, because a rename leaves the count unchanged.
# 113 -> 111: DecompositionConfirmMenu and BriefCheckpointMenu collapsed into one
# menu that declares `TYPE: decision`, so two entries left and none replaced them.
UNTYPED_MENU_BASELINE_CEILING = 111



def _menu_type_declarations() -> dict[str, str | None]:
    """Map every `<path>::<MenuName>` in the prompt roots to its declared TYPE.

    Built from the validator's own block scanner and regexes rather than a
    second parser, so this guard cannot disagree with the checker it guards
    about what a MENU is or where a declaration is read. A private
    reimplementation previously missed indented MENU headers and headers with
    trailing text, and read `TYPE:` out of prose outside the fence.
    """
    declarations: dict[str, str | None] = {}
    seen_declaration: set[str] = set()
    for path in _prompt_files():
        text, error = pdsl.read_source_file(path)
        if error or text is None:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        blocks, _ = pdsl.scan_blocks(str(path), text)
        for block in blocks:
            current: str | None = None
            in_region = False
            sub_header_indent: int | None = None
            for raw_line in block.text.splitlines():
                stripped = raw_line.strip()
                if not stripped or stripped.startswith("//"):
                    continue
                unit_or_menu = pdsl.UNIT_OR_MENU_RE.match(stripped)
                if unit_or_menu:
                    kind, name = unit_or_menu.group(1), unit_or_menu.group("name")
                    # Keyed by block index too, so two blocks in one file
                    # declaring the same MENU name cannot mask each other.
                    current = (
                        f"{rel}#{block.block_index}::{name}" if kind == "MENU" else None
                    )
                    in_region = kind == "MENU"
                    sub_header_indent = None
                    if current is not None:
                        declarations.setdefault(current, None)
                    continue
                head = pdsl.SECTION_HEAD_RE.match(stripped)
                if not head or current is None or not in_region:
                    continue
                indent = len(raw_line) - len(raw_line.lstrip(" "))
                section = head.group("section")
                # Mirrors the validator's continuation rule: a line indented
                # deeper than this menu's first sub-header is that header's own
                # text. Without it an over-indented `TYPE:` counted here while
                # the validator ignored it, so a newly added menu could leave
                # the untyped set with no declaration the validator can see.
                if sub_header_indent is None:
                    sub_header_indent = indent
                elif section not in pdsl.MENU_SUB_HEADERS and indent > sub_header_indent:
                    continue
                if section == pdsl.GATE_HEADER:
                    # Latch on the FIRST declaration, mirroring the validator's
                    # `state.menu_type_line`: it flags every later TYPE line as a
                    # duplicate whatever its value, so a menu whose first
                    # declaration is invalid stays untyped no matter what follows.
                    if current in seen_declaration:
                        continue
                    seen_declaration.add(current)
                    value = stripped[len(pdsl.GATE_HEADER) + 1:].strip()
                    # A value the validator would reject is not a declaration.
                    if value in pdsl.GATE_TYPES:
                        declarations[current] = value
                    continue
                # Mirrors the validator: only a recognized section other than
                # TITLE or TYPE ends the region. Prose does not.
                if section in pdsl.SECTION_HEADERS and section != "TITLE":
                    in_region = False
    return declarations


#: The paths that auto-resolve a gate by runtime judgement rather than by reading
#: a declared TYPE. Named here so the claim in UNTYPED_MENU_BASELINE's comment is
#: pinned to something: if a path is retired or stops judging, the guard below
#: fails and the comment has to be corrected with it. Sourced from
#: `architecture/specs/PDSL.md`, which cites the same three.
RUNTIME_JUDGEMENT_PATHS = {
    "skills/studio/modules/gates/simple-mode-rules.md": "ALWAYS choose automatically only when",
    "workflows/brave-new-world.md": "allowing this overlay to answer eligible menus",
    "skills/studio/modules/subagents/dispatch.md": "SUB_AGENT_GROUP_DECISION = approve-once",
}

#: The claim has a second half -- that none of those paths *reads* a declaration --
#: and it is the half that changes first, because binding them to declared types
#: is what the default-flip does. Matched on the reading vocabulary rather than on
#: the bare type tokens, since `SUB_AGENT_GROUP_DECISION` would otherwise match
#: "decision". A proxy, not a proof: a path could read a declaration in wording
#: this misses.
DECLARED_TYPE_READ_RE = re.compile(
    r"declared\s+TYPE|gate\s+risk|TYPE:\s*(?:confirmation|decision|blocking)\b",
    re.IGNORECASE,
)


def test_the_runtime_judgement_paths_named_in_the_baseline_comment_still_exist() -> None:
    """Pin the claim that undeclared gates are resolved by judgement, not fail-closed.

    `UNTYPED_MENU_BASELINE`'s comment and this module's docstrings state that
    `blocking` is the intended contract rather than current behaviour, because
    shipped paths still auto-resolve an undeclared gate by runtime judgement.
    That is a factual claim about three specific files, and prose cannot hold it:
    a path could be retired or bound to declared types and the comment would
    quietly become false, which is the same overclaim this wording replaced.

    So the count, the paths and both halves of the claim are asserted: each path
    still carries its auto-resolution rule, and none of them reads a declared
    type. The second half matters more, because binding these paths to declared
    types is exactly what the default flip does -- so that is where the comment
    will go stale first. An earlier version of this guard checked only the first
    half and passed when a path gained a declared-type read.

    What still gets past it: a path that reads a declaration in wording
    `DECLARED_TYPE_READ_RE` does not match. The fix when this fails is to correct
    the comment in the same change, not to edit these constants to match.
    """
    assert len(RUNTIME_JUDGEMENT_PATHS) == 3, (
        f"The comment on UNTYPED_MENU_BASELINE says three paths resolve gates by "
        f"runtime judgement; this guard names {len(RUNTIME_JUDGEMENT_PATHS)}. Keep "
        "the two in step."
    )

    findings: list[str] = []
    for rel, marker in sorted(RUNTIME_JUDGEMENT_PATHS.items()):
        path = REPO_ROOT / rel
        if not path.is_file():
            findings.append(f"{rel}: no longer exists")
            continue
        # Read through the validator's own reader, which normalizes OSError and
        # UnicodeDecodeError into a reported error: an unreadable path is a
        # finding about that path, not a crash that hides the other two.
        text, error = pdsl.read_source_file(path)
        if error is not None or text is None:
            findings.append(
                f"{rel}: cannot be read, so the claim cannot be checked "
                f"({error.message if error else 'no content'})"
            )
            continue
        if marker not in text:
            findings.append(f"{rel}: no longer carries {marker!r}")
        read = DECLARED_TYPE_READ_RE.search(text)
        if read is not None:
            findings.append(
                f"{rel}: now reads a declared type ({read.group(0)!r}), so it may no "
                "longer decide by runtime judgement"
            )

    assert not findings, "\n  ".join(
        [
            "The runtime-judgement paths the baseline comment relies on have changed:",
            *findings,
            "",
            "If a path was retired or now reads a declared TYPE, update the comment on "
            "UNTYPED_MENU_BASELINE and the docstring below it -- `blocking` may have "
            "become the actual behaviour rather than only the intended contract.",
        ]
    )


def _validated(text: str):
    """Validate one inline PDSL source and return ``(status, rule ids)``."""
    from studio.utils import pdsl  # noqa: PLC0415

    result = pdsl.validate_source(pdsl.PdslSource(source="inline.md", text=text))
    return result.status, sorted({f.rule_id for f in result.findings})


_GATE = ("```pdsl\nUNIT U\nPURPOSE: x\nDO:\n  EMIT_MENU {name}\n"
         "MENU {name}\nTYPE: {kind}\nOPTIONS:\n  1 go -> CONTINUE Next\n```\n")


class TestOnlyARegisteredGateMayAnswerForTheUser:
    """`confirmation` is the one type that auto-proceeds, so it is the one that is listed.

    The guard is inverted on purpose, and the reason was measured rather than assumed. The
    blocked-action invariants say which gates must never auto-answer, in categories --
    destructive operations, credentials, git mutation, unknown blast radius. Matching those
    categories by their own vocabulary refuses **every one of the 106 menu declarations**
    in this repository's own tree, so a lint
    built that way would disable the type rather than guard it.

    So the lint asks "is this registered", which it can answer, rather than "is this
    dangerous", which it cannot.
    """

    def test_an_unregistered_confirmation_is_refused(self) -> None:
        status, rules = _validated(_GATE.format(name="SomeMenu", kind="confirmation"))
        assert status == "FAIL", rules
        assert rules == ["PDSL704"], rules

    @pytest.mark.parametrize("kind", ["decision", "blocking"])
    def test_the_types_that_keep_asking_need_no_registration(self, kind: str) -> None:
        """Only auto-proceeding is registered; the other two already stop for the user."""
        status, rules = _validated(_GATE.format(name="SomeMenu", kind=kind))
        assert (status, rules) == ("PASS", []), (status, rules)

    @pytest.mark.parametrize("token", ["Confirmation", "confirm", "nonsense"])
    def test_an_unreadable_token_is_reported_as_the_token_not_the_registry(
            self, token: str) -> None:
        """Which rule wins when two could fire, asserted rather than left to ordering.

        A misspelt `Confirmation` is not a `confirmation` that forgot to register — it is
        a token this does not understand, and reporting both would send the author to add
        a registry entry for a type they have not successfully declared. `PDSL700` alone,
        and the registry check is not reached.
        """
        status, rules = _validated(_GATE.format(name="SomeMenu", kind=token))
        assert status == "FAIL", rules
        assert rules == ["PDSL700"], rules

    def test_a_registered_confirmation_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from studio.utils import pdsl  # noqa: PLC0415

        monkeypatch.setattr(pdsl, "AUTO_PROCEEDING_GATES", frozenset({"SomeMenu"}))
        status, rules = _validated(_GATE.format(name="SomeMenu", kind="confirmation"))
        assert (status, rules) == ("PASS", []), (status, rules)

    def test_the_registry_starts_empty_so_nothing_auto_proceeds_yet(self) -> None:
        """Pinned as a literal: the typing work has not happened, and this says so.

        When the first gate is registered this test changes in the same commit, which is
        the point -- the set of gates that may answer for a user should not move without a
        reviewer noticing.
        """
        from studio.utils import pdsl  # noqa: PLC0415

        assert pdsl.AUTO_PROCEEDING_GATES == frozenset(), pdsl.AUTO_PROCEEDING_GATES

    def test_the_measurement_that_justified_the_inversion_still_holds(self) -> None:
        """The whole design rests on one number, so the number is pinned.

        The guard is inverted because matching the blocked-action categories by their own
        vocabulary refuses **every** menu in the tree — which makes a blocklist useless.
        That claim justified the design and nothing reproduced it, so a corpus that drifted
        would leave the rationale quietly false. Raised in review.

        Asserted as the relationship rather than the exact count: what matters is that
        vocabulary-matching is indiscriminate, not that the tree has a particular number
        of menus. Counted as *declarations* rather than names: two files declare
        `TerminalStates`, and keying by name measured the survivor twice.
        """
        stop = {"prompts", "prompt", "confirmations", "or", "any", "that", "authorize",
                "auto-answer", "never", "the", "a", "an", "and", "of", "in", "to", "which",
                "may", "be", "fixed", "selects", "changes", "operations", "controls",
                "approvals", "choices", "state", "rules", "needs", "human", "judgment",
                "judgement", "result", "acceptance", "final", "review", "other"}
        invariants = [line.strip()[2:] for line in Path(
            "skills/studio/modules/brave-new-world-eligibility.md"
        ).read_text(encoding="utf-8").splitlines() if line.strip().startswith("- NEVER")]
        terms = {word for line in invariants for fragment in re.split(r",| or ", line)
                 for word in re.findall(r"[a-z][a-z-]{3,}", fragment.lower())
                 if word not in stop}
        assert len(terms) > 50, f"the invariant vocabulary has collapsed to {len(terms)} terms"

        # A list, not a dict keyed by name: `TerminalStates` is declared in two files, so
        # keying by name silently dropped one of them and measured the survivor twice
        # over. Raised in review — and it is precisely what the duplicate-name tripwire
        # beside this test exists to catch, written into the measurement itself.
        declarations = []
        for folder in ("workflows", "skills"):
            for path in Path(folder).rglob("*.md"):
                body = path.read_text(encoding="utf-8-sig", errors="replace")
                for match in re.finditer(
                        r"^MENU[ \t]+([A-Za-z][\w-]*)(.*?)(?=^MENU |^UNIT |\Z)",
                        body, re.M | re.S):
                    declarations.append((str(path), match.group(1), match.group(0)))
        assert len(declarations) > 50, (
            f"only {len(declarations)} menu declarations found; the corpus scan is wrong")
        refused = [(path, name) for path, name, body in declarations
                   if any(term in (name + " " + body).lower() for term in terms)]
        assert len(refused) == len(declarations), (
            "vocabulary-matching no longer refuses every menu declaration, so a blocklist "
            "may now be viable and the inversion is worth revisiting: "
            f"{len(refused)} of {len(declarations)}"
        )

    def test_a_registered_name_that_no_longer_exists_is_caught(self) -> None:
        """A registry entry outliving its menu is an authorisation nobody can see.

        `UNTYPED_MENU_BASELINE` in this file already has exactly this guard; the new
        registry did not. A stale entry is not merely untidy — it silently pre-authorises
        whatever menu is next given that name. Raised in review.
        """
        from studio.utils import pdsl  # noqa: PLC0415

        declared = set()
        for folder in ("workflows", "skills"):
            for path in Path(folder).rglob("*.md"):
                body = path.read_text(encoding="utf-8-sig", errors="replace")
                declared.update(re.findall(r"^MENU[ \t]+([A-Za-z][\w-]*)", body, re.M))
        assert declared, "no MENU declarations found; this guard has lost its subject"
        stale = sorted(set(pdsl.AUTO_PROCEEDING_GATES) - declared)
        assert not stale, (
            "AUTO_PROCEEDING_GATES names menus that no longer exist, so the entry now "
            f"pre-authorises whatever is next called that: {stale}"
        )

    def test_registering_one_name_authorises_every_menu_that_shares_it(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The limitation, asserted as behaviour rather than described in a comment.

        The registry keys on a bare name and the validator cannot scope it to a file, so
        two menus sharing a name are both authorised by one entry. This proves it rather
        than claiming it — which is what makes the corpus tripwire above load-bearing
        instead of decorative. Raised in review.
        """
        from studio.utils import pdsl  # noqa: PLC0415

        monkeypatch.setattr(pdsl, "AUTO_PROCEEDING_GATES", frozenset({"Shared"}))
        shared = _GATE.format(name="Shared", kind="confirmation")
        # Two separate sources, same bare name: one entry clears both.
        for source in ("reviewed.md", "never-looked-at.md"):
            result = pdsl.validate_source(pdsl.PdslSource(source=source, text=shared))
            assert result.status == "PASS", (source, result.findings)

    def test_no_name_defined_in_two_files_is_ever_registered(self) -> None:
        """The registry keys on a bare name, so a duplicated one authorises both copies.

        The validator sees one source at a time and has no project root, and the path
        differs between this repository and an installed kit, so the key cannot be scoped
        to a file without inventing context that does not exist. This is the guard that is
        available instead — and it is not hypothetical: `TerminalStates` is defined in two
        files in this tree today. Raised in review.
        """
        import collections  # noqa: PLC0415

        from studio.utils import pdsl  # noqa: PLC0415

        where = collections.defaultdict(set)
        for folder in ("workflows", "skills"):
            for path in Path(folder).rglob("*.md"):
                body = path.read_text(encoding="utf-8-sig", errors="replace")
                for match in re.finditer(r"^MENU[ \t]+([A-Za-z][\w-]*)", body, re.M):
                    where[match.group(1)].add(str(path))
        duplicated = {name for name, files in where.items() if len(files) > 1}
        assert duplicated, (
            "no menu name is defined twice any more; if that is real this guard can go, "
            "but check before deleting it"
        )
        overlap = duplicated & set(pdsl.AUTO_PROCEEDING_GATES)
        assert not overlap, (
            "these names are defined in more than one file, so registering them would "
            f"authorise a definition nobody reviewed: {sorted(overlap)}"
        )

    def test_no_gate_the_invariants_name_is_ever_registered(self) -> None:
        """The mechanical link back to the blocked-action list, such as it can be.

        Only two menus are named outright there -- the rest are categories a lint cannot
        decide. Those two can at least never be registered, and this reads the shipped file
        rather than a copy of it, so extending or renaming the list moves the check with it.
        """
        from studio.utils import pdsl  # noqa: PLC0415

        text = Path("skills/studio/modules/brave-new-world-eligibility.md").read_text(
            encoding="utf-8")
        invariants = [line for line in text.splitlines()
                      if line.strip().startswith("- NEVER")]
        assert len(invariants) >= 10, (
            "the blocked-action invariants have shrunk or moved; re-check this guard")
        named = {m for line in invariants
                 for m in re.findall(r"\b([A-Z][a-z]+(?:[A-Z][a-z0-9]+){1,})\b", line)}
        assert named, "no menu is named outright in the invariants any more"
        overlap = named & set(pdsl.AUTO_PROCEEDING_GATES)
        assert not overlap, (
            "these are named in the never-auto-answer invariants and must not be "
            f"registered as auto-proceeding: {sorted(overlap)}")


def test_the_untyped_menu_surface_does_not_grow() -> None:
    """A newly introduced MENU must declare a gate risk TYPE.

    The tail recorded in UNTYPED_MENU_BASELINE is grandfathered so the surface
    can migrate one gate at a time. It is *not* grandfathered because undeclared
    already means `blocking` -- that is the intended contract, and three shipped
    paths still resolve an undeclared gate by runtime judgement today. This test
    freezes the existing untyped inventory: what must not happen is that
    inventory growing, so a MENU neither typed nor in the baseline fails here.
    """
    declarations = _menu_type_declarations()
    untyped_now = {key for key, value in declarations.items() if value is None}

    new_untyped = sorted(untyped_now - UNTYPED_MENU_BASELINE)
    assert not new_untyped, (
        "New MENU(s) without a declared gate risk TYPE:\n  "
        + "\n  ".join(new_untyped)
        + "\n\nDeclare `TYPE: confirmation | decision | blocking` on each, or, if the "
        "menu was renamed or moved, update UNTYPED_MENU_BASELINE."
    )

    # Both assertions above and below are set differences, so a rename -- one key
    # out, another in -- passes, as it should. So would a genuinely new untyped
    # menu added to the baseline in the same diff, disguised as that rename. The
    # count is what makes that impossible without editing a second, obviously
    # named constant that a reviewer can see moving.
    assert len(UNTYPED_MENU_BASELINE) <= UNTYPED_MENU_BASELINE_CEILING, (
        f"UNTYPED_MENU_BASELINE holds {len(UNTYPED_MENU_BASELINE)} entries, above the "
        f"recorded ceiling of {UNTYPED_MENU_BASELINE_CEILING}. The untyped surface may "
        "only shrink: declare a TYPE on the new menu rather than grandfathering it. A "
        "rename swaps one key for another and leaves the count unchanged."
    )

    stale = sorted(UNTYPED_MENU_BASELINE - set(declarations))
    assert not stale, (
        "UNTYPED_MENU_BASELINE lists MENU(s) that no longer exist:\n  "
        + "\n  ".join(stale)
        + "\n\nRemove them from the baseline."
    )


PREP_GATE_GLOB = "skills/studio/modules/*-prep-gates.md"

# Both modules on the cf-plan decomposition path: the gate lives in one and the
# unit that must not write before it lives in the other, so a guard reading only
# one of them cannot see a write moved across the boundary.
PLAN_DECOMPOSITION_MODULES = (
    "skills/studio/modules/plan-assess-decompose.md",
    "skills/studio/modules/plan-compile.md",
)

# Units that consume a written brief package. An option reaching any of them has
# to have written it; keying on these rather than on option labels means renaming
# a label cannot quietly drop an option out of the check.
BRIEF_PACKAGE_CONSUMERS = (
    "PlanPhase3Validate",
    "PlanPhaseCompilerDispatch",
    "NextActionsOffer",
)

PLAN_FIRST_ASSIGNMENT_RE = re.compile(r"PLAN_FIRST_CONTINUE\s*=\s*(?P<unit>[A-Za-z_][\w-]*)")


#: Sections whose lines are executable actions. PURPOSE, TITLE and NOTES are prose:
#: a phrase quoted there is documentation, not a transfer of control, and must not
#: create an obligation for these guards.
ACTION_SECTIONS = frozenset({"DO", "RULES", "OPTIONS", "INVALID"})

#: `PLAN_FIRST_CONTINUE` targets that name no defined UNIT. Grandfathered like
#: UNTYPED_MENU_BASELINE, and like it this set may only shrink: a new dangling
#: target is a defect, and clearing one of these is the fix. Choosing their real
#: targets is a flow decision rather than a rename, so neither is repointed here.
#:   CodingDispatch    - 4 sites; workflows/coding.md is now a thin CodingAlias and
#:                       the test asserting UNIT CodingDispatch exists is xfail.
#:   WriteDocsDispatch - 1 site, write-docs-intent-routing.md.
DANGLING_CONTINUATION_TARGETS = frozenset({"CodingDispatch", "WriteDocsDispatch"})


#: Sections whose lines are self-contained clauses. A menu option and a rule each
#: carry their own actions, so an assignment in a *sibling* clause does not bind
#: them -- one valid option must not vouch for an unbound one next to it. A `DO`
#: block is sequential instead, so an earlier `SET` in the same block does bind a
#: later line.
CLAUSE_SECTIONS = frozenset({"OPTIONS", "INVALID", "RULES"})


def _sectioned_lines(
    path: Path, *, actions_only: bool = False
) -> list[tuple[str, str, int, str]]:
    """Return (UNIT/MENU name, section, absolute line number, line) for a prompt file.

    Read through the validator's own block scanner so these guards agree with the
    checker about what is inside a ```pdsl fence. With ``actions_only`` the result
    is narrowed to ACTION_SECTIONS, so prose cannot create an obligation.
    """
    text, error = pdsl.read_source_file(path)
    if error or text is None:
        return []
    blocks, _ = pdsl.scan_blocks(str(path), text)
    rows: list[tuple[str, str, int, str]] = []
    for block in blocks:
        current = "<no unit>"
        section = ""
        for offset, line in enumerate(block.text.splitlines()):
            stripped = line.strip()
            header = pdsl.UNIT_OR_MENU_RE.match(stripped)
            if header:
                current, section = header.group("name"), ""
            else:
                head = pdsl.SECTION_HEAD_RE.match(stripped)
                if head and head.group("section") in pdsl.SECTION_HEADERS:
                    section = head.group("section")
            if actions_only and section not in ACTION_SECTIONS:
                continue
            rows.append((current, section, block.line + offset, line))
    return rows


def _binding_scope(rows: list[tuple[str, str, int, str]], index: int) -> str:
    """Text that may legitimately bind the continuation on ``rows[index]``.

    A clause section binds per line, because sibling options and sibling rules do
    not vouch for each other. A sequential section binds from the lines that
    precede it inside the same unit and section.
    """
    unit, section, _, line = rows[index]
    if section in CLAUSE_SECTIONS:
        return line
    preceding = [
        text
        for other_unit, other_section, _, text in rows[:index]
        if other_unit == unit and other_section == section
    ]
    return "\n".join([*preceding, line])


def _defined_unit_names() -> set[str]:
    """Every `UNIT <Name>` defined in the prompt corpus."""
    names: set[str] = set()
    for path in _prompt_files():
        for _, _, _, line in _sectioned_lines(path):
            header = pdsl.UNIT_OR_MENU_RE.match(line.strip())
            if header and header.group(1) == "UNIT":
                names.add(header.group("name"))
    return names


def test_every_entry_into_plan_first_gate_sets_its_return_unit() -> None:
    """`PlanFirstGate` may not be entered without a real `PLAN_FIRST_CONTINUE`.

    `gates/plan-first.md:19` states `NEVER run without PLAN_FIRST_CONTINUE set by
    the caller`, and nothing in the shared `gates/workflow-prep.md` sets it on a
    caller's behalf. Two auto-skip rules did not: they reached the gate with the
    variable unset and the module unloaded, so the gate's own `no-plan` option
    continued to an unset unit -- silently, no reason surfaced, the run just
    proceeded.

    Binding is per clause, not per unit: a menu option or a rule must carry its
    own assignment and load, because a valid sibling option must not vouch for an
    unbound one beside it. A `DO` block binds sequentially instead, so an earlier
    `SET` in the same block counts and splitting a long clause stays legal.
    `unset` is rejected because it is the exact state the gate forbids, and the
    indirect entry via `COMPANION_CONTINUE` is included, because a clause added
    there fails the same way.
    """
    findings: list[str] = []
    checked = 0
    defined = _defined_unit_names()
    for path in _prompt_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        rows = _sectioned_lines(path, actions_only=True)

        for index, (unit, section, line_no, line) in enumerate(rows):
            direct = "CONTINUE PlanFirstGate" in line
            indirect = "COMPANION_CONTINUE = PlanFirstGate" in line
            if not (direct or indirect):
                continue
            checked += 1
            scope = _binding_scope(rows, index)
            units = {m.group("unit") for m in PLAN_FIRST_ASSIGNMENT_RE.finditer(scope)}
            real = units - {"unset"}
            if not units:
                findings.append(
                    f"{rel}:{line_no}: no PLAN_FIRST_CONTINUE set in this "
                    f"{section} clause of {unit}"
                )
            elif not real:
                findings.append(
                    f"{rel}:{line_no}: PLAN_FIRST_CONTINUE = unset in this "
                    f"{section} clause of {unit}, which is the state the gate "
                    "refuses to run under"
                )
            if direct and "gates/plan-first.md" not in scope:
                findings.append(
                    f"{rel}:{line_no}: continues to PlanFirstGate without LOADing "
                    f"gates/plan-first.md in this {section} clause of {unit}"
                )
            # Rejecting only `unset` would accept a typo: any identifier-shaped
            # token read as "real". The gate cannot CONTINUE to a unit that does
            # not exist, so the target is resolved against the corpus.
            for unit in sorted(real - DANGLING_CONTINUATION_TARGETS):
                if unit not in defined:
                    findings.append(
                        f"{rel}:{line_no}: PLAN_FIRST_CONTINUE = {unit}, which is not a "
                        "defined UNIT anywhere in the corpus"
                    )

    # A floor, not the count: consolidating a clause is legitimate and must not
    # fail here. It exists only so a rename cannot leave this guard inspecting
    # nothing and still reporting green.
    assert checked >= 5, (
        f"Only {checked} clause(s) enter PlanFirstGate; expected at least 5. If the "
        "gate or the variable was renamed, update this guard -- do not let it pass "
        "over a corpus it no longer inspects."
    )
    assert not findings, "\n  ".join(["Entries into PlanFirstGate are unguarded:"] + findings)


def test_prep_gate_modules_apply_the_same_auto_skip_rules() -> None:
    """Every prep-gate module must skip itself on the same terms.

    `write-docs` and `write-skills` auto-skipped their explore and brainstorm
    gates when the target was unambiguous; `coding` had no auto-skip rule at all,
    so the same task would have cost two extra stops purely because it was code.
    Stated in the conditional because no shipped workflow currently loads any of
    these three modules -- they are reachable only through `*-intent-routing.md`
    /`coding-intent-companion.md`, which nothing references -- so the divergence
    is latent. This guard exists so the three stay aligned until that path is
    reconnected, at which point the difference becomes observable.

    Discovered by glob, so a fourth prep-gate module added without the rules
    fails here rather than being noticed in review. Each rule is checked for its
    continuation target, its note, the dispatch unit its own menu names, and the
    UNIT it sits in -- target and note alone pin none of the placement, so both
    rules could sit in the explore unit and leave the brainstorm gate with no
    auto-skip while every string this test looks for was still present.
    """
    modules = sorted(REPO_ROOT.glob(PREP_GATE_GLOB))
    assert len(modules) >= 3, (
        f"Found {len(modules)} prep-gate module(s) via {PREP_GATE_GLOB}; expected at "
        "least 3. If they moved, update the glob."
    )

    findings: list[str] = []
    for path in modules:
        rel = path.relative_to(REPO_ROOT).as_posix()
        action_rows = _sectioned_lines(path, actions_only=True)
        rules = [
            (unit, line.strip())
            for unit, _, _, line in action_rows
            if "ALWAYS auto-skip" in line
        ]
        if len(rules) != 2:
            findings.append(f"{rel}: {len(rules)} auto-skip rule(s), expected 2")
            continue

        # The two gates are derived from the module, not named here: the explore
        # unit is whichever one wires the brainstorm gate, and the brainstorm unit
        # is the one it names.
        wiring = [
            (unit, re.search(r"SET WORKFLOW_PREP_BRAINSTORM_GATE = (?P<gate>\S+)", line))
            for unit, _, _, line in action_rows
        ]
        wiring = [(unit, m) for unit, m in wiring if m is not None]
        if not wiring:
            findings.append(f"{rel}: no WORKFLOW_PREP_BRAINSTORM_GATE to continue to")
            continue
        explore_unit, brainstorm = wiring[0]
        brainstorm_unit = brainstorm.group("gate")

        # Target and note alone do not pin placement: both rules could sit in the
        # explore unit, leaving the brainstorm gate with no auto-skip at all while
        # every string this test looks for is still present somewhere in the file.
        expected_unit = {
            f"CONTINUE {brainstorm_unit}": explore_unit,
            "CONTINUE PlanFirstGate": brainstorm_unit,
        }

        expected = {
            f"CONTINUE {brainstorm_unit}": "Skipping context discovery — target is clear.",
            "CONTINUE PlanFirstGate": "Skipping brainstorm — approach is clear.",
        }
        # A rule may name a dispatch target its own menu does not: a copy-paste
        # from a sibling module routes that module's skip path into the wrong
        # dispatch unit, while every shared substring still matches. Derived from
        # the module itself rather than a table, so it cannot drift out of date.
        menu_targets = {
            m.group(1)
            for _, _, _, line in _sectioned_lines(path, actions_only=True)
            if "EMIT_MENU" not in line
            for m in [re.search(r"PLAN_FIRST_CONTINUE\s*=\s*([A-Za-z_][\w-]*)", line)]
            if m and "->" in line
        }
        for _, rule in rules:
            found = re.search(r"PLAN_FIRST_CONTINUE\s*=\s*([A-Za-z_][\w-]*)", rule)
            if found and menu_targets and found.group(1) not in menu_targets:
                findings.append(
                    f"{rel}: auto-skip rule sets PLAN_FIRST_CONTINUE = {found.group(1)}, "
                    f"but this module's own menu options set {sorted(menu_targets)}"
                )

        for target, note in expected.items():
            matching = [(unit, rule) for unit, rule in rules if target in rule]
            if len(matching) != 1:
                findings.append(
                    f"{rel}: {len(matching)} auto-skip rule(s) continue to {target!r}, expected 1"
                )
                continue
            unit, rule = matching[0]
            if unit != expected_unit[target]:
                findings.append(
                    f"{rel}: the {target!r} auto-skip rule sits in {unit}, expected "
                    f"{expected_unit[target]} — placement decides which gate skips itself"
                )
            if "ORIGINAL_INTENT resolves to a single known file" not in rule:
                findings.append(f"{rel}: {target!r} rule does not share the condition")
            if note not in rule:
                findings.append(f"{rel}: {target!r} rule does not emit {note!r}")

    assert not findings, "\n  ".join(
        ["Prep-gate auto-skip rules are inconsistent across modules:"] + findings
    )


def test_the_brief_package_is_never_written_before_its_gate_resolves() -> None:
    """`plan.toml` and the briefs may only be written by an authorised choice.

    The write and the authorisation used to be two stops: a confirmation, then
    the writes, then a second menu choosing the production mode. They are now one
    `decision` gate, which only holds while the writes stay behind it.

    Both modules on the path are read, because a write moved into the pre-gate
    unit would otherwise be invisible; writes are matched on the artifact rather
    than on one spelling of its path, because PDSL actions are free prose; the
    producing options are identified by the units they reach, because an option
    label can be renamed; and only action sections are scanned, so a PURPOSE or
    NOTES line naming these artifacts cannot fail the build.
    """
    findings: list[str] = []
    writers: set[str] = set()

    for rel in PLAN_DECOMPOSITION_MODULES:
        rows = _sectioned_lines(REPO_ROOT / rel, actions_only=True)
        for section, _, line_no, line in rows:
            if "WRITE" not in line:
                continue
            if not ("plan.toml" in line or "brief-" in line):
                continue
            if section != "PlanWriteBriefPackage":
                findings.append(
                    f"{rel}:{line_no}: {section} writes the brief package; only "
                    f"PlanWriteBriefPackage may: {line.strip()[:90]}"
                )
        for section, _, _, line in rows:
            if "RUN PlanWriteBriefPackage" in line:
                writers.add(f"{rel}::{section}")

    if writers != {"skills/studio/modules/plan-compile.md::PlanProduceChoice"}:
        findings.append(
            f"PlanWriteBriefPackage is run from {sorted(writers) or ['nowhere']}, "
            "expected only plan-compile.md::PlanProduceChoice"
        )

    produced = 0
    for section, _, line_no, line in _sectioned_lines(
        REPO_ROOT / "skills/studio/modules/plan-compile.md", actions_only=True
    ):
        if section != "PlanProduceChoice" or "->" not in line:
            continue
        consumes = any(consumer in line for consumer in BRIEF_PACKAGE_CONSUMERS)
        writes = "RUN PlanWriteBriefPackage" in line
        produced += writes
        if consumes and not writes:
            findings.append(
                f"{line_no}: option reaches a brief-package consumer without writing "
                f"the package: {line.strip()[:90]}"
            )
        if writes and not consumes:
            findings.append(
                f"{line_no}: option writes the package but reaches no consumer of it: "
                f"{line.strip()[:90]}"
            )
    if produced < 1:
        findings.append("no option writes the brief package, so the gate guards nothing")

    # A consumer is reached from the same option clause that runs the writer, so
    # nothing structural stops a partial package being consumed -- what stops it
    # is that the summary is the consumer's only completeness signal, and that a
    # failed write stops the turn instead of emitting one. Both are pinned here:
    # the summary must be the writer's last DO action, so no write follows a
    # signal that everything is written, and the failure path must terminate.
    writer_rows = [
        (section, line)
        for unit, section, _, line in _sectioned_lines(
            REPO_ROOT / "skills/studio/modules/plan-compile.md"
        )
        if unit == "PlanWriteBriefPackage"
    ]
    do_actions = [line.strip() for section, line in writer_rows if section == "DO" and line.strip()]
    if not do_actions:
        findings.append("PlanWriteBriefPackage has no DO actions")
    elif "EMIT the brief package summary" not in do_actions[-1]:
        findings.append(
            "PlanWriteBriefPackage's last DO action is "
            f"{do_actions[-1][:70]!r}, expected the brief package summary — a write "
            "after the completeness signal would be reported as already done"
        )
    on_error = [line.strip() for section, line in writer_rows if section == "ON_ERROR" and line.strip()]
    if not on_error:
        findings.append(
            "PlanWriteBriefPackage has no ON_ERROR clause, so a failed write has no "
            "defined path and a partial package can reach a consumer"
        )
    elif not any("STOP_TURN" in line for line in on_error):
        findings.append(
            "PlanWriteBriefPackage's ON_ERROR does not STOP_TURN, so control "
            "continues into the consumer after a failed write"
        )

    # Pin the declared type: a `confirmation` would let an autonomous session
    # authorise the write without asking, which is what this collapse removed.
    declarations = _menu_type_declarations()
    key = "skills/studio/modules/plan-compile.md#0::PlanProduceChoice"
    if declarations.get(key) != "decision":
        findings.append(
            f"PlanProduceChoice declares TYPE {declarations.get(key)!r}, expected 'decision'"
        )

    assert not findings, "\n  ".join(["Brief-package write authorisation broken:"] + findings)


@pytest.mark.parametrize(
    ("kind", "message"),
    [
        ("READ_ERROR", "Cannot read source: [Errno 13] Permission denied"),
        ("DECODE_ERROR", "Cannot decode source as UTF-8: invalid start byte"),
    ],
)
def test_the_runtime_judgement_guard_reports_an_unreadable_path(kind: str, message: str) -> None:
    """An unreadable path is a finding naming that path, never a raised error.

    The guard reads three files. Calling `read_text` directly meant one
    unreadable or non-UTF-8 file aborted the whole guard, so the other two went
    unchecked and the failure said nothing about which path was at fault. Both
    error shapes the reader normalizes are covered here, because a manual check
    leaves nothing behind to stop this coming back.
    """
    error = pdsl.PdslError(message=message, source_path="x", kind=kind)
    with mock.patch.object(pdsl, "read_source_file", return_value=(None, error)):
        with pytest.raises(AssertionError) as raised:
            test_the_runtime_judgement_paths_named_in_the_baseline_comment_still_exist()

    report = str(raised.value)
    for rel in RUNTIME_JUDGEMENT_PATHS:
        assert f"{rel}: cannot be read" in report, f"{rel} missing from:\n{report}"
    assert message in report, f"the reader's reason is not reported:\n{report}"


def _declarations_for(tmp_path: Path, name: str, body: str) -> dict[str, str | None]:
    """Run the guard's scanner over a single fixture file."""
    fixture = tmp_path / name
    fixture.write_text(body, encoding="utf-8")
    with mock.patch(f"{__name__}._prompt_files", return_value=[fixture]), \
            mock.patch(f"{__name__}.REPO_ROOT", tmp_path):
        return _menu_type_declarations()


def test_the_guard_classifies_declared_and_undeclared_menus(tmp_path: Path) -> None:
    """The guard is the only thing requiring a new MENU to declare a type.

    It has to agree with the validator about what a MENU is and what counts as
    a declaration, so both classifications are pinned here rather than trusted.
    """
    body = (
        "```pdsl\n"
        "MENU Declared:\n  TITLE: t\n  TYPE: blocking\n  OPTIONS:\n    1 a -> CONTINUE X\n"
        "\nMENU Undeclared:\n  TITLE: t\n  OPTIONS:\n    1 a -> CONTINUE X\n"
        "```\n"
    )
    values = {key.split("::")[-1]: value for key, value in _declarations_for(
        tmp_path, "both.md", body).items()}
    assert values == {"Declared": "blocking", "Undeclared": None}


def test_the_guard_sees_menu_shapes_a_private_regex_missed(tmp_path: Path) -> None:
    """An indented header, and trailing text after the name, are still MENUs."""
    indented = "```pdsl\nUNIT Flow:\n  PURPOSE: x\n  MENU Nested:\n    OPTIONS:\n      1 a -> RUN X\n```\n"
    assert list(_declarations_for(tmp_path, "a.md", indented).values()) == [None]

    trailing = "```pdsl\nMENU Trailing: pick one\n  OPTIONS:\n    1 a -> RUN X\n```\n"
    assert list(_declarations_for(tmp_path, "b.md", trailing).values()) == [None]


def test_the_guard_does_not_read_a_declaration_the_validator_rejects(tmp_path: Path) -> None:
    """A value or a position the validator rejects must not count as declared."""
    outside_fence = (
        "```pdsl\nMENU Fenced:\n  TITLE: t\n  OPTIONS:\n    1 a -> RUN X\n```\n"
        "\n  TYPE: confirmation is one of three values.\n"
    )
    assert list(_declarations_for(tmp_path, "c.md", outside_fence).values()) == [None]

    bad_value = "```pdsl\nMENU Bad:\n  TITLE: t\n  TYPE: urgent\n  OPTIONS:\n    1 a -> RUN X\n```\n"
    assert list(_declarations_for(tmp_path, "d.md", bad_value).values()) == [None]

    past_region = "```pdsl\nMENU Late:\n  OPTIONS:\n    1 a -> RUN X\n  TYPE: blocking\n```\n"
    assert list(_declarations_for(tmp_path, "e.md", past_region).values()) == [None]


def test_the_guard_keeps_same_named_menus_in_separate_blocks_apart(tmp_path: Path) -> None:
    """A typed menu must not mask an untyped one of the same name in another block."""
    body = (
        "```pdsl\nMENU Same:\n  TITLE: t\n  OPTIONS:\n    1 a -> RUN X\n```\n"
        "\n```pdsl\nMENU Same:\n  TITLE: t\n  TYPE: blocking\n  OPTIONS:\n    1 a -> RUN X\n```\n"
    )
    assert sorted(_declarations_for(tmp_path, "f.md", body).values(), key=str) == [None, "blocking"]


def test_the_guard_does_not_accept_a_declaration_the_validator_rejects(tmp_path: Path) -> None:
    """A malformed declaration must not satisfy the no-growth guard.

    The scanner latches on the first `TYPE` line, mirroring the validator's
    `state.menu_type_line`. Without that latch an invalid first declaration
    followed by a valid one registered the menu as typed while the validator
    rejected the file outright — so a newly added menu could carry a malformed
    declaration and still pass the guard.
    """
    invalid_then_valid = (
        "```pdsl\nMENU X:\n  TITLE: t\n  TYPE: bogus\n  TYPE: blocking\n"
        "  OPTIONS:\n    1 a -> RUN Y\n```\n"
    )
    assert list(_declarations_for(tmp_path, "a.md", invalid_then_valid).values()) == [None]

    single_invalid = (
        "```pdsl\nMENU X:\n  TITLE: t\n  TYPE: bogus\n  OPTIONS:\n    1 a -> RUN Y\n```\n"
    )
    assert list(_declarations_for(tmp_path, "b.md", single_invalid).values()) == [None]

    # A valid first declaration still counts; the duplicate that follows fails
    # the file on PDSL701, so the guard's verdict cannot create a bypass.
    valid_then_valid = (
        "```pdsl\nMENU X:\n  TITLE: t\n  TYPE: decision\n  TYPE: blocking\n"
        "  OPTIONS:\n    1 a -> RUN Y\n```\n"
    )
    assert list(_declarations_for(tmp_path, "c.md", valid_then_valid).values()) == ["decision"]


def test_the_guard_ignores_an_over_indented_declaration_like_the_validator(tmp_path: Path) -> None:
    """The guard must not count a declaration the validator does not read.

    An over-indented `TYPE:` is continuation text to the validator. Counted
    here, it would drop a newly added menu out of the untyped set while
    producing no validator finding — a silently undeclared gate, which is the
    failure the freeze exists to prevent.
    """
    over_indented = (
        "```pdsl\nMENU Over:\n  TITLE: Heading\n    TYPE: blocking\n"
        "  OPTIONS:\n    1 a -> RUN X\n```\n"
    )
    assert list(_declarations_for(tmp_path, "over.md", over_indented).values()) == [None]

    at_level = (
        "```pdsl\nMENU AtLevel:\n  TITLE: Heading\n  TYPE: blocking\n"
        "  OPTIONS:\n    1 a -> RUN X\n```\n"
    )
    assert list(_declarations_for(tmp_path, "level.md", at_level).values()) == ["blocking"]


#: Units that begin plan execution — a phase is dispatched from each. Named rather than
#: pattern-matched so the intent is explicit, and kept honest by
#: `test_the_execution_entry_list_covers_every_dispatching_unit`, which fails when a unit
#: dispatches phase work without appearing here. An earlier version of this comment
#: claimed a completeness guard that did not exist.
PLAN_EXECUTION_ENTRIES = {
    "PlanNativeExecute": str(REPO_ROOT / "skills/studio/modules/plan-native-dispatch.md"),
    "PlanPhaseCompilerDispatch": str(REPO_ROOT / "skills/studio/modules/plan-compiler-dispatch.md"),
}

#: The points at which a plan is genuinely approved: the decomposition was shown and
#: the user chose to proceed with it. `PlanProduceChoice`'s own title says options 1-4
#: "authorise writing plan.toml + N brief files", and it is already a declared
#: `decision` gate; `PlanStorageChoice` presents the drafted plan for review first.
#:
#: Deliberately *not* `PlanSaveGateMenu`: it asks where to put the file, and its module
#: never shows the plan, so neither answer is consent to the plan's content. Recording
#: approval there would manufacture it. That path has no approval point, so its gates
#: ask — which is the safe direction and the honest one.
#:
#: Deliberately *not* `Phase4NextStepsMenu` either: it routes an already-approved plan.
#: Approval there would sit *after* phase compilation, which requires approval — a
#: deadlock that killed the sub-agent option outright before this test existed.
PLAN_APPROVAL_POINTS = {
    "PlanProduceChoice": str(REPO_ROOT / "skills/studio/modules/plan-compile.md"),
    "PlanStorageChoice": str(REPO_ROOT / "skills/studio/modules/gates/plan-first.md"),
}

#: Menu options that change a plan after it was approved. Each must revoke the
#: approval: one left in place would vouch for a plan that no longer exists.
PLAN_REVISION_OPTIONS = {
    "PlanProduceChoice": str(REPO_ROOT / "skills/studio/modules/plan-compile.md"),
    "Phase4NextStepsMenu": str(REPO_ROOT / "skills/studio/modules/plan-validate-finalize.md"),
}

APPROVAL_FLAG = "accepted_plan_active"
APPROVAL_ARTIFACT_FIELD = "plan.approval_status"


def test_the_approval_flag_is_declared_state_somewhere() -> None:
    """It was set in menu options and read only in prose, declared nowhere.

    The flag the whole anchor rests on was an undeclared variable: no `STATE:` block
    named it, so nothing recorded its type, default or scope, and a reader had to
    infer all three from an assignment inside a menu option.
    """
    declarations = [
        (path, unit, line.strip())
        for path in _prompt_files()
        for unit, section, _, line in _sectioned_lines(path)
        if section == "STATE" and APPROVAL_FLAG in line
    ]
    assert declarations, f"{APPROVAL_FLAG} is set but never declared in a STATE block"
    assert any("scope workflow_run" in line for _, _, line in declarations), declarations
    # Declared once, by the gate whose contract reads it. "Somewhere" was too weak: two
    # modules could each declare it with different defaults and this would pass, which
    # is precisely the shared-state confusion this flag has already caused once.
    owners = {(str(path), unit) for path, unit, _ in declarations}
    assert len(owners) == 1, f"{APPROVAL_FLAG} is declared in more than one place: {owners}"
    owner_path, owner_unit = owners.pop()
    assert owner_path.endswith("gates/plan-first.md"), owner_path
    assert owner_unit == "PlanFirstGate", owner_unit


def test_every_approval_point_sets_the_flag() -> None:
    """One flag, set at each path's approval, rather than a second concept per path."""
    for menu, module in PLAN_APPROVAL_POINTS.items():
        rows = _sectioned_lines(Path(module), actions_only=True)
        # Every option that authorises the work, not merely one of them. The first
        # version asserted the list was non-empty, so deleting the setter from a
        # single option left it passing while that path approved nothing.
        # Each gate records its approval where its own consumer reads it: `cf-plan`
        # writes `plan.approval_status` to the plan it just produced, and the
        # plan-first gate sets its run-scoped flag. They are deliberately not the
        # same channel — the flag carries `PlanAcceptedExecutionContract`, whose
        # `DISPATCH:`/`INLINE:` directives a cf-plan plan does not use.
        expected = (f'{APPROVAL_ARTIFACT_FIELD}="approved"'
                    if "plan-compile" in module else f"SET {APPROVAL_FLAG} = true")
        authorising = [
            line for unit, section, _, line in rows
            if unit == menu and section in CLAUSE_SECTIONS
            and ("RUN PlanWriteBriefPackage" in line or APPROVAL_FLAG in line)
            and "unset" not in line and "revised" not in line
        ]
        assert authorising, f"{menu} in {module} has no authorising option"
        missing = [line for line in authorising if expected not in line]
        assert not missing, f"{menu} authorises work without recording {expected}: {missing}"


def test_every_execution_entry_refuses_an_unapproved_plan_out_loud() -> None:
    """No path may start work unapproved — and it must say so, not just not happen.

    Two mistakes are pinned here. `PlanNativeExecute` and the compiler dispatch gated
    only on their own `CF_PHASE_GATE`, so nothing asserted the plan had been approved.
    The first fix used a `WHEN` clause, which is worse than it looks: an unmet `WHEN`
    skips the unit silently, so an unapproved run produced no phases and no message.
    The check has to be an action that emits and stops.
    """
    for unit, module in PLAN_EXECUTION_ENTRIES.items():
        rows = _sectioned_lines(Path(module), actions_only=True)
        # `startswith`, not `in`: the first version matched the text anywhere on the
        # line, so commenting the refusal out left it passing — the mutation that
        # exposed this removed the behaviour and no guard noticed.
        refusals = [
            line for row_unit, section, _, line in rows
            if row_unit == unit and section == "DO"
            and line.strip().startswith("EMIT ")
            and APPROVAL_FLAG in line and "STOP_TURN" in line
        ]
        assert refusals, f"{unit} in {module} does not refuse an unapproved plan out loud"
        silent = [
            line for row_unit, section, _, line in _sectioned_lines(Path(module))
            if row_unit == unit and section == "WHEN" and APPROVAL_FLAG in line
        ]
        assert not silent, f"{unit} gates approval in WHEN, which skips in silence: {silent}"


def test_the_approval_requirement_is_satisfiable_from_disk() -> None:
    """A new chat has no run state, and handing off to one is a shipped option.

    Requiring only the run-scoped flag would block the very path that exists to be
    pasted into a fresh chat — the same reason correlation is done by the approved
    plan found on disk rather than by anything carried in the session.
    """
    for unit, module in PLAN_EXECUTION_ENTRIES.items():
        rows = _sectioned_lines(Path(module))
        when = " ".join(
            line for row_unit, section, _, line in rows
            if row_unit == unit and section == "DO" and APPROVAL_FLAG in line
        )
        assert APPROVAL_ARTIFACT_FIELD in when, (
            f"{unit} requires only the run-scoped flag, so a handoff into a new chat "
            f"could never satisfy it"
        )


def test_the_structured_path_persists_the_approval() -> None:
    """Run state cannot reach the next session; the artifact can."""
    rows = _sectioned_lines(REPO_ROOT / "skills/studio/modules/plan-compile.md", actions_only=True)
    persisted = [
        line for unit, _, _, line in rows
        if unit == "PlanProduceChoice" and f'SET {APPROVAL_ARTIFACT_FIELD}="approved"' in line
    ]
    assert len(persisted) >= 4, (
        "every option that authorises writing the plan package must record the approval "
        f"in the artifact, found {len(persisted)}"
    )


def test_the_save_gate_never_records_an_approval_it_did_not_collect() -> None:
    """The inverse of what this test first asserted, because the first version was wrong.

    `PlanSaveGateMenu` asks "Save this plan as a Markdown file?" and its module emits
    the plan nowhere. An earlier draft of this change set the approval flag on *both*
    of its options and called resolving the gate "the point the plan was shown and
    accepted". It was not shown, so neither answer is consent to its content, and
    recording approval there would have manufactured it — the one thing an audit
    anchor must never do.

    That path therefore has no approval point. Its `decision` gates ask, which is the
    safe direction, and this test exists so the shortcut is not taken again.
    """
    rows = _sectioned_lines(
        REPO_ROOT / "skills/studio/modules/planning-runtime.md", actions_only=True
    )
    approvals = [
        line for unit, _, _, line in rows
        if unit == "PlanSaveGateMenu" and APPROVAL_FLAG in line
    ]
    assert not approvals, (
        "the save gate records an approval the user was never asked for: " + str(approvals)
    )


def test_every_revision_option_revokes_the_approval() -> None:
    """Changing an approved plan must revoke the approval it no longer describes.

    Both revision paths return the user to the same menu with the flag still set, so
    an approval granted before the change would vouch for a plan that no longer
    exists — and on the cf-plan path it is also written to the artifact, where it
    would outlive the session.
    """
    for menu, module in PLAN_REVISION_OPTIONS.items():
        rows = _sectioned_lines(Path(module), actions_only=True)
        revisers = [
            line for unit, section, _, line in rows
            if unit == menu and section in CLAUSE_SECTIONS
            and ("revise" in line or "modify" in line)
        ]
        assert revisers, f"no revision option found in {menu}"
        for line in revisers:
            # The artifact is the channel that outlives the session and the one phase
            # dispatch reads, so it is the one a revision must mark. An earlier version
            # asserted the run-scoped flag instead, which cf-plan no longer sets.
            assert f'{APPROVAL_ARTIFACT_FIELD}="revised"' in line, (
                f"{menu} lets the user change the plan without revoking approval: {line}"
            )


def test_approval_is_never_granted_after_the_work_it_authorises() -> None:
    """The deadlock guard, written because I shipped the deadlock.

    Phase compilation requires approval. An earlier draft granted approval at
    `Phase4NextStepsMenu`, which only runs *after* phase files were produced — so
    compilation waited for an approval that waited for compilation, and the sub-agent
    option could never run at all. Six other tests passed while that was true,
    because they checked that the words were present rather than that the flow closed.

    So: no menu that routes an already-produced plan may be an approval point.
    """
    for menu, module in PLAN_APPROVAL_POINTS.items():
        assert menu != "Phase4NextStepsMenu", "approval moved back after compilation"
    rows = _sectioned_lines(
        REPO_ROOT / "skills/studio/modules/plan-validate-finalize.md", actions_only=True
    )
    granted = [
        line for unit, _, _, line in rows
        if unit == "Phase4NextStepsMenu"
        and (f"SET {APPROVAL_FLAG} = true" in line
             or f'{APPROVAL_ARTIFACT_FIELD}="approved"' in line)
    ]
    assert not granted, f"approval granted after the compilation that requires it: {granted}"


def test_revoking_an_approval_leaves_a_route_to_a_new_one() -> None:
    """Revocation without a way back is a worse failure than a stale approval.

    Making `modify` revoke the approval was right, and it created a dead end: none
    of that menu's six options routed to a gate that could grant a new one, so a
    user who edited the plan could revoke approval and then never execute. The fix
    routes the edit back through decomposition, which is where approval is given
    and which re-shows the plan before asking again.
    """
    approval_units = set(PLAN_APPROVAL_POINTS)
    for menu, module in PLAN_REVISION_OPTIONS.items():
        rows = _sectioned_lines(Path(module), actions_only=True)
        revisers = [
            line for unit, section, _, line in rows
            if unit == menu and section in CLAUSE_SECTIONS
            and f'{APPROVAL_ARTIFACT_FIELD}="revised"' in line
        ]
        assert revisers, f"{menu} revokes nothing"
        for line in revisers:
            # the option must hand control somewhere an approval can be re-granted:
            # either a named unit upstream of the approval gate, or the gate's menu
            assert "CONTINUE " in line, (
                f"{menu} revokes the approval and offers no route to a new one: {line}"
            )
            assert any(target in line for target in ("PlanPhase2Decompose", *approval_units)), (
                f"{menu} routes somewhere that cannot re-approve: {line}"
            )


def test_the_deferred_continue_in_the_revision_route_precedes_its_wait() -> None:
    """The resume idiom only works written before the WAIT it defers past.

    `WAIT` + `STOP_TURN` is a hard turn boundary, so a `CONTINUE ... after
    user.reply` placed after it is unreachable — the rule the spec states and
    nothing yet enforces. The revision route added here uses that idiom, so it is
    pinned locally until the corpus-wide check exists.
    """
    rows = _sectioned_lines(
        REPO_ROOT / "skills/studio/modules/plan-validate-finalize.md", actions_only=True
    )
    deferred = [
        line for unit, _, _, line in rows
        if unit == "Phase4NextStepsMenu" and "after user.reply" in line
    ]
    assert deferred, "the revision route no longer defers a continuation"
    for line in deferred:
        assert line.index("CONTINUE ") < line.index("WAIT "), (
            f"the deferred continue sits after its WAIT, so it can never run: {line}"
        )


def test_the_artifact_approval_is_written_after_the_file_exists() -> None:
    """`plan.toml` is created by the package write, so the field cannot precede it.

    Three separate drafts of this change wrote `plan.approval_status` into a file
    that did not exist yet — once on the revise option, once on all four authorising
    options. The corpus already showed the right order: option 4's own
    `SET plan.execution_status` sits *after* `RUN PlanWriteBriefPackage`.
    """
    rows = _sectioned_lines(REPO_ROOT / "skills/studio/modules/plan-compile.md", actions_only=True)
    lines = [
        line for unit, _, _, line in rows
        if unit == "PlanProduceChoice" and f'{APPROVAL_ARTIFACT_FIELD}="approved"' in line
    ]
    assert len(lines) >= 4, f"expected the four authorising options, found {len(lines)}"
    for line in lines:
        assert "RUN PlanWriteBriefPackage" in line, line
        assert line.index("RUN PlanWriteBriefPackage") < line.index(APPROVAL_ARTIFACT_FIELD), (
            "the approval is written to plan.toml before the step that creates it: " + line
        )


def test_the_execution_entry_list_covers_every_dispatching_unit() -> None:
    """Make the list's completeness a fact rather than a comment.

    The constant's own comment used to claim a guard asserted this. None did, so a new
    unit could dispatch phase work with no approval check and every test would pass —
    the same shape as a docstring promising a property the code does not hold.

    `RUN SubAgentDispatch` is the signal: it is how a phase reaches a sub-agent, and it
    appears in exactly the units that start phase work.
    """
    dispatching: dict[str, str] = {}
    # Every prompt file, not `plan-*.md`: a unit that dispatches phase work is not
    # obliged to live in a file whose name starts with "plan-", and a guard that only
    # looks there would miss the one that did not.
    for path in _prompt_files():
        for unit, section, _, line in _sectioned_lines(path, actions_only=True):
            # `SubAgentDispatch` alone is too broad once every file is searched: the
            # migrator, the brainstorm panel and the reviewers all dispatch sub-agents
            # and none of them runs a plan phase. A *phase* dispatch names one.
            if (section == "DO" and "RUN SubAgentDispatch" in line
                    and "phase" in line.lower()):
                dispatching[unit] = str(path)
    assert dispatching, "the dispatch signal changed; this guard is no longer measuring"
    missing = {u: m for u, m in dispatching.items() if u not in PLAN_EXECUTION_ENTRIES}
    assert not missing, (
        f"these units dispatch phase work but are not checked for approval: {missing}"
    )


def test_phase_dispatch_requires_this_plans_own_artifact_not_the_shared_flag() -> None:
    """`accepted_plan_active` is shared across two different plan systems in one run.

    `gates/plan-first.md` sets it when its *own* plan is accepted — memory or disk.
    Both live in `scope workflow_run`, so a session that accepted a plan-first plan
    and then ran cf-plan would arrive at phase dispatch with the flag already true,
    and dispatch phases whose decomposition was never approved. The flag says a plan
    was approved; it does not say *which*.

    `plan.approval_status` lives in that plan's own `plan.toml`, so it cannot be
    satisfied by a different plan's approval. Phase dispatch keys on the artifact.
    """
    for unit, module in PLAN_EXECUTION_ENTRIES.items():
        rows = _sectioned_lines(Path(module), actions_only=True)
        refusal = " ".join(
            line for row_unit, section, _, line in rows
            if row_unit == unit and section == "DO"
            and line.strip().startswith("EMIT ") and "STOP_TURN" in line
        )
        assert APPROVAL_ARTIFACT_FIELD in refusal, (
            f"{unit} does not require this plan's own recorded approval: {refusal}"
        )
        # and must not accept the shared flag as sufficient on its own
        assert f"{APPROVAL_FLAG} != true AND" not in refusal, (
            f"{unit} still treats the shared run flag as an alternative: {refusal}"
        )


def test_the_plan_first_gate_still_owns_its_own_flag() -> None:
    """Tightening phase dispatch must not break the gate the flag belongs to.

    `accepted_plan_active` is `PlanFirstGate`'s contract — `PlanAcceptedExecutionContract`
    reads it to decide that an accepted plan is the controlling contract. That stays;
    what changed is that cf-plan's phase dispatch no longer *borrows* it.
    """
    rows = _sectioned_lines(
        REPO_ROOT / "skills/studio/modules/gates/plan-first.md", actions_only=True
    )
    setters = [line for unit, _, _, line in rows
               if unit == "PlanStorageChoice" and f"SET {APPROVAL_FLAG} = true" in line]
    assert len(setters) >= 2, f"the storage choice no longer records acceptance: {setters}"
    readers = [line for _, section, _, line in rows
               if section == "RULES" and APPROVAL_FLAG in line]
    assert readers, "nothing reads the flag any more, so it has become dead state"


def test_only_the_disk_option_claims_a_record_that_outlives_the_run() -> None:
    """The two storage options do not promise the same thing, so a test must tell them apart.

    Both set `accepted_plan_active`, which is run-scoped, and the flag-count guard above
    is satisfied by either — so it would stay green with the artifact clause deleted.
    Raised in review, and correctly: the disk option's added promise was prose that
    nothing asserted, which is a rule held by convention.

    What separates them is durability. A plan kept in session memory has no artifact to
    record acceptance in and must not claim one; a plan written to disk does, and that
    record is what a later run can still see.
    """
    rows = _sectioned_lines(
        REPO_ROOT / "skills/studio/modules/gates/plan-first.md", actions_only=True
    )
    options = {line.strip().split(" ", 1)[0]: line.strip()
               for unit, section, _, line in rows
               if unit == "PlanStorageChoice" and section == "OPTIONS"
               and line.strip()[:1].isdigit()}
    memory, disk = options.get("1", ""), options.get("2", "")
    assert "memory" in memory, f"option 1 is no longer the memory option: {options}"
    assert "disk" in disk, f"option 2 is no longer the disk option: {options}"

    assert "accepted it" in disk, \
        f"the disk option no longer records this gate's acceptance in what it writes: {disk}"
    assert "accepted it" not in memory, \
        f"the memory option claims a written record it has nowhere to keep: {memory}"


def test_the_plan_first_gate_never_writes_cf_plans_approval_field() -> None:
    """One record per channel, and this gate does not write the other's.

    `plan.approval_status` is what the phase dispatchers require, and no plan-first plan
    is ever phase-dispatched — `test_no_plan_first_continuation_is_a_phase_dispatcher`
    is what holds that. Writing the field here would record an approval collected by a
    menu that never showed the plan to the unit that would honour it, which is the exact
    failure the dispatch refusal exists to prevent.

    Naming it in prose to say which record is which is fine and is why this asserts on
    assignment rather than on mention.
    """
    rows = _sectioned_lines(
        REPO_ROOT / "skills/studio/modules/gates/plan-first.md", actions_only=True
    )
    writes = [line.strip() for _, _, _, line in rows
              if re.search(r"SET\s+plan\.approval_status", line)]
    assert not writes, f"the plan-first gate writes cf-plan's approval field: {writes}"


def test_cf_plan_does_not_borrow_the_plan_first_flag() -> None:
    """Two plan systems, two channels, and neither carries the other's contract.

    `accepted_plan_active` activates `PlanAcceptedExecutionContract`, which requires
    every plan item to carry a `DISPATCH:`, `INLINE:` or `GIT_FINALIZATION:` directive.
    A cf-plan plan has phases, not directives, so setting that flag from the
    decomposition gate imposed a contract its own plans cannot satisfy.

    The reverse direction was closed first — phase dispatch keys on the artifact, so a
    plan-first approval cannot authorise cf-plan phases. This is the other half.
    """
    for module in (REPO_ROOT / "skills/studio/modules/plan-compile.md",
                   REPO_ROOT / "skills/studio/modules/plan-validate-finalize.md"):
        borrowed = [
            line for _, _, _, line in _sectioned_lines(module, actions_only=True)
            if APPROVAL_FLAG in line
        ]
        assert not borrowed, (
            f"{module.name} sets or reads the plan-first flag: {borrowed}"
        )


def test_the_executing_units_state_the_refusal_in_their_own_rules() -> None:
    """A reader of the unit that executes must see what it refuses.

    The invariant was stated only in `PlanDispatch`, a sibling that names sub-agents.
    The units whose `DO` actually refuses said nothing about it in their own contract.
    """
    for unit, module in PLAN_EXECUTION_ENTRIES.items():
        rules = " ".join(
            line for row_unit, section, _, line in _sectioned_lines(Path(module))
            if row_unit == unit and section == "RULES"
        )
        assert "approval" in rules.lower() or APPROVAL_ARTIFACT_FIELD in rules, (
            f"{unit}'s own rules are silent on the approval it refuses without: {rules}"
        )


def test_a_revision_discards_phase_files_compiled_from_the_old_plan() -> None:
    """Re-approving a changed plan must not leave the superseded phases executable.

    `modify` routes back through decomposition, where a new package is written — but
    phase files compiled from the plan being replaced sit under the same directory and
    would be executed as though they belonged to the new one.
    """
    rows = _sectioned_lines(
        REPO_ROOT / "skills/studio/modules/plan-validate-finalize.md", actions_only=True)
    modify = [line for unit, _, _, line in rows
              if unit == "Phase4NextStepsMenu" and "5 modify" in line]
    assert modify, "the modify option is gone"
    for line in modify:
        assert "discard" in line, (
            f"a revision leaves phase files from the superseded plan in place: {line}")
        assert "phase file" in line, (
            f"a revision discards something, but not the phase files: {line}")


def test_the_approval_and_revision_maps_are_complete() -> None:
    """The same guard `PLAN_EXECUTION_ENTRIES` has, for the other two named sets.

    A hand-written list of approval points is a claim about the corpus, and a claim
    that nothing checks goes stale the moment a menu is added. Any menu that records
    the approval must appear in the approval map; any option that revokes it must
    appear in the revision map.
    """
    recording, revoking = {}, {}
    for path in _prompt_files():
        for unit, section, _, line in _sectioned_lines(path, actions_only=True):
            # Menu options only. A RULES line that *describes* the recording is not a
            # place the recording happens, and counting it listed `PlanWriteBriefPackage`
            # — the unit the rule is written on — as an approval point.
            if not re.match(r"\s*\d+ ", line):
                continue
            if f'{APPROVAL_ARTIFACT_FIELD}="approved"' in line or \
                    f"SET {APPROVAL_FLAG} = true" in line:
                recording[unit] = str(path)
            if f'{APPROVAL_ARTIFACT_FIELD}="revised"' in line or \
                    f"SET {APPROVAL_FLAG} = unset" in line:
                revoking[unit] = str(path)
    assert recording, "the approval signal changed; this guard measures nothing"
    missing_approval = set(recording) - set(PLAN_APPROVAL_POINTS)
    assert not missing_approval, (
        f"these menus record an approval and are unlisted: {missing_approval}")
    missing_revision = set(revoking) - set(PLAN_REVISION_OPTIONS)
    assert not missing_revision, (
        f"these menus revoke an approval and are unlisted: {missing_revision}")


def test_declining_or_stopping_never_records_an_approval() -> None:
    """The options that say no must not say yes.

    Every approval menu has a way out — decline, stop, write nothing. Those are the
    options a user picks *because* they do not agree, and an approval recorded on one
    would be the manufactured-consent failure in its purest form. Nothing asserted it.
    """
    for menu, module in PLAN_APPROVAL_POINTS.items():
        rows = _sectioned_lines(Path(module), actions_only=True)
        declining = [
            line for unit, section, _, line in rows
            if unit == menu and section in CLAUSE_SECTIONS
            # By what the option *does*, not by a word in its label: "briefs-only —
            # write plan.toml + briefs and stop there" contains "stop" and is an
            # approval, since the decomposition was shown and accepted; only the work
            # was deferred. A decline writes nothing.
            and ("nothing written" in line.lower() or "declined" in line.lower()
                 or re.search(r"->\s*STOP_TURN", line))
        ]
        for line in declining:
            assert f"SET {APPROVAL_FLAG} = true" not in line, (
                f"{menu} records an approval on an option that declines: {line}")
            assert f'{APPROVAL_ARTIFACT_FIELD}="approved"' not in line, (
                f"{menu} records an approval on an option that declines: {line}")


def test_every_deferred_continuation_in_the_changed_files_precedes_its_wait() -> None:
    """All of them, not the one file the first version happened to check.

    `WAIT` + `STOP_TURN` is a hard turn boundary, so a `CONTINUE ... after user.reply`
    written after it can never run. The revise option in the decomposition gate uses
    the same idiom as the modify option in the finalize menu, and only the second was
    pinned.
    """
    checked = 0
    for module in (REPO_ROOT / "skills/studio/modules/plan-compile.md",
                   REPO_ROOT / "skills/studio/modules/plan-validate-finalize.md"):
        for _, _, _, line in _sectioned_lines(module, actions_only=True):
            if "after user.reply" not in line or "WAIT " not in line:
                continue
            checked += 1
            assert line.index("CONTINUE ") < line.index("WAIT "), (
                f"{module.name}: the deferred continue sits after its WAIT: {line}")
    assert checked >= 2, f"expected both files to use the idiom, saw {checked}"


def test_no_plan_first_continuation_is_a_phase_dispatcher() -> None:
    """Why the plan-first gate does not write cf-plan's approval field.

    A reviewer read the disk option's "approval recorded in the file" as the field the
    phase dispatchers check, and asked for that field to be written there. It is a
    different record: this gate's plans resume through `PLAN_FIRST_CONTINUE`, whose
    every target is a workflow dispatch unit, and none of them dispatches a plan phase.

    Asserted rather than argued, because the answer is only true while it stays true.
    """
    continuations = {
        line.split("SET PLAN_FIRST_CONTINUE = ")[1].split(",")[0].split(";")[0].strip()
        for path in _prompt_files()
        for _, _, _, line in _sectioned_lines(path, actions_only=True)
        if "SET PLAN_FIRST_CONTINUE = " in line
    }
    assert continuations, "the continuation signal changed; this guard measures nothing"
    overlap = continuations & set(PLAN_EXECUTION_ENTRIES)
    assert not overlap, (
        f"a plan-first plan can now reach phase dispatch, so it does need the "
        f"dispatcher's approval field: {overlap}"
    )


#: The per-phase register's two fields in `plan.toml`. `status` already existed on every
#: `[[phases]]` entry, so the blocked state reuses it rather than adding a parallel flag.
#:
#: `awaiting_decision`, not `open_question`. The execution card's rule names the reason:
#: "never named for the brainstorm carryover it is not" — brainstorm already carries an
#: open-question concept, and one name over two meanings is how a register becomes a second
#: copy of the prompt. These tests were written against the rejected name and asserted it
#: for four days while the modules said otherwise.
REGISTER_FIELDS = ("awaiting_decision", 'status = "blocked"')


def test_an_indeterminate_gate_records_one_outcome_and_never_two() -> None:
    """A gate that records neither a ruling nor a question has silently guessed.

    This is the half the acceptance criteria call the register's reason for
    existing: without it the feature is "a ruling with worse bookkeeping".
    """
    rows = _sectioned_lines(
        Path("skills/studio/modules/runtime/pdsl-execution-card.md"), actions_only=True
    )
    rules = " ".join(line for _, section, _, line in rows if section == "RULES")
    assert "exactly one outcome" in rules, "the exactly-one semantics are not stated"
    # Split, because the two halves fail for different reasons and a composite assertion
    # reports whichever it likes: "never both" is the rule against recording a ruling and a
    # question together, "never neither" the rule against recording nothing at all, and an
    # indeterminate gate that records nothing has silently become a guess.
    assert "never both" in rules, f"nothing forbids recording both outcomes: {rules}"
    assert "never neither" in rules, f"nothing forbids recording no outcome: {rules}"


def test_the_register_never_stores_the_question_wording() -> None:
    """`explain-deliver-wrap.md:34` forbids saving open questions without consent.

    Recording *that* a gate ended in an open question, keyed by its decision key, is
    a fact about the gate. Recording the prose would be saving the question, which
    that shipped rule governs — so the register holds the key and the phase only.
    """
    rows = _sectioned_lines(
        Path("skills/studio/modules/runtime/pdsl-execution-card.md"), actions_only=True
    )
    rules = " ".join(line for _, section, _, line in rows if section == "RULES")
    assert "NEVER record the question's wording" in rules, rules
    # and the constraint it is protecting still exists to be protected
    consent = Path("skills/studio/modules/explain-deliver-wrap.md").read_text(encoding="utf-8")
    assert "without explicit user consent" in consent, (
        "the consent rule this design was shaped around is gone; re-check the design"
    )


def test_the_rejected_field_name_is_never_presented_as_the_canonical_one() -> None:
    """Two comment blocks sat here, the first naming `open_question` as the field.

    It was left behind by the rename and contradicted the block directly below it, which
    exists to say the name was rejected. A reader stopping at the first one takes the
    wrong name into the next module. Raised in review.
    """
    text = Path("tests/test_pdsl_keywords.py").read_text(encoding="utf-8")
    # The comment block directly above the constant, which is where the two contradicting
    # versions sat. Scoped there rather than file-wide, so this test's own prose about the
    # rejected name does not trip it.
    lines = text.splitlines()
    marker = next(i for i, line in enumerate(lines) if line.startswith("REGISTER_FIELDS ="))
    block = [line for line in lines[:marker][::-1]]
    comment = []
    for line in block:
        if not line.startswith("#"):
            break
        comment.append(line)
    said = " ".join(comment)
    assert "open_question" in said, (
        "the note explaining why the rejected name is not used has gone; without it the "
        "next author reintroduces it"
    )
    assert "not `open_question`" in said, (
        f"the comment block names the rejected field as canonical: {said}"
    )
    assert said.count("The per-phase register's two fields") == 1, (
        f"the superseded copy of this comment block is back: {said}"
    )


def test_a_blocked_phase_is_held_and_the_rest_still_run() -> None:
    """Phase-level blocking: the question stops its phase, not the whole plan.

    Blocking everything would be safest and unusable; blocking by decision key needs
    a key registry increment 3 has not built. The plan is already decomposed into
    phases with declared dependencies, so the phase is the unit that exists today.
    """
    for unit, module in PLAN_EXECUTION_ENTRIES.items():
        rows = _sectioned_lines(Path(module), actions_only=True)
        # the action and the rule are asserted apart, because an `or` across both let
        # the rule satisfy a claim about the action: stripping "dispatch only the rest"
        # from the DO action left this test passing.
        action = " ".join(
            line for row_unit, section, _, line in rows
            if row_unit == unit and section == "DO"
            and ("decision_held =" in line or "manually_held =" in line)
        )
        rules = " ".join(
            line for row_unit, section, _, line in rows
            if row_unit == unit and section == "RULES" and "held" in line
        )
        # The hold is **computed**, not read off the stored field. Review found that
        # nothing anywhere clears `awaiting_decision`, so a phase held once stayed held
        # after its answer arrived. Deciding from the phase's declared `needs` at dispatch
        # time removes that by construction: there is nothing to clear, because no
        # decision is taken from the record.
        assert "declared needs still leave a key unresolved" in action, (
            f"{unit} decides the hold from a stored field rather than by re-resolving: {action}"
        )
        assert 'status = "blocked"' in action, (
            f"{unit}'s DO does not honour the by-hand hold: {action}"
        )
        # The notice is its own line, and asserted separately from the set definitions:
        # joining them is what let one line satisfy a claim about another earlier in this
        # same test. It states the hold and dispatches nothing — review read "dispatch
        # only the rest", sitting before the git-policy gate, as an action verb.
        notice = " ".join(
            line for row_unit, section, _, line in rows
            if row_unit == unit and section == "DO"
            and line.strip().startswith("EMIT every phase in held_phases")
        )
        assert "runnable_phases minus held_phases" in notice, (
            f"{unit}'s notice does not say which phases are left to dispatch: {notice}"
        )
        assert "performs no dispatch" in notice, (
            f"{unit}'s notice still reads as if it dispatched: {notice}"
        )
        assert "dispatch the rest" in rules, (
            f"{unit} has no rule that unblocked phases still run: {rules}"
        )


def test_a_finished_phase_is_not_dispatched_again() -> None:
    """Held is not the only reason a phase must not run: done is another.

    Selecting the lowest-numbered *unheld* phase picked phase 1 of a plan whose phase 1
    had already finished, so resuming a part-done plan re-ran work and overwrote its
    output. Raised in review as a Major on both dispatch paths.
    """
    for unit, module in PLAN_EXECUTION_ENTRIES.items():
        rows = _sectioned_lines(Path(module), actions_only=True)
        runnable = " ".join(
            line for row_unit, section, _, line in rows
            if row_unit == unit and section == "DO" and "runnable_phases" in line
        )
        assert runnable, f"{unit} does not narrow the group to runnable phases: {unit}"
        assert "pending or unset" in runnable, (
            f"{unit} does not say which statuses may run: {runnable}"
        )
        for finished in ("done", "in_progress", "failed"):
            assert finished in runnable, (
                f"{unit} does not exclude a phase that is {finished}: {runnable}"
            )
        # A by-hand hold is not a lifecycle state, so scoping it to the runnable set hid
        # every manually blocked phase and its notice could never fire. Raised in review.
        manual = " ".join(
            line for row_unit, section, _, line in rows
            if row_unit == unit and section == "DO" and "manually_held =" in line
        )
        assert "runnable or not" in manual, (
            f"{unit} scopes the by-hand hold to the runnable set, hiding it: {manual}"
        )
        # And the reason given agrees with the architecture doc, which enumerates
        # `blocked` as a phase lifecycle state. An earlier wording here said a by-hand
        # hold "is not a lifecycle state", contradicting the document it implements —
        # raised in review. It is a state; it is not a *runnable* one, which is the
        # actual reason the scan cannot be scoped to the runnable set.
        assert "not a lifecycle state" not in manual, (
            f"{unit} denies that `blocked` is a lifecycle state, which execution-plans.md "
            f"declares it to be: {manual}"
        )
        # Declaring the runnable set is not using it. Reverting the selection line to
        # "the lowest-numbered [[phases]] entry" left the declaration in place and this
        # test green, which is the same shape as declaring a constant nothing reads.
        # Each line on its own: joining them let the `held_phases` line, which also says
        # "runnable", satisfy a claim about the selection line. That is the composite
        # assertion the analyser objects to, arrived at from the other direction.
        for name in ("decision_held =", "target_phase ="):
            line = " ".join(
                text for row_unit, section, _, text in rows
                if row_unit == unit and section == "DO" and name in text
            )
            if not line:
                continue                    # the compiler path selects no single phase
            assert "runnable" in line, (
                f"{unit} declares a runnable set and then ignores it in `{name}`: {line}"
            )
        rules = " ".join(
            line for row_unit, section, _, line in rows
            if row_unit == unit and section == "RULES" and "runnable" in line
        )
        assert "never one held" in rules or "nor one held" in rules, (
            f"{unit}'s rule does not keep both reasons a phase may not run: {rules}"
        )


def test_a_status_the_schema_does_not_know_is_held_not_skipped() -> None:
    """A mistyped status matched neither set, so it was dropped from both.

    `runnable` is pending-or-unset and the manual hold is exactly `"blocked"`; a
    hand-edited `Block` or `blocking` falls outside both and was silently treated as work
    that need not run — which is to say, as finished. An unreadable state is not evidence
    that a phase is done. Raised in review.
    """
    for unit, module in PLAN_EXECUTION_ENTRIES.items():
        rows = _sectioned_lines(Path(module), actions_only=True)
        unknown = " ".join(
            line for row_unit, section, _, line in rows
            if row_unit == unit and section == "DO" and "unknown_status_phases" in line
        )
        assert unknown, f"{unit} does not notice a status outside the declared set"
        for state in ("pending", "in_progress", "blocked", "done", "failed"):
            assert state in unknown, f"{unit} does not enumerate `{state}`: {unknown}"
        assert "held_phases = decision_held together with manually_held and unknown_status_phases" in \
            " ".join(line for row_unit, section, _, line in rows
                     if row_unit == unit and section == "DO"), (
            f"{unit} computes the unknown-status set and then does not hold on it")


def test_the_held_phase_notice_bounds_the_text_it_echoes() -> None:
    """The notice echoes plan.toml fields, and nothing in the module bounds them.

    `_bounded` lives in `plan_decisions.py` and the dispatch modules do not call into it —
    they interpret prose. So the rule has to be stated where the emitting happens, or a
    newline in a phase label forges a line in the notice. Raised in review; the same
    forgery class this story has already fixed in three other modules.
    """
    for unit, module in PLAN_EXECUTION_ENTRIES.items():
        rows = _sectioned_lines(Path(module), actions_only=True)
        notice = " ".join(
            line for row_unit, section, _, line in rows
            if row_unit == unit and section == "DO"
            and line.strip().startswith("EMIT every phase in held_phases")
        )
        assert notice, f"{unit} has no held-phase notice"
        assert "Bound and strip" in notice, (
            f"{unit}'s notice does not bound the author text it echoes: {notice}")
        assert "forges a line" in notice, (
            f"{unit}'s notice does not say why it bounds it: {notice}")


def test_a_plan_held_only_by_hand_is_not_told_to_answer_keys() -> None:
    """The notice has to match the reason, or it sends its reader to do nothing.

    Every phase blocked by hand and none waiting on a decision produced "answer the keys
    listed above" — with no keys listed, because a by-hand hold has none. Raised in review.

    Asserted on **both** dispatch paths, because the follow-up finding was exactly that:
    the native unit got three branches and the compiler unit got none, so a plan whose
    every runnable phase was held fell through to dispatching an empty group. A guard one
    of two siblings has is the shape that keeps coming back here.
    """
    stops = []
    for unit, module in PLAN_EXECUTION_ENTRIES.items():
        rows = _sectioned_lines(Path(module), actions_only=True)
        found = [
            line for row_unit, section, _, line in rows
            if row_unit == unit and section == "DO"
            and line.strip().startswith("EMIT") and "STOP_TURN" in line
            and ("no phase was dispatched" in line or "nothing to dispatch" in line
                 or "no compiler was dispatched" in line or "nothing to compile" in line)
        ]
        assert len(found) >= 5, (
            f"{unit} does not tell the five reasons nothing ran apart: {found}"
        )
        stops.extend(found)
    joined = " ".join(stops)
    assert "Lift those holds" in joined, f"a by-hand hold has no instruction of its own: {joined}"
    assert "no decision outstanding" in joined, (
        f"a by-hand hold is still reported as an open decision: {joined}"
    )
    assert "already done, in_progress or failed" in joined, (
        f"a plan with nothing left to run is reported as blocked: {joined}"
    )
    # Four reasons, and the conditions must not overlap: an all-done plan satisfied the
    # manual-hold branch vacuously, and a plan held both ways reported as decision-held
    # only. Raised in review.
    assert "some on an open decision, some by hand" in joined, (
        f"a plan held both ways is reported as one or the other: {joined}"
    )
    # Fifth reason, and the regression that made it necessary: the completion branch
    # excluded only the manual holds, so a plan whose every phase carried an invalid status
    # satisfied it and reported itself finished — two lines after this same sequence held
    # those phases and said an unreadable state is not evidence a phase is done. Raised in
    # review as a Major, and correctly: the contradiction was inside one DO block.
    assert "a status this plan's schema does not define" in joined, (
        f"an invalid-status plan has no terminal branch of its own: {joined}"
    )
    for unit, module in PLAN_EXECUTION_ENTRIES.items():
        rows = _sectioned_lines(Path(module), actions_only=True)
        terminal = [
            line for row_unit, section, _, line in rows
            if row_unit == unit and section == "DO"
            and line.strip().startswith("EMIT") and "STOP_TURN" in line
            and ("held" in line.lower() or "already done" in line)
        ]
        assert len(terminal) >= 5, f"{unit} has fewer than five terminal branches: {terminal}"
        for line in terminal:
            # Every branch names the unknown-status set, because that is what keeps the five
            # mutually exclusive: the invalid-status branch fires on it, and the other four
            # are guarded by it being empty. The completion branch not naming it at all is
            # exactly the defect this pins.
            assert "unknown_status_phases is" in line, (
                f"{unit} has a terminal branch that ignores an unreadable status: {line}"
            )
            # And each branch still says where the manual holds are — except the
            # invalid-status one, whose condition genuinely does not depend on them: it runs
            # ahead of the others so a reader fixes the unreadable status first.
            if "schema does not define" in line:
                assert "unknown_status_phases is not empty" in line, line
                continue
            assert ("manually_held is empty" in line or "manually_held is not empty" in line), (
                f"{unit} has a hold branch that does not say where the manual holds are: {line}"
            )
    # Both units, not one: the count above would be satisfied by three branches on either.
    assert joined.count("Lift those holds") == len(PLAN_EXECUTION_ENTRIES), (
        f"only one dispatch path distinguishes a by-hand hold: {joined}"
    )


def test_the_handoff_prompt_names_the_phase_it_actually_selected() -> None:
    """The fallback message said "Phase 1" while the unit had chosen some other phase.

    `target_phase` is the lowest-numbered runnable phase in neither held set, so it is
    phase 1 only until something earlier is done, blocked or held. The approved-dispatch
    path interpolates it; the not-approved / inline-fallback path carried a static
    "Return here after Phase 1 completes to continue with Phase 2." — text that was
    correct when the phase was always 1 and was not revisited when phase-skipping arrived
    in this change. A reader told to come back after phase 1 when phase 3 was dispatched
    goes looking for work nobody is doing. Raised in review.
    """
    rows = _sectioned_lines(Path(PLAN_EXECUTION_ENTRIES["PlanNativeExecute"]), actions_only=True)
    handoff = [
        line for unit, section, _, line in rows
        if unit == "PlanNativeExecute" and section == "DO" and "Paste this into a new chat" in line
    ]
    assert len(handoff) == 1, f"expected one handoff message, found {len(handoff)}: {handoff}"
    line = handoff[0]

    # Only what the user is shown. The trailing prose on a PDSL action is a note to the
    # next maintainer and may name `Phase 1` while explaining why the message must not.
    shown = re.findall(r'"((?:[^"\\]|\\.)*)"', line)
    assert shown, f"the handoff action emits no quoted message: {line}"
    message = shown[0]

    assert "{target_phase}" in message, (
        f"the handoff prompt does not name the phase the unit selected: {message}"
    )
    # The literal is what regressed, so the literal is what is refused -- a check for the
    # placeholder alone passes a message that interpolates it and still says "Phase 1".
    assert not re.search(r"\bPhase [0-9]", message), (
        f"the handoff prompt hardcodes a phase number: {message}"
    )


def test_the_completion_check_expects_only_what_was_dispatched() -> None:
    """A held phase produces no output, and that is not a compiler failure.

    Raised in review as a Major: holding phases back changed what "every expected output"
    means, and the paired completion unit still said every phase in the plan. It would
    report the hold as a failed compiler and send its author to re-dispatch work that was
    correctly withheld — the feature's own success looking like its failure.
    """
    rows = _sectioned_lines(Path("skills/studio/modules/plan-compiler-dispatch.md"),
                            actions_only=True)
    verify = " ".join(
        line for unit, section, _, line in rows
        if unit == "PlanPhaseCompilerComplete" and section == "DO" and "expected" in line
    )
    assert verify, "the completion unit no longer verifies expected outputs at all"
    assert "dispatch_group_id" in verify, (
        f"the expected-output set is not scoped to what was dispatched: {verify}"
    )
    assert "never every phase in the plan" in verify, (
        f"nothing rules out demanding output from a phase that was held: {verify}"
    )
    # `"held" in line` matched the verify line too — it contains "withheld" — so removing
    # this EMIT entirely left the assertion green off the wrong line. Anchored to the EMIT
    # and to a phrase the other line does not carry.
    held = " ".join(
        line for unit, section, _, line in rows
        if unit == "PlanPhaseCompilerComplete" and section == "DO"
        and line.strip().startswith("EMIT") and "still held" in line
    )
    assert held, "a plan that compiled only its unheld phases reports as fully compiled"


def test_the_register_is_a_record_and_never_the_authority() -> None:
    """Nothing clears `awaiting_decision`, so nothing may decide from it.

    Raised in review as a Major: the write path set the field and no rule, module or
    function ever removed it, so a phase held on an open decision stayed held after the
    answer was supplied. The lifecycle is fixed by taking the decision elsewhere rather
    than by adding a clear step whose omission would recreate exactly this.
    """
    rows = _sectioned_lines(
        Path("skills/studio/modules/runtime/pdsl-execution-card.md"), actions_only=True
    )
    rules = " ".join(line for _, section, _, line in rows if section == "RULES")
    assert "NEVER treat `awaiting_decision` as the authority" in rules, rules
    assert "re-resolves" in rules, f"the card does not say what decides instead: {rules}"
    # And the multi-key format, which was undefined: a phase blocked on two keys and told
    # about one sends its author back for the second.
    assert "list of every key" in rules, f"the register's shape is still singular: {rules}"


def test_holding_a_phase_back_is_announced_not_silent() -> None:
    """Skipping work in silence is the failure mode the loud-refusal rule exists for."""
    for unit, module in PLAN_EXECUTION_ENTRIES.items():
        rows = _sectioned_lines(Path(module), actions_only=True)
        # The per-phase notice specifically, not the all-held stop branches, which name
        # `held_phases` in their condition while being a different message.
        held = [
            line for row_unit, section, _, line in rows
            if row_unit == unit and section == "DO"
            and line.strip().startswith("EMIT every phase in held_phases")
        ]
        assert held, f"{unit} holds phases back without emitting which, or why"
        for line in held:
            assert "unresolved keys it is waiting on" in line, (
                f"the notice does not name what the phase is waiting on: {line}"
            )
            # Every key, not the first. And the one hold that has no key to name says so
            # rather than naming one it does not have.
            assert "all of them" in line, f"the notice names one key of several: {line}"
            assert "held by status alone" in line, (
                f"a by-hand hold would be announced as waiting on a key it has none of: {line}"
            )
