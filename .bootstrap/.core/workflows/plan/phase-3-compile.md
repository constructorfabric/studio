---
cf: true
type: workflow-phase
name: plan-phase-3-compile
description: "Invoke when /cf-plan enters Phase 3 to write the plan manifest, generate compilation briefs, present the post-brief choice menu, produce phase files or phase-generation prompts, and validate compiled phase files."
loaded_by: workflows/plan.md
version: 1.0
---

# Phase 3: Compile Phase Files

<!-- toc -->

- [3.1 Write Plan Manifest](#31-write-plan-manifest)
- [3.2 Generate Compilation Briefs (from Template)](#32-generate-compilation-briefs-from-template)
- [3.2A Stop After Briefs & Ask For Next Step](#32a-stop-after-briefs--ask-for-next-step)
- [3.3 Produce Phase Files Or Phase-Generation Prompts](#33-produce-phase-files-or-phase-generation-prompts)
- [3.4 Validate Phase Files](#34-validate-phase-files)

<!-- /toc -->

Open and follow `{cf-studio-path}/.core/requirements/plan-template.md`.

Phase 3 is split to minimize context: write the manifest, write briefs, then stop for an explicit user choice about how phase files should be produced.

The manifest and all `brief-*` files are mandatory outputs of `/cf-plan`. After they are on disk, the workflow MUST pause and ask whether to continue with inline phase generation, per-brief phase-generation prompts, or `cf-phase-compiler` subagents.

## 3.1 Write Plan Manifest

Set CF_PHASE_GATE=released_for_orchestrator_write with scope = {cf-studio-path}/.plans/{task-slug}/plan.toml before writing the plan.toml file.

Write `plan.toml` after decomposition and lifecycle selection, but **before** phase compilation:
```toml
[meta]
# Variables resolved in Phase 0 from `{cfs_cmd} --json info`.
# Persisted here so the runtime can read them on resume after context compaction
# without re-deriving them; refresh by re-running `{cfs_cmd} --json info` if stale.
cfs_cmd = "{resolved cfs_cmd value}"            # e.g. "cfs" or "python3 /abs/path/.cf-studio/.core/skills/studio/scripts/studio.py"
cf_studio_path = "{absolute cf_studio_path}"  # e.g. "/abs/path/.cf-studio"
project_root = "{absolute project_root}"        # e.g. "/abs/path/repo"
# variables = "{path to JSON snapshot}"          # OPTIONAL: full `variables` dict from `info` output

[plan]
task = "{task description}"
type = "{generate|analyze|implement}"
target = "{artifact kind}"          # e.g. "PRD", "DESIGN", "FEATURE"
target_key = "{canonical target identity}" # deterministic naming/reuse key for this plan target
kit_path = "{absolute path to kit}" # e.g. "/abs/path/config/kits/sdlc"
created = "{ISO 8601 timestamp}"
lifecycle = "{gitignore|cleanup|archive|manual}"
execution_status = "not_started"     # not_started|briefs_only|prompts_emitted|in_progress|done|failed
lifecycle_status = "pending"         # pending|ready|partial|in_progress|manual_action_required|done|failed; use "done" immediately for `gitignore` once `.plans/` is gitignored
plan_dir = "{cf-studio-path}/.plans/{task-slug}"
active_plan_dir = "{cf-studio-path}/.plans/{task-slug}" # update if archived
input_dir = "{cf-studio-path}/.plans/{task-slug}/input" # omit or set "" when no raw-input package was created
input_manifest = "{cf-studio-path}/.plans/{task-slug}/input/manifest.json" # omit or set "" when no raw-input package was created
input_signature = "{sha256 of direct prompt + provided file contents}" # omit or set "" when no raw-input package was created
input_chunks = []                      # ordered `input/*.md` files emitted by `chunk-input`
total_phases = {N}

[[phases]]
number = 1
title = "{phase title}"
slug = "{short-slug}"
file = "phase-01-{slug}.md"
brief_file = "brief-01-{slug}.md"  # compilation brief (MUST exist before phase file)
status = "pending"
kind = "delivery"                    # delivery|lifecycle
depends_on = []
input_files = []                    # project files to read at runtime
output_files = ["{target file}"]    # project files this phase creates/modifies
outputs = ["out/phase-01-{what}.md"] # intermediate results for later phases
inputs = []                         # intermediate results from prior phases
template_sections = [1, 2, 3]      # H2 numbers from template.md (generate tasks)
checklist_sections = []             # H2 numbers from checklist.md (analyze tasks)
```
`plan.execution_status` tracks aggregate phase execution independently from plan-file handling. `plan.lifecycle_status` tracks whether plan storage actions are still pending, in progress, complete, or awaiting manual resolution.

Reset CF_PHASE_GATE=armed immediately after the write completes or fails.

Any later mutation of `plan.toml` in this phase (for example setting
`execution_status` to `briefs_only` or `prompts_emitted`) MUST reopen
`CF_PHASE_GATE=released_for_orchestrator_write` with scope =
`{cf-studio-path}/.plans/{task-slug}/plan.toml` for that update and reset
the gate to `armed` immediately after the update completes or fails.

## 3.2 Generate Compilation Briefs (from Template)

Set CF_PHASE_GATE=released_for_orchestrator_write with scope = {cf-studio-path}/.plans/{task-slug}/brief-*.md before writing the brief-*.md file(s).

For each phase, generate a compilation brief (`~50-80` lines). ALWAYS open and follow `{cf-studio-path}/.core/requirements/brief-template.md`. Estimate kit file sizes with `wc -l`, list examples with `ls`, fill the brief from `plan.toml`, and write `{cf-studio-path}/.plans/{task-slug}/brief-{NN}-{slug}.md`. A brief contains the context boundary, phase metadata, load instructions, phase file structure, and context budget — never copied kit content or the phase file itself.

When `plan.input_chunks` is non-empty, each brief MUST include the specific `input/*.md` chunk files assigned to that phase in both `input_files` metadata and Load Instructions, with runtime-read steps for every listed chunk.

Reset CF_PHASE_GATE=armed immediately after the write completes or fails.

## 3.2A Stop After Briefs & Ask For Next Step

Once `plan.toml` and every `brief-*` file exist on disk, stop immediately and report:
```text
Brief package prepared: {cf-studio-path}/.plans/{task-slug}/
  Manifest: plan.toml
  Briefs: {N}
  Compiled phase files: 0/{N}

What would you like to do next?

The manifest and briefs are ready on disk. Choose how to produce the phase files:

  [1] Generate phase files here — compile phases in the current chat from the briefs
  [2] Generate phase-compilation prompts — emit one self-contained prompt per brief for downstream chats
  [3] Run phase-compiler subagents — invoke `cf-phase-compiler` for each brief
  [4] Stop here — keep the manifest and briefs without compiling phase files yet
Reply with `1`, `2`, `3`, or `4`.
[1] Suggested when you want to keep working in this chat and compile phase files now.
[2] Emit downstream prompts instead of compiling phase files here.
[3] Use dedicated phase-compiler subagents for compilation.
[4] Stop after the brief package and resume later.
```
Wait for user choice before entering Phase 3.3. Do not emit `Plan created` at this checkpoint.

If the user chooses option `[4]`, reopen the plan-manifest write gate, set
`plan.execution_status = "briefs_only"` in `plan.toml`, reset the gate, then
stop. A plan with `execution_status = "briefs_only"` and existing `brief-*`
files on disk is valid and does NOT require re-planning. Recovery instruction:
in a new chat, read `plan.toml`, confirm `execution_status = "briefs_only"`,
and present the same `[1]–[4]` menu to continue from the saved brief package.

## 3.3 Produce Phase Files Or Phase-Generation Prompts

Phase 3.3 runs only after the user chooses one of the post-brief paths.

For each phase, apply:
```text
--- CONTEXT BOUNDARY ---
Disregard previous workflow context except plan.toml metadata and recorded user decisions. The brief below is self-contained.
Read ONLY the files listed in the brief. Follow its instructions exactly.
---
```
Then:
1. Read the brief **FROM DISK** at `{cf-studio-path}/.plans/{task-slug}/{brief_file}`. If it is not on disk, go back to 3.2. Using a brief that was not read from disk is INVALID.
2. If the user chose option `[1]`, set CF_PHASE_GATE=released_for_orchestrator_write with scope = {cf-studio-path}/.plans/{task-slug}/phase-*.md before writing the phase-*.md file(s). Compile exactly one `phase-*` file in the current chat from that brief, validate it against the brief, report `Phase {N} compiled inline → {filename} ({lines} lines)`, and continue. Reset CF_PHASE_GATE=armed immediately after the write completes or fails.
3. If the user chose option `[2]`, emit exactly one self-contained downstream prompt for that brief. The prompt MUST instruct the downstream worker to read the brief from disk, apply the context boundary, and compile exactly one phase file. Report `Phase {N} prompt prepared → {brief_file}` and continue. Do not write `phase-*` files in this mode. After all downstream prompts have been emitted (one per brief), reopen the plan-manifest write gate, set `plan.execution_status = 'prompts_emitted'`, then reset the gate. The prompts are the deliverable for option `[2]`.
4. If the user chose option `[3]`, the following preconditions MUST be met before setting the gate: the Session Sub-Agent Approval Gate (SKILL.md) MUST be resolved before this option runs. Open, load, and follow `workflows/shared/inline-fallback-probe.md` first. If `INLINE_FALLBACK=true` is the result, option `[3]` is unavailable for this run — route the user to option `[1]` (orchestrator-side compile) or option `[2]` (downstream prompts). If the user explicitly insists on option `[3]` while `INLINE_FALLBACK=true`, do not pretend native sub-agent execution is happening; either re-run option `[1]` under `released_for_orchestrator_write` or stop and ask for `[1]`/`[2]`. Once the gate is confirmed resolved and `INLINE_FALLBACK=false`, set `CF_PHASE_GATE=released_for_dispatch` immediately before routing compilation to `{cf-studio-path}/.core/skills/studio/agents/cf-phase-compiler.md`. The dispatch payload MUST include `git_commit_mode=GIT_COMMIT_MODE`, `contributing_guide=CONTRIBUTING_GUIDE`, and the matching `git_constraint` block from `workflows/generate/phase-4-write.md` § Git constraint blocks. Accept the result only if it reports a successful compile summary with phase identity, output file path, and compile-time validation outcome. Report `Phase {N} compiled via subagent → {filename} ({lines} lines)` and continue. Reset `CF_PHASE_GATE=armed` immediately after the subagent returns — success, error, or no-response.

The planner remains responsible for decomposition, manifest creation, and brief generation. Phase-file production may happen inline, via downstream prompts, or through the dedicated phase compiler subagent depending on the user's post-brief choice.

## 3.4 Validate Phase Files

Run Phase 3.4 only if option `[1]` or `[3]` generated phase files in this run.

After all phases are compiled:
1. Every `brief_file` exists on disk.
2. Each phase file matches its brief's load instructions.
3. Unresolved `{...}` variables outside code fences = zero.
4. Phase file size `≤ 1000` lines; otherwise split.
5. Rules completeness: every applicable `MUST` / `MUST NOT` from `rules.md` is present; if adding missing rules breaks budget, re-split — NEVER drop rules.
6. Context budget `phase_file_lines + input_files + inputs + output_lines ≤ 2000`; otherwise split.
7. After the final phase, the union of all Rules sections must cover `100%` of applicable rules.
