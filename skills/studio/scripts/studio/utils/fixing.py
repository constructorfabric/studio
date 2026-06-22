"""Enrichment utilities for validation output: fixing prompts for LLM agents.

Each validation error/warning gets a ``fixing_prompt`` — a concise, actionable
instruction that an LLM agent can follow to resolve the issue.  The prompt
includes the clickable ``location`` (PATH:LINE), the affected ID, and relevant
constraint context (SYSTEM, KIND, template).
"""
# @cpt-begin:cpt-studio-algo-traceability-validation-fixing-prompts:p1:inst-fix-datamodel
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import error_codes as EC
# @cpt-end:cpt-studio-algo-traceability-validation-fixing-prompts:p1:inst-fix-datamodel


# ---------------------------------------------------------------------------
# Probable reasons registry — keyed by error code.
# Templates use {field} placeholders resolved from the issue dict at runtime.
# Available fields: id, id_kind, artifact_kind, target_kind, inst, location,
#   parent_id, headings, found_headings, heading_pattern, allowed, kinds, etc.
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-algo-traceability-validation-fixing-prompts:p1:inst-fix-define-reasons
_REASONS: Dict[str, List[str]] = {
    # Structure — task / checkbox consistency
    EC.CDSL_STEP_UNCHECKED: [
        "CDSL child step `{id}` was not marked as done after completing the work",
        "Parent `{id}` was checked prematurely while child steps were still pending",
    ],
    EC.PARENT_UNCHECKED_ALL_DONE: [
        "All child tasks under `{id}` were completed but the parent rollup checkbox was not updated",
        "Parent `{id}` was left unchecked after incremental completion of subtasks",
    ],
    EC.PARENT_CHECKED_NESTED_UNCHECKED: [
        "Parent `{parent_id}` was marked done before all nested items (e.g. `{id}`) were completed",
        "New subtask was added under already-checked parent `{parent_id}` without unchecking it",
    ],

    # Structure — references
    EC.REF_NO_DEFINITION: [
        "`{id}` was copy-pasted from another artifact but the source ID was never defined",
        "`{id}` was renamed or deleted in the defining artifact but references were not updated",
        "Typo in `{id}` (wrong slug, system, or kind segment)",
    ],
    EC.REF_DONE_DEF_NOT_DONE: [
        "Reference to `{id}` was checked as done but the source definition is still in progress",
        "Definition of `{id}` was unchecked (reverted) after the reference was already marked done",
    ],
    EC.DEF_DONE_REF_NOT_DONE: [
        "Definition of `{id}` was marked done in {def_artifact_kind} but the reference was not updated to [x]",
        "Reference to `{id}` was unchecked (reverted) after the definition was already completed",
        "Downstream artifact was regenerated and the checkbox state for `{id}` was lost",
    ],
    EC.REF_TASK_DEF_NO_TASK: [
        "Reference to `{id}` was given a task checkbox but the original definition does not use task tracking",
        "Definition of `{id}` was changed to remove task tracking without updating references",
    ],

    # Structure — heading numbering
    EC.HEADING_NUMBER_NOT_CONSECUTIVE: [
        "A numbered heading was deleted or reordered in {artifact_kind} without renumbering — expected `{expected_prefix}` after `{previous_prefix}`",
        "LLM generated headings with non-sequential numbering in {artifact_kind} artifact",
    ],

    # Structure — cross-artifact ID coverage
    EC.ID_NOT_REFERENCED: [
        "`{id}` was defined in {artifact_kind} but never referenced from {other_kinds}",
        "Reference to `{id}` was accidentally deleted during artifact editing",
        "`{id}` is newly added and cross-references have not yet been created",
    ],
    EC.ID_NOT_REFERENCED_NO_SCOPE: [
        "Only one artifact kind exists in scope — `{id}` cannot be cross-referenced yet",
        "Other artifact kinds have not been created for this system",
    ],

    # Constraints — ID kind presence
    EC.MISSING_CONSTRAINTS: [
        "Artifact kinds {kinds} were added to the registry but constraints.toml was not updated",
    ],
    EC.ID_KIND_NOT_ALLOWED: [
        "`{id}` uses kind `{id_kind}` not listed in allowed set {allowed} for {artifact_kind}",
        "Typo in the kind segment of `{id}` (e.g. `feat` instead of `fr`)",
        "constraints.toml was not updated after introducing kind `{id_kind}",
    ],
    EC.REQUIRED_ID_KIND_MISSING: [
        "{artifact_kind} artifact was generated without any `{id_kind}` IDs",
        "LLM skipped mandatory kind `{id_kind}` when generating {artifact_kind} from template",
        "`{id_kind}` IDs were accidentally placed under the wrong heading or removed from {artifact_kind}",
    ],

    # Constraints — task / priority on definitions
    EC.DEF_MISSING_TASK: [
        "`{id}` (kind `{id_kind}`) was written as plain text instead of a task list item `- [ ]`",
        "LLM did not follow the template which requires task checkboxes for kind `{id_kind}`",
    ],
    EC.DEF_PROHIBITED_TASK: [
        "Task checkbox was added to `{id}` but kind `{id_kind}` does not allow task tracking",
        "Copy-paste from another kind that uses task tracking into `{id_kind}` section",
    ],
    EC.DEF_MISSING_PRIORITY: [
        "Priority marker (🔴/🟡/🟢) was not added to `{id}` (kind `{id_kind}` requires it)",
        "LLM omitted priority when generating `{id_kind}` IDs in {artifact_kind}",
    ],
    EC.DEF_PROHIBITED_PRIORITY: [
        "Priority marker was added to `{id}` but kind `{id_kind}` prohibits priority",
    ],

    # Constraints — heading placement
    EC.DEF_WRONG_HEADINGS: [
        "`{id}` (kind `{id_kind}`) was placed under {found_headings} instead of required {headings}",
        "LLM put `{id_kind}` IDs under a general section instead of the required heading in {artifact_kind}",
        "Heading structure of {artifact_kind} was reorganized but `{id}` was not moved accordingly",
    ],

    # Constraints — heading contract
    EC.HEADING_MISSING: [
        "Required heading `{heading_pattern}` (level {heading_level}) was not included when generating {artifact_kind}",
        "LLM deviated from the template structure of {artifact_kind}",
        "Heading `{heading_pattern}` was accidentally deleted during editing of {artifact_kind}",
    ],
    EC.HEADING_PROHIBITS_MULTIPLE: [
        "Heading `{heading_pattern}` appears more than once in {artifact_kind} but only one occurrence is allowed",
        "LLM duplicated the `{heading_pattern}` section when expanding {artifact_kind}",
    ],
    EC.HEADING_REQUIRES_MULTIPLE: [
        "Heading `{heading_pattern}` requires at least 2 occurrences in {artifact_kind} (e.g. repeated feature blocks)",
        "Only one `{heading_pattern}` instance was generated when the template expects multiple",
    ],
    EC.HEADING_NUMBERING_MISMATCH: [
        "Heading `{heading_pattern}` in {artifact_kind} has/lacks numbering prefix contrary to constraint (numbered={numbered})",
        "LLM inconsistently applied numbered heading format in {artifact_kind}",
    ],

    # Constraints — cross-reference coverage
    EC.REF_TARGET_NOT_IN_SCOPE: [
        "`{target_kind}` artifact has not been created yet for this system — `{id}` cannot be referenced",
        "`{target_kind}` artifact was removed from the registry",
    ],
    EC.REF_MISSING_FROM_KIND: [
        "`{id}` (defined in {artifact_kind}) was never referenced in any `{target_kind}` artifact",
        "`{target_kind}` artifact exists but LLM did not include a reference to `{id}`",
        "Reference to `{id}` was accidentally removed during `{target_kind}` artifact regeneration",
    ],
    EC.REF_WRONG_HEADINGS: [
        "Reference to `{id}` in `{target_kind}` is under {found_headings} but must be under {headings}",
        "LLM placed the reference to `{id}` under a generic section instead of the required heading",
    ],
    EC.REF_MISSING_TASK_FOR_TRACKED: [
        "Reference to `{id}` in `{target_kind}` lacks a task checkbox — definition in {artifact_kind} is task-tracked",
        "LLM referenced `{id}` as plain text instead of a task list item in `{target_kind}`",
    ],
    EC.REF_FROM_PROHIBITED_KIND: [
        "Reference to `{id}` was placed in `{target_kind}` but references from `{target_kind}` are prohibited for {artifact_kind} IDs",
        "LLM included a cross-reference to `{id}` in `{target_kind}` violating coverage rules",
    ],
    EC.REF_MISSING_TASK: [
        "Reference to `{id}` in `{target_kind}` lacks required task checkbox `- [ ]`",
    ],
    EC.REF_PROHIBITED_TASK: [
        "Reference to `{id}` in `{target_kind}` has a task checkbox but task tracking is prohibited here",
    ],
    EC.REF_MISSING_PRIORITY: [
        "Reference to `{id}` in `{target_kind}` lacks required priority marker",
    ],
    EC.REF_PROHIBITED_PRIORITY: [
        "Reference to `{id}` in `{target_kind}` has a priority marker but priority is prohibited here",
    ],

    # Code traceability — markers
    EC.MARKER_DUP_BEGIN: [
        "Duplicate @cpt-begin for `{id}` (inst `{inst}`) without closing the previous block",
        "Copy-paste error when adding traceability markers for `{id}`",
    ],
    EC.MARKER_END_NO_BEGIN: [
        "@cpt-end for `{id}` (inst `{inst}`) has no matching @cpt-begin",
        "The opening marker for `{id}` was deleted or has a mismatched ID/phase/instance",
    ],
    EC.MARKER_EMPTY_BLOCK: [
        "Block for `{id}` (inst `{inst}`) was opened but no implementation code was added between markers",
        "Placeholder markers for `{id}` were left without actual code",
    ],
    EC.MARKER_BEGIN_NO_END: [
        "@cpt-begin for `{id}` (inst `{inst}`) was never closed with @cpt-end",
        "End marker for `{id}` was accidentally deleted or has a mismatched ID",
    ],
    EC.MARKER_DUP_SCOPE: [
        "Scope marker for `{id}` appears twice in the same file — first at line {first_occurrence}",
        "Copy-paste error when adding scope markers for `{id}`",
    ],

    # Code traceability — cross-validation
    EC.CODE_DOCS_ONLY: [
        "Code file contains @cpt markers but traceability mode is DOCS-ONLY",
        "Traceability mode was changed from FULL to DOCS-ONLY without removing code markers",
    ],
    EC.CODE_ORPHAN_REF: [
        "Code marker references `{id}` which does not exist in any artifact",
        "`{id}` was renamed or removed from the artifact without updating code markers",
    ],
    EC.CODE_TASK_UNCHECKED: [
        "`{id}` is marked to_code but its task checkbox is not checked yet — implementation started prematurely",
        "Task for `{id}` was unchecked (reverted) after code was already written",
    ],
    EC.CODE_NO_MARKER: [
        "`{id}` is marked to_code=\"true\" but no @cpt marker referencing it exists in the codebase",
        "Code marker for `{id}` was accidentally removed or was never added",
    ],
    EC.CODE_INST_MISSING: [
        "CDSL instruction `{inst}` of `{id}` exists in the artifact but has no @cpt-begin/@cpt-end block in code",
        "Instruction `{inst}` was renamed in the artifact without updating the code marker",
        "Code implementation for instruction `{inst}` was not yet written",
    ],
    EC.CODE_INST_ORPHAN: [
        "Code block `inst-{inst}` of `{id}` has no matching CDSL step in the artifact",
        "Instruction `{inst}` was renamed or removed from the artifact without updating the code marker",
        "Instruction slug `{inst}` has a typo in the artifact CDSL step",
    ],

    # TOC (Table of Contents) validation
    EC.TOC_MISSING: [
        "Document was created or regenerated without a Table of Contents section",
        "TOC section was accidentally deleted during editing",
    ],
    EC.TOC_ANCHOR_BROKEN: [
        "Heading was renamed or removed but the TOC entry was not updated",
        "TOC was manually edited and an anchor slug was mistyped",
    ],
    EC.TOC_HEADING_NOT_IN_TOC: [
        "A new heading was added to the document but the TOC was not regenerated",
        "TOC was generated with a `--max-level` that excludes this heading",
    ],
    EC.TOC_STALE: [
        "Headings were added, removed, reordered, or renamed since the TOC was last generated",
        "TOC was manually edited instead of being regenerated with `cfs toc`",
    ],

    # File errors
    EC.FILE_READ_ERROR: [
        "File could not be read — check encoding (must be UTF-8) or file permissions",
    ],
    EC.FILE_LOAD_ERROR: [
        "Code file failed to load — the file may be missing, empty, or have encoding issues",
    ],
}
# @cpt-end:cpt-studio-algo-traceability-validation-fixing-prompts:p1:inst-fix-define-reasons


