---
description: Invoke at storytelling workflow phase E5 (export-emit) to write the finalized export package to disk under {cf-studio-path}/.cache/explain/packages/<slug>-<timestamp>/. WRITE-CAPABLE — creates index.md, per-portion files, navigation.mmd, and mode-specific extras. Refuses export for mode=socratic.
---

<!-- toc -->

- [Authority boundary](#authority-boundary)
- [Write authority boundary](#write-authority-boundary)
- [Frozen Input Payload](#frozen-input-payload)
- [Methodology](#methodology)
  - [Step 1 — Compute package_dir and guard socratic mode](#step-1--compute-package_dir-and-guard-socratic-mode)
  - [Step 2 — Create package directory](#step-2--create-package-directory)
  - [Step 3 — Write index.md](#step-3--write-indexmd)
  - [Step 4 — Write per-portion files](#step-4--write-per-portion-files)
  - [Step 5 — Write navigation.mmd](#step-5--write-navigationmmd)
  - [Step 6 — Mode-specific extras](#step-6--mode-specific-extras)
  - [Step 7 — Format handling](#step-7--format-handling)
  - [Step 8 — Build manifest](#step-8--build-manifest)
- [Output Contract](#output-contract)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

## Dispatch Generator Contract

This file is a controller-side prompt generator source, not a runtime prompt for the dispatched sub-agent.

The controller MUST use this file to synthesize the final dispatch prompt for
the agent. The final prompt MUST include the task statement, frozen input
payload, task-relevant instruction assets resolved from `SHARED_CONTEXT_PACK`,
allowed resource context, output contract, completion gate, and the explicit
rule that the dispatched sub-agent executes only that final prompt.

The dispatched sub-agent MUST NOT open prompt assets from disk and MUST NOT
rediscover workflows, requirements, specs, AGENTS, SKILL, or kit prompt files.


## Write authority boundary

```text
UNIT WriteAuthorityBoundary

PURPOSE:
  Enforce the path prefix constraint for all file writes.

INVARIANTS:
  - MUST write files only under:
      `{cf-studio-path}/.cache/explain/packages/<slug>-<timestamp>/`
  - MUST normalize the computed path (resolve any `..` segments) and verify
    the result is strictly prefixed by `{cf-studio-path}/.cache/explain/packages/`

ON_ERROR:
  path_escapes_prefix ->
    append "path_traversal_blocked: computed package_dir escaped write prefix" to errors[]
    SET files_written = []
    RETURN output immediately; do NOT write any file
```

## Frozen Input Payload

```json
{
  "slug": "string — derived from canonical_path basename + mode",
  "timestamp": "string — ISO compact e.g. 20260523T141500Z",
  "cf_studio_path": "string",
  "export_format": "markdown | html | pdf | all",
  "mode": "string",
  "audience": "string",
  "e2_segments": [
    {
      "plan_item_index": "number",
      "title": "string",
      "narrative_text": "string",
      "source_refs": ["string"]
    }
  ],
  "wrap": {
    "header": "string",
    "session": "object — session block from wrap output",
    "key_takeaways": "array",
    "open_questions": "array",
    "save_prompt_default_path": "string",
    "glossary": "array | null",
    "bookmarks_export_prompt": "boolean",
    "next_steps": "array"
  },
  "handle": {
    "canonical_path": "string",
    "session_id": "string",
    "target_type": "string",
    "primary_language": "string | null"
  },
  "navigation_mermaid_source": "string — Mermaid diagram source built by orchestrator from plan + nav transitions",
  "project_root": "string — absolute path to project root, used to compute manifest.source_path as relative-from-project-root from handle.canonical_path"
}
```

```text
UNIT InputConstraints

RULES:
  - MUST treat all fields as required
  - MUST treat `e2_segments` as non-empty
  - MUST default `export_format` to "markdown" when omitted
```

## Methodology

```text
UNIT ExportMethodology

PURPOSE:
  Execute the eight steps in order to produce the export package.

DO:
  CONTINUE Step1_ComputeAndGuard
  CONTINUE Step2_CreateDirectory
  CONTINUE Step3_WriteIndex
  CONTINUE Step4_WritePortions
  CONTINUE Step5_WriteNavigation
  CONTINUE Step6_ModeExtras
  CONTINUE Step7_FormatHandling
  CONTINUE Step8_BuildManifest
```

### Step 1 — Compute package_dir and guard socratic mode

```text
UNIT Step1_ComputeAndGuard

DO:
  1. Compute `package_dir`:
       {cf-studio-path}/.cache/explain/packages/{slug}-{timestamp}/
     Normalize the path (resolve any `..` segments).
     Verify result is strictly prefixed by `{cf-studio-path}/.cache/explain/packages/`.

ON_ERROR:
  path_escapes_prefix ->
    append "path_traversal_blocked: computed package_dir escaped write prefix" to errors[]
    SET files_written = []
    RETURN output immediately

WHEN:
  mode == "socratic"
DO:
  RETURN immediately:
    {
      "package_path": null,
      "files_written": [],
      "manifest": null,
      "errors": ["Export is not supported for mode=socratic. Socratic sessions are interactive and produce no exportable artifact."]
    }

RULES:
  - MUST use the exact error message above for mode=socratic (AP-#34); do not alter the wording
  - MUST_NOT write any files when mode=socratic
```

### Step 2 — Create package directory

```text
UNIT Step2_CreateDirectory

DO:
  Create `package_dir` with mkdir -p semantics (create all intermediate directories as needed).

ON_ERROR:
  directory_creation_failed ->
    record the OS error in errors[]
    STOP
```

### Step 3 — Write index.md

```text
UNIT Step3_WriteIndex

PURPOSE:
  Write {package_dir}/index.md with all required sections in order.

DO:
  Write `{package_dir}/index.md` containing, in order:
    1. YAML front-matter: keys slug, timestamp, mode, audience, format,
       source (relative-from-project-root path from handle.canonical_path —
       strip the cf_studio_path's project-root prefix).
    2. H1: `# {wrap.header}` verbatim.
    3. Session block: markdown table or definition list with fields:
         role, audience, input (relative path), progress, diagrams,
         open_questions_count, bookmarks_count, glossary_count.
    4. H2 `## Key Takeaways`: bullet per wrap.key_takeaways entry as
         `- {text} ({source_ref})`.
    5. H2 `## Open Questions`: present only if wrap.open_questions is non-empty;
         each entry as `- [{id}] {text}`.
    6. H2 `## Glossary`: present only if wrap.glossary is non-null;
         each entry as `- **{term}**: {definition}`.
    7. H2 `## Portions`: numbered list linking to each portion file:
         `1. [portion-<n>-<slug>.md](portion-<n>-<slug>.md)` (n = 1-based).
    8. H2 `## Navigation`: fenced `mermaid` block containing navigation_mermaid_source.
    9. Footer line:
         > Paths in this package are relative to the project root. Do not move files
         > outside this package directory without updating cross-references.
   10. H2 `## Next Steps`: bullet list of wrap.next_steps.

RULES:
  - MUST use only relative paths inside index.md (AP-#28e); no absolute paths
```

### Step 4 — Write per-portion files

```text
UNIT Step4_WritePortions

PURPOSE:
  Write one file per e2_segments entry.

DO:
  FOR each entry in e2_segments (0-based index i):
    1. portion_filename = "portion-{i+1}-{slug}.md"
    2. portion_path = "{package_dir}/{portion_filename}"
    3. Write file containing:
         - H1: `# {segment.title}`
         - Mode-lens label: `> Mode: {mode} | Audience: {audience}`
         - Body: segment.narrative_text verbatim (do NOT reformat or truncate)
         - H2 `## Sources`: present only if segment.source_refs is non-empty;
             each ref as `- [source]({ref})` when ref is a URL, or `- {ref}` when plain path/label
         - Footer nav:
             `[Back to index](index.md)`
             when i > 0: `[Previous](portion-{i}-{slug}.md)`
             when i < len(e2_segments)-1: `[Next](portion-{i+2}-{slug}.md)`

RULES:
  - MUST use only relative paths in footer nav (AP-#28e); no absolute paths
SEE_ALSO: Step3_WriteIndex
```

### Step 5 — Write navigation.mmd

```text
UNIT Step5_WriteNavigation

DO:
  Write `{package_dir}/navigation.mmd` with navigation_mermaid_source as the file body verbatim.

RULES:
  - MUST_NOT add a fenced code block wrapper — write the raw Mermaid source directly
```

### Step 6 — Mode-specific extras

```text
UNIT Step6_ModeExtras

PURPOSE:
  Emit the mode-specific extra file when applicable.

MENU ModeExtrasDispatch:
  mode == "review" ->
    Write `comments.md`:
      H1 `# Review Comments`
      FOR each e2_segment: H2 with segment title, then any inline review comments
        extracted from narrative_text (lines beginning with `> **Comment:**` or `> **Note:**`);
        if no such lines exist, emit `_No inline comments found._`

  mode == "onboarding" ->
    Write `next-steps-checklist.md`:
      H1 `# Onboarding Next Steps`
      GFM task list `- [ ]` derived from wrap.next_steps
      H2 `## Open Questions` listing wrap.open_questions

  mode == "decision" ->
    Write `decision-record.md`:
      H1 `# Decision Record`
      Session metadata block
      H2 `## Decision Summary` with wrap.key_takeaways as bullets
      H2 `## Options Considered` placeholder section
      H2 `## Outcome` placeholder section

  otherwise ->
    No extra file is written; do NOT write a placeholder file for unmatched modes
```

### Step 7 — Format handling

```text
UNIT Step7_FormatHandling

PURPOSE:
  Apply format conversions after all .md files are written.

MENU FormatDispatch:
  export_format == "markdown" ->
    No additional action.

  export_format == "html" ->
    FOR each .md file written in Steps 3-6:
      Emit sibling .html file with same basename containing:
        <!-- Generated by cf storytelling-export. Requires pandoc or
             equivalent md->html conversion. Run: pandoc -o <file>.html <file>.md -->
        <p><em>HTML rendering requires pandoc. See README for conversion instructions.</em></p>
      Record each .html file in files_written.

  export_format == "pdf" ->
    Same as html stub approach with extension `.pdf.stub` and comment adjusted
    to reference a PDF renderer. Record each .pdf.stub in files_written.

  export_format == "all" ->
    Apply html AND pdf steps above.
```

### Step 8 — Build manifest

```text
UNIT Step8_BuildManifest

PURPOSE:
  Assemble the output manifest after all writes succeed.

DO:
  SET package_path = absolute path to package_dir
  SET files_written = sorted list of all file basenames written (basenames only, relative to package_dir)
  SET manifest.slug = input slug
  SET manifest.timestamp = input timestamp
  SET manifest.format = input export_format
  SET manifest.mode = input mode
  SET manifest.audience = input audience
  SET manifest.source_path = relpath(handle.canonical_path, project_root)
    — strip project_root absolute prefix to produce relative-from-project-root value (AP-#28e)
  SET manifest.byte_sizes = dict mapping each written basename to its byte size in bytes
    — compute as len(content.encode("utf-8")) at write-time; Bash stat is acceptable fallback
  SET manifest.file_count = len(files_written)
  SET errors = list of non-fatal warnings (e.g. "html requires pandoc — stubs written")

ON_ERROR:
  canonical_path_outside_project_root ->
    SET manifest.source_path = handle.canonical_path verbatim
    append "source_path: canonical_path lies outside project_root — using verbatim path" to errors[]
```

## Output Contract

```json
{
  "package_path": "string — absolute path to package directory",
  "files_written": ["string — basenames relative to package_dir"],
  "manifest": {
    "slug": "string",
    "timestamp": "string",
    "format": "string",
    "mode": "string",
    "audience": "string",
    "source_path": "string — relative-from-project-root",
    "byte_sizes": {"<filename>": "number"},
    "file_count": "number"
  },
  "errors": ["string"]
}
```

```text
NOTES:
  For mode=socratic, package_path and manifest are null, files_written is [],
  and errors contains the required refusal message (AP-#34).

  The JSON block is the entire response — no preamble, no trailing commentary.
```

## Response Completion Gate

```text
UNIT ResponseCompletionGate

RULES:
  - MUST return the JSON shape above as the entire output (no chat, no preamble, no markdown wrapping outside the JSON block)
  - MUST return package_path=null, manifest=null, files_written=[], and errors[0] containing the exact AP-#34 refusal message when mode=socratic
  - MUST return package_path as an absolute path strictly prefixed by `{cf-studio-path}/.cache/explain/packages/` when mode != "socratic"
  - MUST list at minimum index.md, navigation.mmd, and one portion-*-*.md in files_written (when not socratic and no fatal error)
  - MUST use basenames only (no path separators) in files_written
  - MUST use a relative value (no /Users/, /Volumes/, /home/ prefix) for manifest.source_path
  - MUST include the mode-specific extra file in files_written when applicable
  - MUST ensure manifest.file_count equals len(files_written)
  - MUST ensure manifest.byte_sizes has one entry per file in files_written
  - MUST satisfy the SKILL.md invariant
SEE_ALSO: WriteAuthorityBoundary
SEE_ALSO: Step3_WriteIndex
```
