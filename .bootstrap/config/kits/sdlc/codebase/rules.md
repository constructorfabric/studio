# CODEBASE Rules

**Artifact**: CODEBASE
**Kit**: sdlc

**Dependencies** (lazy-loaded): `{codebase_checklist}` (kit-specific semantic alignment), `{cf-studio-path}/.core/requirements/code-checklist.md` (generic code quality).

---

```pdsl
UNIT CodebaseImplementation

PURPOSE:
  Implement code from a resolved design source, in work packages, under the
  correct traceability mode.

STATE:
  - SET TRACEABILITY_MODE: FULL | DOCS-ONLY
    default: DOCS-ONLY

DO:
  - RUN resolve source in priority order:
      1 FEATURE design (registered, has `to_code="true"` IDs) -> FULL possible
      2 Other Constructor Studio artifact (PRD / DESIGN / ADR / DECOMPOSITION) -> DOCS-ONLY
      3 User-provided description / requirements -> DOCS-ONLY
      4 Prompt only -> DOCS-ONLY
  - REQUIRE if no source -> suggest `/cf-studio-generate FEATURE` first
  - LOAD project `AGENTS.md` for code conventions
  - LOAD the FEATURE artifact being implemented (flows, algorithms, states, definition-of-done tasks)
  - LOAD the system DESIGN artifact if registered in `artifacts.toml` (architecture, components, principles, constraints)
  - SET TRACEABILITY_MODE: FULL when FEATURE source with `to_code="true"` IDs; else DOCS-ONLY
  - RUN per work package:
      1 identify exact design items to code (flows / algos / states / requirements / tests)
      2 implement per project conventions
      3 WHEN Mode FULL: add `@cpt-begin`/`@cpt-end` markers per CDSL instruction (see CodebaseMarkers)
      4 run work-package validation (tests, build, linters per project config)
      5 WHEN Mode FULL: sync FEATURE / DECOMPOSITION checkboxes (see CodebaseCascade)
      6 continue to next work package
  - CONTINUE CodebaseValidate

RULES:
  - ALWAYS apply TDD (failing test first, minimal code, then refactor), SOLID, DRY, KISS, YAGNI, explicit error handling, and testability
  - ALWAYS refactor only after tests pass; keep behavior unchanged
  - ALWAYS load `{cf-studio-path}/.core/requirements/code-checklist.md` for the full generic code-quality criteria; do not restate them here

NOTES:
  Mode FULL requires the traceability spec `{cf-studio-path}/.core/architecture/specs/traceability.md`.
  Mode determination also follows `{codebase_checklist}` Traceability Preconditions.
```

```pdsl
UNIT CodebaseMarkers

PURPOSE:
  Define @cpt marker syntax and granularity (Traceability Mode FULL only).

WHEN:
  - REQUIRE TRACEABILITY_MODE == FULL

DO:
  - EMIT scope markers: `@cpt-{kind}:{cpt-id}:p{N}` — single-line, at function/class entry point (kind: flow | algo | state | dod)
  - EMIT paired block markers: `@cpt-begin:{cpt-id}:p{N}:inst-{local}` / `@cpt-end:{cpt-id}:p{N}:inst-{local}`

RULES:
  - ALWAYS wrap the SMALLEST code fragment implementing one CDSL instruction in each begin/end pair
  - ALWAYS place a separate begin/end pair per instruction when a function implements multiple instructions
  - ALWAYS place markers as close to the implementing code as possible
  - ALWAYS ensure every `to_code="true"` ID has markers and every implemented CDSL instruction (`[x] ... inst-*`) has a paired begin/end block wrapping non-empty code
  - NEVER wrap a whole multi-instruction function body in a single begin/end pair (loses per-instruction traceability)
  - NEVER leave orphaned or stale markers
```

Correct — each instruction wrapped individually:

```python
# @cpt-algo:cpt-system-algo-process:p1
def process_data(items):
    # @cpt-begin:cpt-system-algo-process:p1:inst-validate
    if not items:
        raise ValueError("Empty input")
    # @cpt-end:cpt-system-algo-process:p1:inst-validate

    # @cpt-begin:cpt-system-algo-process:p1:inst-transform
    result = [transform(item) for item in items]
    # @cpt-end:cpt-system-algo-process:p1:inst-transform

    # @cpt-begin:cpt-system-algo-process:p1:inst-return-result
    return result
    # @cpt-end:cpt-system-algo-process:p1:inst-return-result
```

Anti-pattern: a single `@cpt-begin/.../@cpt-end` pair wrapping the entire multi-instruction function body.

