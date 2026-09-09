"""Validate PDSL prompt blocks through the PDSL CLI."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from unittest import mock

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
    """
    simple_mode_text = (REPO_ROOT / "skills/studio/modules/gates/simple-mode.md").read_text()
    bnw_text = (REPO_ROOT / "workflows/brave-new-world.md").read_text()

    trigger = "change mode"
    assert f'"{trigger}"' in simple_mode_text, (
        "Expected the literal mode-change trigger phrase to still be declared "
        "in gates/simple-mode.md; update this test if the wording changed."
    )

    activation_line = next(
        (line for line in bnw_text.splitlines() if "ALWAYS resolve semantically equivalent phrases" in line),
        None,
    )
    assert activation_line is not None, (
        "Expected to find BraveNewWorldActivate's activation-phrase rule in "
        "workflows/brave-new-world.md; update this test if the wording moved."
    )
    bnw_phrases = re.findall(r"'([^']+)'", activation_line)
    assert bnw_phrases, "Expected quoted activation phrases on that rule line"

    assert trigger not in bnw_phrases, (
        f"Mode-change trigger {trigger!r} collides with a Brave New World "
        "activation phrase; ADR-0023 requires these trigger sets to be disjoint."
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
# An undeclared gate is treated as `blocking` at runtime, so the existing
# surface is grandfathered and migrates gate by gate -- but the untyped surface
# must not grow. Anything not in this set has to declare a TYPE.
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
    "skills/studio/modules/plan-assess-decompose.md#1::DecompositionConfirmMenu",
    "skills/studio/modules/plan-compile.md#0::BriefCheckpointMenu",
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
UNTYPED_MENU_BASELINE_CEILING = 113



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


def test_the_untyped_menu_surface_does_not_grow() -> None:
    """A newly introduced MENU must declare a gate risk TYPE.

    The tail recorded in UNTYPED_MENU_BASELINE is grandfathered because an
    undeclared gate is treated as `blocking`, which is the conservative
    direction. What must not happen is the untyped surface growing, so a MENU
    that is neither typed nor in the baseline fails here.
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