# @cpt-begin:cpt-studio-algo-traceability-validation-fixing-prompts:p1:inst-fix-datamodel
class _SafeDict(dict):
    """dict subclass that returns '{key}' for missing keys in str.format_map()."""
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _resolve_reasons(templates: List[str], issue: Dict[str, object]) -> List[str]:
    """Render reason templates with actual issue field values."""
    ctx = _SafeDict({k: v for k, v in issue.items() if v is not None})
    return [tpl.format_map(ctx) for tpl in templates]
# @cpt-end:cpt-studio-algo-traceability-validation-fixing-prompts:p1:inst-fix-datamodel


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-algo-traceability-validation-fixing-prompts:p1:inst-fix-enrich
def enrich_issues(
    issues: List[Dict[str, object]],
    project_root: Optional[Path] = None,
    strip_path: bool = True,
) -> None:
    """Add ``fixing_prompt``, ``reasons``, and optionally strip ``path`` from every issue (in-place).

    After this call each issue has ``location`` (PATH:LINE) + ``line``.
    When *strip_path* is ``True`` (the default) the redundant ``path`` key is
    removed — the consumer reconstructs a pure path from ``location`` if
    needed.  Pass ``strip_path=False`` to preserve the ``path`` key (useful
    when callers need the original path after enrichment).
    """
    for issue in issues:
        prompt = _build_fixing_prompt(issue, project_root=project_root)
        code = str(issue.get("code") or "")
        reasons = _resolve_reasons(_REASONS[code], issue) if code and code in _REASONS else []
        if reasons:
            issue["reasons"] = reasons
        if prompt:
            text = f"studio: {prompt}"
            if reasons:
                text += " | Probable causes: " + "; ".join(reasons)
            issue["fixing_prompt"] = text
        if strip_path:
            issue.pop("path", None)
