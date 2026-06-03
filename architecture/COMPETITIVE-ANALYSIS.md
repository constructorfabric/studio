# Competitive Analysis — Constructor Studio

**Methodology**: Two-pass cf-analyze with parallel freeform reviewers.
- **Pass 1** (Rf-001–021): README.md, DESIGN.md, PRD.md, DECOMPOSITION.md
- **Pass 2** (Rf-022–037): all `workflows/` files + guides/PROJECT-EXTENSIBILITY.md
- **Research base**: 14 competitors identified across 3 tiers via web research

**Overall verdict**: Constructor Studio is the **most comprehensive workflow-level SDLC
system among open-source alternatives** with 8 capabilities that are genuinely unique in
the market. The primary gaps are autonomous execution (Planu/cc-sdd/LAO), retroactive
healing (Planu), and compliance gates (claude-code-sdlc). The most critical problem is
positioning: none of the unique capabilities are explained comparatively anywhere in the
documentation.

---

## Competitive Landscape

### Tier 1 — Direct AI-assisted SDLC workflow competitors

| Tool | Operating model | Host support | Pricing |
|------|----------------|-------------|---------|
| **Kiro** (Amazon) | Spec-driven IDE: requirements.md + design.md + tasks.md + steering files + hooks + Powers | Cloud IDE only | Proprietary |
| **Planu** | 14 MCP tools, unified spec.md, 8-phase lifecycle, retroactive healing, multi-agent swarm | Multi-host (auto-detect) | Commercial |
| **cc-sdd** (gotalab) | 17 skills, /kiro-discovery, /kiro-impl TDD loop, long-running autonomous impl | 8 agents | MIT |
| **devflo** | PM/Architect/Dev/QA agents, OpenSpec lifecycle, git state persistence | Claude Code + Cursor | Open |
| **LAO** | 10 SDLC role-agents, preview-then-execute, cross-role gates | Claude Code + Cursor | Open |
| **claude-code-sdlc** | 10-phase SDLC, company profiles, compliance gates (SOC2/HIPAA/GDPR) | Claude Code | Open |
| **autonomous-sdlc** | 40+ agents, 11 phases (discovery→monitoring), 9+ IDE support | Multi-IDE | Open |

### Tier 2 — Execution platforms (indirect competitors)

Claude Code, Cursor, GitHub Copilot, Windsurf, Devin — provide the execution substrate
but not the SDLC workflow layer. Constructor Studio targets this layer.

### Tier 3 — Visual builders (different paradigm)

OrchStack, Nagent — visual canvas builders; not direct competitors.

---

## Full Competitive Feature Matrix

### Core platform dimensions

| Dimension | Constructor Studio | Planu | Kiro | cc-sdd | LAO | claude-code-sdlc |
|-----------|:-----------------:|:-----:|:----:|:------:|:---:|:---------------:|
| **Artifact model** | ✅ PRD+DESIGN+ADR+DECOMP+FEATURE (kit) | ✅ unified spec.md | ✅ req+design+tasks | ⚠️ brief.md+tasks | ⚠️ ticket-driven | ✅ PRD+DESIGN+ADR |
| **Stable IDs + code tags** | ✅ CPT-IDs, @cpt-* markers, versioning (-vN) | ⚠️ spec-embedded, no code tags | ⚠️ task-scoped | ⚠️ per-task | ⚠️ ticket | ✅ @rules chain |
| **Deterministic validation** | ✅ cfs validate, stdlib Python, ≤3s, CI-ready | ⚠️ LLM-driven MCP | ❌ | ⚠️ TDD-based | ⚠️ LLM gates | ✅ hard gates |
| **Multi-host agent gen** | ✅ Windsurf+Cursor+Claude+Copilot+Codex | ✅ auto-detect | ❌ IDE-bound | ✅ 8 agents | ✅ | ⚠️ Claude-centric |
| **GitHub kit system** | ✅ file-diff update, manifest, resource binding | ✅ 557 tools/skills | ⚠️ Powers (cloud) | ⚠️ overlay files | ⚠️ hardcoded | ✅ YAML profiles |
| **Execution plan compilation** | ✅ phase decomp, ≤500/≤1000-line budget, self-contained | ⚠️ fixed 8-phase | ❌ | ⚠️ per-task TDD | ⚠️ 11 phases | ⚠️ 6-gate |
| **Multi-repo workspace** | ✅ cross-repo trace, Git URL sources, per-source adapter | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Dependency map** | ✅ cfs map, HTML/JSON, phantom IDs, federation-aware | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Behavioral spec DSL** | ✅ CDSL (actor-centric, non-programmer readable) | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Offline / local-first** | ✅ stdlib Python, no cloud | ✅ | ❌ cloud IDE | ✅ | ✅ | ✅ |
| **Open source** | ✅ Apache 2.0 | ❌ commercial | ❌ proprietary | ✅ MIT | ✅ | ✅ |

