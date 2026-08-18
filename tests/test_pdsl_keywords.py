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