# @cpt-end:cpt-studio-algo-traceability-validation-fixing-prompts:p1:inst-fix-enrich


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-algo-traceability-validation-fixing-prompts:p1:inst-fix-datamodel
def _rel_loc(issue: Dict[str, object], project_root: Optional[Path] = None) -> str:
    """Return a relative location string (``rel/path:line``)."""
    loc = str(issue.get("location") or f"{issue.get('path')}:{issue.get('line', 1)}")
    if project_root is not None:
        prefix = project_root.as_posix()
        # Strip absolute project_root prefix, keep colon+line
        if loc.startswith(prefix + "/"):
            loc = loc[len(prefix) + 1:]
        elif loc.startswith(prefix):
            loc = loc[len(prefix):]
    return loc


def _tpl_hint(issue: Dict[str, object]) -> str:
    t = str(issue.get("id_kind_template") or "")
    return f" Template: `{t}`." if t else ""


def _kind_ctx(issue: Dict[str, object]) -> str:
    """Return a short 'Kind: X, Artifact: Y' context string."""
    parts: List[str] = []
    ik = str(issue.get("id_kind") or "")
    ak = str(issue.get("artifact_kind") or "")
    if ik:
        parts.append(f"kind=`{ik}`")
    if ak:
        parts.append(f"artifact=`{ak}`")
    return (" (" + ", ".join(parts) + ")") if parts else ""