### Workflow-level dimensions (new in v2)

| Dimension | Constructor Studio | Planu | Kiro | cc-sdd | LAO | Status |
|-----------|:-----------------:|:-----:|:----:|:------:|:---:|:------:|
| **Brainstorm-within-generate** (Phase 0.7) | ✅ multi-round expert panel (3-6 personas, topic+challenge rounds, user-driven) | ❌ clarify_requirements only | ❌ | ❌ | ❌ | **UNIQUE** |
| **Explore workflow** (standalone + save + route) | ✅ save-to-disk bundle, refine loop, 6-action routing | ⚠️ MCP tool only | ❌ | ⚠️ /kiro-discovery | ❌ | **ADVANTAGE** |
| **Explain + storytelling export** (6 modes) | ✅ session-based, checkpointing, package export to disk | ❌ | ❌ | ❌ | ❌ | **UNIQUE** |
| **PDSL prompt engineering workflow** | ✅ 3 modes (new/transform/review), 3 subagents, deterministic validate | ❌ | ❌ | ❌ | ❌ | **UNIQUE** |
| **4-layer manifest + cross-agent translation** | ✅ core→kit→orchestrator→repo, includes directive, 5-host translation | ❌ | ⚠️ Powers (cloud) | ⚠️ overlay only | ❌ | **UNIQUE** |
| **Generate built-in review loop** (Phase 5) | ✅ det gate + semantic review + approval + remediation | ⚠️ MCP validate after | ❌ | ❌ | ⚠️ role gates | **ADVANTAGE** |
| **Author-plan subagent** (Phase 1.5) | ✅ cf-planner before writing, memory/disk/inline storage | ❌ | ❌ | ⚠️ /kiro-impl phases | ❌ | **ADVANTAGE** |
| **Brownfield auto-config gate** | ✅ task-matched rule detection, generates rules/AGENTS.md/artifacts.toml | ⚠️ | ⚠️ generates docs | ❌ | ❌ | **ADVANTAGE** |
| **Plan compilation (self-contained files)** | ✅ inlined rules, resolved vars, binary acceptance, ≤500 line target | ❌ | ❌ | ❌ | ⚠️ no line budget | **UNIQUE** |
| **Map config-assist** | ✅ guided md-map.toml generation with palette selection | ❌ | ❌ | ❌ | ❌ | **UNIQUE** |
| **Brainstorm orchestration modes** | ✅ single-agent vs. fan-out, env var config | ❌ | ❌ | ❌ | ❌ | **UNIQUE** |
| **Git commit mode** | ✅ optional GIT_COMMIT_MODE after artifact creation | ⚠️ | ❌ | ❌ | ❌ | **PARITY** |
| **Autonomous execution** | ❌ interactive only | ✅ autopilot | ⚠️ partial | ✅ /kiro-impl | ✅ cross-role | **GAP** |
| **Retroactive healing / drift detection** | ❌ read-only | ✅ post-merge healing | ❌ | ❌ | ❌ | **GAP** |
| **Compliance gates** | ❌ excluded by design | ❌ | ❌ | ❌ | ❌ | ✅ SOC2/HIPAA/GDPR | **GAP** |
| **Preview-then-execute** | ❌ | ❌ | ❌ | ❌ | ✅ simulate first | **GAP** |