```pdsl
UNIT CodebaseCascade

PURPOSE:
  Cascade code markers up through FEATURE / DECOMPOSITION / PRD-DESIGN checkboxes, consistently and versioned.

WHEN:
  - REQUIRE TRACEABILITY_MODE == FULL

DO:
  - RUN cascade chain:
      CODE markers exist
        -> FEATURE: flow/algo/state/dod IDs [x] (dod also requires evidence complete)
        -> DECOMPOSITION: feature entry [x]
        -> PRD/DESIGN: referenced IDs [x] when ALL downstream refs [x]
  - RUN update order:
      1 after implementing a CDSL instruction: add block markers, mark step [x] in FEATURE
      2 after all steps of a flow/algo/state/dod [x]: mark that ID [x] in FEATURE
      3 after all FEATURE IDs [x]: mark feature entry [x] in DECOMPOSITION; status `⏳ PLANNED` -> `🔄 IN_PROGRESS` -> `✅ IMPLEMENTED`
      4 after DECOMPOSITION updated: mark referenced IDs [x] in PRD/DESIGN when all downstream refs [x]
  - RUN marker versioning on design ID bump:
      WHEN design ID versioned (`-v2`) -> update markers to `@cpt-flow:{cpt-id}-v2:p{N}`; migrate ALL markers; old markers may stay commented during transition

RULES:
  - NEVER mark a CDSL instruction [x] unless code block markers exist and wrap non-empty implementation code
  - NEVER add a code block marker pair unless the CDSL instruction exists in design (add it first if missing)
  - ALWAYS keep a parent ID checkbox consistent with all nested task-tracked items in its scope (heading boundaries): parent [x] IFF all nested task-tracked items [x]
  - NEVER mark a reference [x] while its definition is still [ ]

NOTES:
  `cfs validate` warns if a code marker exists but the FEATURE checkbox is [ ],
  warns if a FEATURE checkbox is [x] but the code marker is missing,
  and reports coverage: N% of FEATURE IDs have code markers.
```

```pdsl
UNIT CodebaseValidate

PURPOSE:
  Deterministic gates, then one delegated semantic review; decide PASS/FAIL.

DO:
  - REQUIRE no placeholder/stub code (no TODO / FIXME / XXX / HACK / unimplemented! / todo! in business logic; no bare unwrap()/panic in production)
  - RUN `cfs validate` (Mode FULL): valid marker format, all begin/end pairs matched, no empty blocks, all `to_code="true"` IDs have markers, no orphaned/stale markers, design checkboxes synced, coverage %
  - REQUIRE test scenarios exist and are traceable: a test file per design scenario, scenario ID in a comment, not ignored without justification, actually validates behavior
  - RUN build -> REQUIRE succeeds, no compilation errors
  - RUN lint -> REQUIRE passes, no linter errors
  - RUN tests -> REQUIRE unit + integration + e2e (if applicable) pass AND coverage meets project requirements
  - RUN semantic expert review per `{codebase_checklist}` (SEM-CODE-001..007) + `{cf-studio-path}/.core/requirements/code-checklist.md` (generic quality + design-to-code logic consistency)
  - RETURN PASS only if: build/lint/tests pass; coverage met; no CRITICAL design divergences; AND (Mode FULL) required markers present and properly paired

RULES:
  - ALWAYS delegate generic code-quality criteria to `{cf-studio-path}/.core/requirements/code-checklist.md`
  - ALWAYS delegate semantic alignment and logic-consistency checks to `{codebase_checklist}`
  - NEVER restate the generic or semantic checklists inline

NOTES:
  Report shape: Build PASS/FAIL, Lint PASS/FAIL, Tests X/Y, Coverage N%,
  Checklist PASS/FAIL (issues), Logic Consistency PASS/FAIL (CRITICAL/MINOR divergences).
```

```pdsl
UNIT CodebaseNextSteps

PURPOSE:
  Offer next actions after validation.

DO:
  - EMIT_MENU NextStepsMenu

MENU NextStepsMenu:
  TITLE: CODE — next steps
  OPTIONS:
    1 after success / feature complete -> update feature status to IMPLEMENTED in DECOMPOSITION
    2 after success / all features done -> `/cf-studio-analyze DESIGN` (validate overall design completion)
    3 after success / new feature needed -> `/cf-studio-generate FEATURE`
    4 after success / expert review only -> `/cf-studio-analyze semantic`
    5 after issues / design mismatch -> `/cf-studio-generate FEATURE` (update feature design)
    6 after issues / missing tests or quality -> continue `/cf-studio-generate CODE`
    7 no design / new feature -> `/cf-studio-generate FEATURE` first
    8 no design / from PRD -> `/cf-studio-generate DESIGN` then DECOMPOSITION
    9 no design / quick prototype -> proceed without traceability, suggest FEATURE later
  INVALID:
    EMIT "Choose a listed option."
    WAIT user.reply
    STOP_TURN
```