def _headings_hint(issue: Dict[str, object], *, key: str = "target_headings", info_key: str = "target_headings_info") -> str:
    """Return a hint like ' Under section: `feature-capabilities` (Capabilities and features).'"""
    headings = issue.get(key) or []
    if not headings:
        return ""
    info = issue.get(info_key) or []
    info_map: Dict[str, str] = {}
    for item in info:
        if isinstance(item, dict):
            hid = str(item.get("id") or "")
            desc = str(item.get("description") or "")
            if hid and desc:
                info_map[hid] = desc
    parts: List[str] = []
    for h in headings:
        desc = info_map.get(str(h))
        if desc:
            parts.append(f"`{h}` ({desc})")
        else:
            parts.append(f"`{h}`")
    return f" Under section: {', '.join(parts)}."


def _rel_path_str(abs_path: str, project_root: Optional[Path]) -> str:
    """Make an absolute path relative to project_root."""
    tp = str(abs_path)
    if project_root is not None:
        prefix = project_root.as_posix()
        if tp.startswith(prefix + "/"):
            tp = tp[len(prefix) + 1:]
        elif tp.startswith(prefix):
            tp = tp[len(prefix):]
    return tp
# @cpt-end:cpt-studio-algo-traceability-validation-fixing-prompts:p1:inst-fix-datamodel