---

## Capabilities Unique to Constructor Studio

The following 8 capabilities have no direct equivalent in any identified competitor:

1. **Brainstorm-within-generate** — multi-round expert panel (3-6 personas, topic+challenge
   rounds, user-editable panel composition, cf-explorer context loaded for experts) embedded
   as Phase 0.7 of the artifact generation workflow. Also available standalone as
   `cf brainstorm:`.

2. **PDSL prompt engineering workflow** — dedicated `cf pdsl:` with 3 modes (new/transform/
   review), 3 subagents (cf-pdsl-author, cf-pdsl-transformer, cf-pdsl-reviewer), and
   deterministic `cfs pdsl validate` as pre-flight and post-flight gate.

3. **4-layer manifest hierarchy with cross-agent translation** — core → kit → orchestrator →
   repo resolution with `includes` directive for component packages; `cfs generate-agents`
   translates to all 5 host formats simultaneously (Claude Code, Cursor, Windsurf, Copilot,
   Codex).

4. **Plan compilation with self-contained phase files** — plan.md Phase 3 inlines all rules,
   resolves all variables, writes binary acceptance criteria per phase, enforces ≤500-line
   target / ≤1000-line max with automatic sub-phase splitting. Phase files are executable by
   any agent without Studio context.

5. **Explain/storytelling with package export** — interactive explain sessions with 6
   pedagogical modes (presentation, review, onboarding, decision, socratic, change-impact),
   session-based checkpointing with resume, and export of full training packages to disk
   under `.cache/explain/packages/{slug}-{ISO}/`.

6. **Multi-repo workspace federation** — cross-repo artifact traceability, Git URL sources,
   per-source adapter context, workspace-init auto-discovery, graceful degradation when
   sources unreachable. No competitor has this.

7. **Dependency map with federation awareness** — `cfs map` with single-repo / with-workspace
   / markdown-only scope modes, phantom-ID detection, config-assist mode (guided md-map.toml
   generation with palette selection), interactive HTML viewer + JSON export.

8. **CDSL behavioral spec language** — actor-centric, non-programmer readable, implementation
   tracking via @cpt-* markers, spec coverage measurement (`cfs spec-coverage`).

---

## Findings

### 🔴 HIGH — Critical gaps and missed differentiators

**Rf-001** · `README.md` entire file · **Positioning Absence**

No mention of competitors, alternative products, or comparative language anywhere in README
or DESIGN. Evaluators have no basis for choosing Constructor Studio over Kiro, Planu,
cc-sdd, or others. Every named competitor either explicitly names alternatives or positions
clearly against a category.

> _Evidence_: The README contains no mention of competitors, alternative products, or
> comparative positioning. It describes Constructor Studio's own model but never states
> "unlike Kiro..." or "compared to Planu..." (Rf-001, README.md)

**Fix**: Add "Competitive positioning" section after "Fit and non-fit" naming 3–5 competitors
with 2–3 differentiators. Alternatively create COMPETITIVE-ANALYSIS.md and link to it.

---

**Rf-002** · `DESIGN.md` lines 34–36 · **Determinism Differentiator Hidden**

> "The architecture maximizes determinism: all validation, scanning, and transformation is
> handled by Python scripts with JSON output; LLMs are reserved only for reasoning tasks
> within agent workflows."

The single strongest differentiator vs. competitors (deterministic, stdlib-only, ≤3s,
CI-ready validation with no LLM calls) is buried in DESIGN.md as an architecture note.
README never mentions deterministic validation as a product capability.

**Fix**: Elevate to README "Product shape" as a first-class bullet with CI angle: "all
structural checks run via Python stdlib with JSON output, enabling CI/CD integration and
offline validation without LLM cost or latency."

---

**Rf-003** · `PRD.md` lines 59–65, `DECOMPOSITION.md` lines 185–203 · **No Retroactive Healing**

Constructor Studio's validator is read-only by design. No post-merge drift correction exists.
Planu's headline differentiator is retroactive healing (post-merge spec drift detection +
auto-correction). Constructor Studio detects drift via `cfs validate` but all remediation is
manual.

**Fix**: Implement P2 `cfs heal --artifact <path>` that runs `cfs validate` and produces
LLM-generated fix suggestions (non-auto-apply, human reviews). Document the read-only
philosophy explicitly as safety-first.

---

**Rf-004** · `PRD.md` lines 59–65, all workflow files · **No Autonomous / Unattended Execution**

All workflows require explicit human approval at multiple interactive gates (Phase 3 summary,
Phase 5 review, Phase 6 handoff). No autonomous execution mode, no background daemon, no
skip-gate option. Planu, cc-sdd (/kiro-impl), and LAO all support background execution.
Ralphex delegation (DECOMPOSITION F14) is planned but in-progress.

**Fix**: Accelerate ralphex delegation to P1. Add `--autonomous` flag that skips interactive
gates and proceeds with defaults. Document "interactive-first" philosophy as deliberate
tradeoff (auditability over automation).

---

**Rf-005** · `PRD.md` lines 658–659 · **No Compliance Gates**

Constructor Studio explicitly excludes regulatory/compliance requirements. claude-code-sdlc
bundles SOC 2, HIPAA, GDPR, PCI-DSS gates. Constructor Studio cannot be used as-is in
regulated industries.

**Fix**: Create `studio-kit-compliance` package with SOC 2/HIPAA/GDPR/PCI-DSS validation
constraints and checklists. Document core Studio as compliance-agnostic; compliance is a
kit concern.

---

**Rf-022** · `workflows/generate/phase-0.7/` entire directory · **Brainstorm-within-generate Not Documented as Differentiator**

> "EMIT proposed panel display containing: header: 'Proposed panel for {KIND}: {name}:' —
> E1..E6 entries: persona name, focus, why rationale — 'Seed topic for round 1:' + seed_topic.text"
> (panel-selection.md lines 45–50)

Constructor Studio embeds a multi-round expert panel (3-6 user-editable personas, topic +
challenge rounds, cf-explorer context loaded before first round, decisions captured in state
for downstream handoff) directly before artifact generation. No competitor has this. But it
is never positioned as a differentiator in README or USAGE-GUIDE.

**Fix**: Add "Brainstorm-before-you-write" section to README "Workflow model". Emphasize:
3-6 user-editable expert panel, multi-round topic/challenge structure, project context loaded
automatically, decisions carried into generation. Available standalone as `cf brainstorm:`.

---

**Rf-023** · `workflows/pdsl.md` lines 1–325 · **PDSL Prompt Engineering Workflow Not Mentioned in Positioning**

> "name: cf-pdsl — description: 'Invoke for requests to author, transform, compress,
> normalize, or review prompt, workflow, skill, or agent instruction files as compact
> state-machine-like PDSL contracts.'" (pdsl.md lines 1–8)

Constructor Studio is the only tool with a dedicated prompt engineering workflow (3 modes:
new/transform/review; 3 specialized subagents; deterministic `cfs pdsl validate` pre- and
post-flight). This is invisible to any reader of the README.

**Fix**: Add "Prompt engineering" section to README. Position as: "Write, transform, and
validate prompt/instruction files with the same structured workflow used for any artifact."
This uniquely positions Constructor Studio for teams managing multiple agent instructions.

---

**Rf-024** · `guides/PROJECT-EXTENSIBILITY.md` lines 80–394 · **4-Layer Manifest Not Visible in Positioning**

> "4-layer manifest hierarchy: 4. Repo Layer → 3. Master Repo Layer → 2. Kit Layer →
> 1. Core Layer. `cfs generate-agents` handles translation: Skill | Claude → Cursor →
> Windsurf → Copilot → Codex" (PROJECT-EXTENSIBILITY.md lines 80–394)

The 4-layer manifest hierarchy (core → kit → orchestrator → repo) with cross-agent
translation to 5 host formats simultaneously is a unique enterprise capability. No competitor
can write once and deploy to all 5 agent tools. This is never mentioned in README.