@dataclass(frozen=True)
class _FixPromptContext:
    """Precomputed values reused across prompt builders."""

    issue: Dict[str, object]
    project_root: Optional[Path]
    code: str
    loc: str
    cpt_id: str
    id_kind: str
    target_kind: str
    parent_id: str
    tpl: str
    ctx: str


def _build_fix_prompt_context(
    issue: Dict[str, object],
    project_root: Optional[Path],
) -> _FixPromptContext:
    """Build shared prompt-generation context for one validation issue."""
    return _FixPromptContext(
        issue=issue,
        project_root=project_root,
        code=str(issue.get("code") or ""),
        loc=_rel_loc(issue, project_root),
        cpt_id=str(issue.get("id") or ""),
        id_kind=str(issue.get("id_kind") or ""),
        target_kind=str(issue.get("target_kind") or ""),
        parent_id=str(issue.get("parent_id") or ""),
        tpl=_tpl_hint(issue),
        ctx=_kind_ctx(issue),
    )


def _prompt_for_structure_task_consistency(ctx: _FixPromptContext) -> Optional[str]:
    if ctx.code == EC.CDSL_STEP_UNCHECKED:
        return (
            f"Open `{ctx.loc}` and mark the CDSL step as checked `[x]`, "
            f"or uncheck parent ID `{ctx.cpt_id}` if the step is incomplete."
        )
    if ctx.code == EC.PARENT_UNCHECKED_ALL_DONE:
        return (
            f"Open `{ctx.loc}` and check parent ID `{ctx.cpt_id}` — "
            f"all its nested task items are already done."
        )
    if ctx.code == EC.PARENT_CHECKED_NESTED_UNCHECKED:
        pid = ctx.parent_id or ctx.cpt_id
        return (
            f"Open `{ctx.loc}` and either uncheck parent `{pid}`, "
            f"or check all nested unchecked items under it."
        )
    return None


def _prompt_for_structure_references(ctx: _FixPromptContext) -> Optional[str]:
    if ctx.code == EC.REF_NO_DEFINITION:
        return (
            f"Open `{ctx.loc}`: add a definition for `{ctx.cpt_id}` in the appropriate artifact, "
            f"or remove this dangling reference."
        )
    if ctx.code == EC.REF_DONE_DEF_NOT_DONE:
        return (
            f"Open `{ctx.loc}`: uncheck the reference to `{ctx.cpt_id}`, "
            f"or check the source definition in its origin artifact."
        )
    if ctx.code == EC.DEF_DONE_REF_NOT_DONE:
        def_kind = str(ctx.issue.get("def_artifact_kind") or "source")
        return (
            f"Open `{ctx.loc}`: check the reference to `{ctx.cpt_id}` as [x] to match the done definition in {def_kind}, "
            f"or uncheck the definition if the work is not actually complete."
        )
    if ctx.code == EC.REF_TASK_DEF_NO_TASK:
        return (
            f"Open `{ctx.loc}`: remove the task checkbox from the reference to `{ctx.cpt_id}`, "
            f"or add a task checkbox to its definition."
        )
    if ctx.code == EC.ID_NOT_REFERENCED:
        other = ctx.issue.get("other_kinds") or []
        other_s = ", ".join(f"`{k}`" for k in other) if other else "other artifact kinds"
        return (
            f"Open `{ctx.loc}`: add a reference to `{ctx.cpt_id}` in {other_s}, "
            f"or verify this ID is intentionally unreferenced."
        )
    return None