**Fix**: Add "Orchestrator pattern + cross-agent translation" to README "Core platform and
optional kits" section. Headline claim: "Write skills and agents once; deploy to Claude Code,
Cursor, Windsurf, Copilot, and Codex from a single manifest."

---

**Rf-025** · `workflows/plan.md` lines 106–211 · **Plan Compilation Not Positioned as Differentiator**

> "Enforce context budget: ≤500 lines target, ≤1000 lines maximum per phase file. If a phase
> exceeds the maximum, it MUST be split into sub-phases. [...] compiled prompt containing all
> rules, constraints, conventions, and context inlined — no external file references"
> (plan.md lines 106–211)

Plan compilation (Phase 3: inline all rules, resolve all variables, enforce ≤500/≤1000
line budget per phase, write binary acceptance criteria) produces self-contained phase files
executable by any agent without Studio context. This is unique; no competitor has it.

**Fix**: In README "Workflow model" section, add: "`cf plan:` compiles tasks into self-
contained phase files with all rules inlined and line budgets enforced (≤500 lines), so
any agent can execute them without Studio context. Prevents context overflow on large tasks."

---

### 🟡 MEDIUM — Competitive gaps and underpublicized advantages

**Rf-006** · `README.md` lines 55–79 · **Multi-host Support Underpublicized**

5-host simultaneous generation via `cfs generate-agents` is listed only as a config table
entry. No competitor generates all 5 integrations simultaneously from a single manifest.

**Fix**: Add a "Supported hosts" section to README with: "One `cfs generate-agents` command
produces integration files for Claude Code, Cursor, Windsurf, GitHub Copilot, and OpenAI
Codex. Switch tools without relearning the system."

---

**Rf-007** · `README.md` lines 137–145 · **Sub-agent Roles Not Named**

README describes subagent roles (explorer, planner, author, reviewer, validator) but never
names the actual subagents (cf-explorer, cf-planner, cf-semantic-reviewer, etc.) or explains
how they are generated per-host.

**Fix**: Add named subagent list to README with per-host availability table.

---

**Rf-008** · `DESIGN.md` line 70 · **Artifact Model Not Compared to Spec-Driven Competitors**

The modular artifact registry with stable CPT-IDs is more traceable than Kiro's 3-file model
and more flexible than Planu's unified spec.md, but never positioned this way.

**Fix**: One-paragraph comparison in README "Traceability model" section.

---

**Rf-009** · All workflow files · **No Preview-then-Execute**

All workflows proceed sequentially with human approval. LAO's preview-then-execute
(simulate before real changes) is a safety feature for large changes that Constructor Studio
lacks.

**Fix**: P2 `--dry-run` flag on plan/generate that shows expected changes without executing.

---

**Rf-010** · `PRD.md` lines 59–65 · **No AI-Native Architecture Support**

Constructor Studio is code-agnostic. Planu auto-detects AI-native architectures and adds
latency budgets, prompt versioning, and LLM observability to specs.

**Fix**: `studio-kit-ai-native` package for AI-service projects with latency/observability
DESIGN templates.

---

**Rf-011** · `DECOMPOSITION.md` lines 42–50 · **P1 Features In-Progress**

Core Infrastructure (F1), Kit Management (F2), Traceability & Validation (F3), Execution
Plans (F11), Subagent Registration (F13), ralphex Delegation (F14), Project-Level
Extensibility (F15) — all high-priority, all in-progress. Planu and claude-code-sdlc are
mature.

**Fix**: Publish public roadmap with target dates for P1 items. Add "feature availability"
table to README.

---

**Rf-012** · `PRD.md` line 658 · **No Security / Monitoring Phases**

autonomous-sdlc bundles 11 phases including security audit and monitoring. Constructor Studio
stops before security and CI/CD monitoring.

**Fix**: `studio-kit-security` package with OWASP-aligned security checklists.

---

**Rf-013** · `README.md` line 10 · **Target Audience Too Broad**

"Developers, product managers, architects, technical leads" describes every software team.

**Fix**: "Teams using multiple AI coding tools who need traceable, offline, deterministic
validation — best fit for multi-host, review-sensitive, or regulated-adjacent work."
Add "Not for" list.

---

**Rf-026** · `workflows/explain.md` lines 1–59 · **Explain Workflow Not Positioned**

Standalone `cf explain:` with EXPLAIN_MODE, 6 pedagogical modes, session checkpointing, and
package export to disk under `.cache/explain/packages/{slug}-{ISO}/` is never presented as
a differentiator. No competitor has this.

**Fix**: Add "Explain mode" section to README with the 6 modes and package export capability.
Position as: "Generate onboarding packages, code tours, or decision narratives — exported to
disk for persistent documentation."

---

**Rf-027** · `workflows/explore.md` lines 86–188 · **Explore Save-to-Disk Not Promoted**

Explore bundles (result.json, resource-map.md, summary.md) saved to `.cache/explore/` with
refine loop and 6-action routing menu. Planu has only MCP tool; cc-sdd's /kiro-discovery is
less structured.

**Fix**: Promote explore as workflow entry point in README: "Start with `cf explore:` to
discover context, save exploration bundles, and route to any downstream workflow."

---

**Rf-028** · `workflows/generate.md` lines 156–163 · **Built-in Review Loop Not Marketed**

Phase 5 (deterministic gate + semantic review + approval + remediation) is embedded within
artifact generation. Competitors validate after-the-fact or require external review tools.

**Fix**: In README generate description: "Every artifact goes through deterministic validation
and semantic review before you approve — built in, not bolted on."

---

**Rf-029** · `workflows/generate.md` lines 141–186 · **Author-plan Subagent Not Visible**

Phase 1.5 cf-planner subagent produces structured author plan before writing, with user
choice of storage (memory/disk/inline). cc-sdd's /kiro-impl has phases but no explicit
planning step.

**Fix**: Mention in USAGE-GUIDE under "Generate workflow" as optional quality step.

---

**Rf-030** · `workflows/generate/reverse-engineering.md` lines 26–70 · **Brownfield Gate Not Compared to Kiro**

Brownfield auto-config gate detects missing task-matched rules and offers to generate
rules/AGENTS.md/artifacts.toml entries before generating. Kiro auto-generates structure.md/
tech.md/product.md (similar goal, different output: docs vs. rules+config).

**Fix**: In README "Fit and non-fit" add: "Joining an existing project? `cf auto-config`
scans your conventions and generates rules — not just docs."

---

**Rf-032** · `workflows/generate/phase-0.7/round-loop.md` lines 23–93 · **Brainstorm Orchestration Modes**

Two modes per round: single-agent (host-independent) vs. fan-out (parallel expert dispatch).
Env var configurable (PANEL_MODE_TOPIC, PANEL_MODE_CHALLENGE). No competitor has this.

**Fix**: Document in USAGE-GUIDE under "Advanced brainstorm options."

---

**Rf-034** · `workflows/generate/phase-0.7/wrap-handoff.md` lines 54–113 · **Brainstorm Next-Step Routing**

5 explicit options after brainstorm: session-only save, disk save (.cache/brainstorm/{id}/),
route to generate, route to analyze, reopen a topic gap. Decisions and open questions carried
forward.

**Fix**: Add brainstorm workflow diagram to USAGE-GUIDE showing the explore → brainstorm →
generate/plan/analyze pipeline.

---

**Rf-036** · `workflows/map.md` lines 119–476 · **Map Config-Assist Not Promoted**

Config-assist mode parses existing JSON map, groups nodes by path prefix, derives category
names deterministically, proposes md-map.toml with palette selection (fixed/light/dark/
pastel/neon). Federation-aware (single-repo vs. with-workspace scope). Unique.

**Fix**: Document in README dependency map section and USAGE-GUIDE as "guided category setup."

---

### 🟢 LOW — Minor gaps and underpublicized advantages