def _prompt_for_constraints(ctx: _FixPromptContext) -> Optional[str]:
    prompt_map = {
        EC.HEADING_NUMBER_NOT_CONSECUTIVE: (
            f"Open `{ctx.loc}`: fix heading number — "
            f"expected `{ctx.issue.get('expected_prefix')}` after `{ctx.issue.get('previous_prefix')}`."
        ),
        EC.MISSING_CONSTRAINTS: f"Add constraint definitions for kinds {ctx.issue.get('kinds')} in `constraints.toml`.",
        EC.ID_KIND_NOT_ALLOWED: (
            f"Open `{ctx.loc}`: ID `{ctx.cpt_id}` uses kind `{ctx.id_kind}` "
            f"not in allowed set {ctx.issue.get('allowed')}. "
            f"Change the ID or update `constraints.toml` to allow `{ctx.id_kind}`."
        ),
        EC.DEF_MISSING_TASK: f"Open `{ctx.loc}`: add `- [ ]` before `{ctx.cpt_id}`{ctx.ctx}.{ctx.tpl}",
        EC.DEF_PROHIBITED_TASK: (
            f"Open `{ctx.loc}`: remove the task checkbox from `{ctx.cpt_id}` — "
            f"kind `{ctx.id_kind}` prohibits task tracking."
        ),
        EC.DEF_MISSING_PRIORITY: (
            f"Open `{ctx.loc}`: add a priority marker "
            f"(e.g. 🔴 HIGH / 🟡 MEDIUM / 🟢 LOW) to `{ctx.cpt_id}`{ctx.ctx}."
        ),
        EC.DEF_PROHIBITED_PRIORITY: (
            f"Open `{ctx.loc}`: remove the priority marker from `{ctx.cpt_id}` — "
            f"kind `{ctx.id_kind}` prohibits priority."
        ),
    }
    if ctx.code in prompt_map:
        return prompt_map[ctx.code]
    if ctx.code == EC.REQUIRED_ID_KIND_MISSING:
        path_s = ctx.loc.rsplit(':', 1)[0] if ':' in ctx.loc else ctx.loc
        hdg = _headings_hint(ctx.issue)
        return f"Add at least one `{ctx.id_kind}` ID definition in `{path_s}`{ctx.ctx}.{hdg}{ctx.tpl}"
    if ctx.code == EC.DEF_WRONG_HEADINGS:
        hdg = _headings_hint(ctx.issue, key="headings", info_key="headings_info")
        return (
            f"Open `{ctx.loc}`: move `{ctx.cpt_id}` to a required section.{hdg} "
            f"Currently under: {ctx.issue.get('found_headings')}.{ctx.tpl}"
        )
    return None


def _prompt_for_heading_contract(ctx: _FixPromptContext) -> Optional[str]:
    if ctx.code == EC.HEADING_MISSING:
        pat = ctx.issue.get("heading_pattern")
        pat_s = f" matching `{pat}`" if pat else ""
        path_s = ctx.loc.rsplit(':', 1)[0] if ':' in ctx.loc else ctx.loc
        return f"Add a level-{ctx.issue.get('heading_level')} heading{pat_s} to `{path_s}`{ctx.ctx}."
    if ctx.code == EC.HEADING_PROHIBITS_MULTIPLE:
        return f"Open `{ctx.loc}`: remove this duplicate heading — only one occurrence is allowed."
    if ctx.code == EC.HEADING_REQUIRES_MULTIPLE:
        return (
            f"Open `{ctx.loc}`: add more headings matching this pattern — "
            f"at least 2 occurrences required."
        )
    if ctx.code == EC.HEADING_NUMBERING_MISMATCH:
        numbered = ctx.issue.get("numbered")
        verb = "is required but missing" if numbered is True else "is prohibited but present"
        return f"Open `{ctx.loc}`: heading numbering {verb}."
    return None


def _prompt_for_cross_ref_coverage(ctx: _FixPromptContext) -> Optional[str]:
    if ctx.code == EC.REF_TARGET_NOT_IN_SCOPE:
        return (
            f"At `{ctx.loc}`: `{ctx.cpt_id}` requires a reference in `{ctx.target_kind}` artifact, "
            f"but no `{ctx.target_kind}` artifact exists in scope."
        )
    if ctx.code == EC.REF_MISSING_FROM_KIND:
        hdg = _headings_hint(ctx.issue)
        target_path = ctx.issue.get("target_artifact_path")
        suggested_path = ctx.issue.get("target_artifact_suggested_path")
        if target_path:
            target_path_s = _rel_path_str(str(target_path), ctx.project_root)
            return (
                f"Open `{ctx.loc}`: add a reference to `{ctx.cpt_id}` "
                f"in `{target_path_s}`{ctx.ctx}.{hdg}{ctx.tpl}"
            )
        if suggested_path:
            return (
                f"Open `{ctx.loc}`: `{ctx.target_kind}` artifact missing — "
                f"create `{suggested_path}` and add a reference to `{ctx.cpt_id}`{ctx.ctx}.{hdg}{ctx.tpl}"
            )
        return (
            f"Open `{ctx.loc}`: add a reference to `{ctx.cpt_id}` "
            f"in a `{ctx.target_kind}` artifact (ask user for the artifact path){ctx.ctx}.{hdg}{ctx.tpl}"
        )
    if ctx.code == EC.REF_WRONG_HEADINGS:
        hdg = _headings_hint(ctx.issue, key="headings", info_key="headings_info")
        return (
            f"Open `{ctx.loc}`: move reference to `{ctx.cpt_id}` to a required section.{hdg} "
            f"Currently under: {ctx.issue.get('found_headings')}.{ctx.tpl}"
        )
    prompt_map = {
        EC.REF_MISSING_TASK_FOR_TRACKED: (
            f"Open `{ctx.loc}`: add `- [ ]` before the reference to `{ctx.cpt_id}` — "
            f"the definition is task-tracked{ctx.ctx}."
        ),
        EC.REF_FROM_PROHIBITED_KIND: (
            f"Open `{ctx.loc}`: remove reference to `{ctx.cpt_id}` — "
            f"references from `{ctx.target_kind}` are prohibited{ctx.ctx}."
        ),
        EC.REF_MISSING_TASK: f"Open `{ctx.loc}`: add `- [ ]` before the reference to `{ctx.cpt_id}`{ctx.ctx}.",
        EC.REF_PROHIBITED_TASK: f"Open `{ctx.loc}`: remove task checkbox from reference to `{ctx.cpt_id}`{ctx.ctx}.",
        EC.REF_MISSING_PRIORITY: f"Open `{ctx.loc}`: add priority marker to reference of `{ctx.cpt_id}`{ctx.ctx}.",
        EC.REF_PROHIBITED_PRIORITY: f"Open `{ctx.loc}`: remove priority marker from reference of `{ctx.cpt_id}`{ctx.ctx}.",
    }
    return prompt_map.get(ctx.code)