| # | Finding | Suggested action |
|---|---------|-----------------|
| Rf-014 | Kit system (file-level diff, manifest) not compared to Planu skills / Kiro Powers | One-paragraph comparison in "Core platform and optional kits" |
| Rf-015 | Offline validation not highlighted as feature | Add to "Product shape" bullet |
| Rf-016 | Multi-repo workspace federation: unique, not promoted | Lead with in competitive positioning |
| Rf-017 | Dependency map unique: not promoted | Promote with federation + phantom-ID angles |
| Rf-018 | CDSL unique: no dedicated section | Add to README |
| Rf-019 | Execution plan line budgets not explained | "LLM context management built in" framing |
| Rf-020 | Language complexity setting (low/middle/high) not promoted | Unique accessibility differentiator |
| Rf-021 | Explain mode (6 pedagogical modes) noted in v1, now confirmed separate workflow | Surface in positioning |
| Rf-031 | Git commit mode (GIT_COMMIT_MODE) — parity with some competitors | Document in USAGE-GUIDE |
| Rf-033 | Explore clarify gate — good UX, prevents empty invocations | Document in USAGE-GUIDE |
| Rf-035 | PDSL pre/post-flight validation gates — part of Rf-023 | Covered |
| Rf-037 | No autonomous execution — confirms Rf-004 | No additional action |

---

## Recommended Actions (Priority Order)

### Priority 1 — Positioning (high ROI, zero code changes)

1. **Add "Competitive positioning" section to README.md** after "Fit and non-fit" — name 3–5
   competitors, state 3 differentiators, include "Not for" list
2. **Elevate deterministic validation** to first-class README bullet with CI angle
3. **Promote 5 UNIQUE capabilities** in README "Workflow model": brainstorm-within-generate,
   PDSL prompt engineering, 4-layer manifest + cross-agent translation, plan compilation,
   explain/storytelling package export
4. **Add "Supported hosts" section** — "one `cfs generate-agents` for 5 hosts simultaneously"
5. **Tighten audience statement** — from generic to specific (multi-host teams + traceability
   + offline)

### Priority 2 — Capability roadmap (closes critical competitive gaps)

6. **Retroactive healing** (`cfs heal`): LLM-suggested fixes from `cfs validate` output —
   closes Planu gap
7. **Autonomous mode**: `--autonomous` flag on generate/plan that skips interactive gates —
   closes cc-sdd/LAO gap
8. **Compliance kit** (`studio-kit-compliance`): SOC 2/HIPAA/GDPR/PCI-DSS — opens regulated
   markets
9. **Preview-then-execute**: `--dry-run` on generate/plan — closes LAO gap

### Priority 3 — Documentation fills

10. **Named subagent reference table** — cf-explorer, cf-planner, cf-semantic-reviewer,
    cf-pdsl-author etc. with per-host availability
11. **Workflow overview diagram** — explore → brainstorm → generate/plan/analyze pipeline
12. **Brownfield vs Kiro comparison** — auto-config generates rules+config, Kiro generates docs
13. **Feature availability table** — P1 done/in-progress/P2/kit for honest v1.0 expectations
14. **Orchestrator repo pattern** — 4-layer manifest + cross-agent translation with examples

---

## Summary Score

| Dimension | Assessment |
|-----------|-----------|
| **Unique to Constructor Studio** (no competitor has these) | Brainstorm-within-generate, PDSL workflow, 4-layer manifest + cross-agent translation, plan compilation, explain package export, multi-repo workspace, dependency map, CDSL, language complexity, map config-assist, brainstorm orchestration modes |
| **Constructor Studio advantage** (materially better) | Explore save/route, generate built-in review loop, author-plan subagent, brownfield auto-config, kit file-diff update, offline validation, deterministic CI-ready validation |
| **Constructor Studio parity** | Multi-host support (comparable to Planu/cc-sdd), artifact model (comparable to Kiro/Planu) |
| **Constructor Studio gaps** | Retroactive healing (Planu only), autonomous execution (Planu/cc-sdd/LAO), compliance gates (claude-code-sdlc only), preview-then-execute (LAO only), AI-native arch support (Planu only) |
| **Strategic position** | Infrastructure + methodology layer for multi-host teams prioritizing determinism, traceability, and extensibility over end-to-end automation |