def _prompt_for_code_traceability(ctx: _FixPromptContext) -> Optional[str]:
    prompt_map = {
        EC.MARKER_DUP_BEGIN: (
            f"Open `{ctx.loc}`: close the previous `@cpt-begin` block for `{ctx.cpt_id}` "
            f"with `@cpt-end` before opening a new one."
        ),
        EC.MARKER_END_NO_BEGIN: (
            f"Open `{ctx.loc}`: add a matching `@cpt-begin` before this `@cpt-end`, "
            f"or remove the orphan marker."
        ),
        EC.MARKER_EMPTY_BLOCK: (
            f"Open `{ctx.loc}`: add implementation code between "
            f"the @cpt-begin and @cpt-end markers for `{ctx.cpt_id}`."
        ),
        EC.MARKER_BEGIN_NO_END: f"Open `{ctx.loc}`: add `@cpt-end` to close the block for `{ctx.cpt_id}`.",
        EC.MARKER_DUP_SCOPE: (
            f"Open `{ctx.loc}`: remove duplicate scope marker for `{ctx.cpt_id}`. "
            f"First occurrence at line {ctx.issue.get('first_occurrence')}."
        ),
        EC.CODE_DOCS_ONLY: f"Open `{ctx.loc}`: remove all @cpt markers — traceability mode is DOCS-ONLY.",
        EC.CODE_ORPHAN_REF: (
            f"Open `{ctx.loc}`: define `{ctx.cpt_id}` in an artifact, "
            f"or remove the code marker."
        ),
        EC.CODE_TASK_UNCHECKED: (
            f"Check the task checkbox `[x]` for `{ctx.cpt_id}` in the artifact "
            f"before referencing it in code. Code ref at `{ctx.loc}`."
        ),
        EC.CODE_NO_MARKER: f"Add a code traceability marker `@cpt-*:{ctx.cpt_id}:p1` in the codebase.",
    }
    if ctx.code in prompt_map:
        return prompt_map[ctx.code]
    if ctx.code == EC.CODE_INST_MISSING:
        inst = str(ctx.issue.get("inst") or "?")
        return (
            f"Add `@cpt-begin:{ctx.cpt_id}:p1:inst-{inst}` / `@cpt-end:...` block in the code, "
            f"or fix the instruction slug `{inst}` in the artifact if it is a typo."
        )
    if ctx.code == EC.CODE_INST_ORPHAN:
        inst = str(ctx.issue.get("inst") or "?")
        return (
            f"Open `{ctx.loc}`: the code block `inst-{inst}` of `{ctx.cpt_id}` has no matching CDSL step in the artifact. "
            f"Add the CDSL step in the artifact, or rename/remove the code marker if the instruction was renamed."
        )
    return None


def _prompt_for_toc_and_warnings(ctx: _FixPromptContext) -> Optional[str]:
    path_s = ctx.loc.rsplit(':', 1)[0] if ':' in ctx.loc else ctx.loc
    if ctx.code == EC.TOC_MISSING:
        return f"Add a Table of Contents to `{path_s}`. Run `cfs toc {path_s}` to generate one automatically."
    if ctx.code == EC.TOC_ANCHOR_BROKEN:
        display = str(ctx.issue.get("toc_display") or "")
        anchor = str(ctx.issue.get("toc_anchor") or "")
        return (
            f"Open `{ctx.loc}`: TOC entry `[{display}](#{anchor})` has a broken anchor. "
            f"Regenerate with `cfs toc` or fix the anchor manually."
        )
    if ctx.code == EC.TOC_HEADING_NOT_IN_TOC:
        heading = str(ctx.issue.get("heading_text") or "")
        return (
            f"Open `{ctx.loc}`: heading `{heading}` is missing from the Table of Contents. "
            f"Run `cfs toc {path_s}` to regenerate."
        )
    if ctx.code == EC.TOC_STALE:
        return f"Table of Contents in `{path_s}` is outdated. Run `cfs toc {path_s}` to regenerate."
    if ctx.code == EC.ID_NOT_REFERENCED_NO_SCOPE:
        return (
            f"At `{ctx.loc}`: `{ctx.cpt_id}` has no references — "
            f"consider adding other artifact kinds that reference it."
        )
    return None


# ---------------------------------------------------------------------------
# Prompt registry — keyed by error ``code`` (see error_codes.py).
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-algo-traceability-validation-fixing-prompts:p1:inst-fix-build-prompt
def _build_fixing_prompt(issue: Dict[str, object], project_root: Optional[Path] = None) -> Optional[str]:
    ctx = _build_fix_prompt_context(issue, project_root)
    builders: List[Callable[[_FixPromptContext], Optional[str]]] = [
        _prompt_for_structure_task_consistency,
        _prompt_for_structure_references,
        _prompt_for_constraints,
        _prompt_for_heading_contract,
        _prompt_for_cross_ref_coverage,
        _prompt_for_code_traceability,
        _prompt_for_toc_and_warnings,
    ]
    for builder in builders:
        prompt = builder(ctx)
        if prompt is not None:
            return prompt
    return None
    # @cpt-end:cpt-studio-algo-traceability-validation-fixing-prompts:p1:inst-fix-warnings
# @cpt-end:cpt-studio-algo-traceability-validation-fixing-prompts:p1:inst-fix-build-prompt
