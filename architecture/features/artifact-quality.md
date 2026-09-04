# Feature: Artifact Quality

<!-- toc -->

- [1. Feature Context](#1-feature-context)
  - [1. Overview](#1-overview)
  - [2. Purpose](#2-purpose)
  - [3. Actors](#3-actors)
  - [4. References](#4-references)
- [2. Actor Flows (CDSL)](#2-actor-flows-cdsl)
  - [Assess Artifact Quality](#assess-artifact-quality)
- [3. Processes / Business Logic (CDSL)](#3-processes--business-logic-cdsl)
  - [Artifact-Quality Finding Model](#artifact-quality-finding-model)
- [4. States (CDSL)](#4-states-cdsl)
  - [Finding Lifecycle](#finding-lifecycle)
- [5. Definitions of Done](#5-definitions-of-done)
  - [Finding Model Contract](#finding-model-contract)
- [6. Implementation Modules](#6-implementation-modules)
- [7. Acceptance Criteria](#7-acceptance-criteria)

<!-- /toc -->

- [ ] `p1` - **ID**: `cpt-studio-featstatus-artifact-quality`

## 1. Feature Context

- [ ] `p1` - `cpt-studio-feature-artifact-quality`

### 1. Overview

Surfaces advisory **semantic-quality findings** on Project Markdown artifacts (Vision, PRD, Epics, feature specs) — duplication, purpose-mismatch, gap, traceability-meaning, and contradiction — as evidence plus a suggested action. Read-only and Markdown-first: it never rewrites an artifact, produces no combined score, and never gates a build. Structural detectors run in-core (stdlib); meaning-level detectors reuse the advisory judge seam. This first piece is the shared **finding model** every detector emits and the JSON schema a presentation layer consumes.

### 2. Purpose

Studio's deterministic layer assures code (`validate`, `spec-coverage`, CPT markers); the specification documents themselves have no comparable signal — nothing flags a requirement duplicated across three docs, content in the wrong doc type, a drifted trace link, or two artifacts that contradict. A single, versioned finding shape lets every detector speak one contract and a UI present findings side-by-side.

### 3. Actors

| Actor | Role in Feature |
|-------|-----------------|
| `cpt-studio-actor-user` | Reviews the surfaced findings and decides what to act on |
| `cpt-studio-actor-ai-agent` | Emits findings while assessing artifacts; consumes the model |

### 4. References

- **PRD**: [PRD.md](../PRD.md) — `cpt-studio-fr-core-traceability`
- **Design**: [DESIGN.md](../DESIGN.md) — `cpt-studio-component-traceability-engine`
- **Dependencies**: `cpt-studio-feature-spec-coverage`

## 2. Actor Flows (CDSL)

### Assess Artifact Quality

- [ ] `p1` - **ID**: `cpt-studio-flow-artifact-quality-assess`

**Actor**: `cpt-studio-actor-user`

**Success Scenarios**:
- User runs `cfs artifact-quality` → registered artifacts are scanned, findings are emitted as JSON plus a one-line human summary, nothing is rewritten and no exit code changes

**Steps**:
1. [ ] - `p1` - User invokes `cfs artifact-quality [--detectors ...]`; registered artifacts are scanned and findings emitted as JSON plus a one-line summary, nothing is rewritten (command lands in a later task; the finding model below is the contract it emits) - `inst-aq-assess-invoke`

## 3. Processes / Business Logic (CDSL)

### Artifact-Quality Finding Model

- [x] `p1` - **ID**: `cpt-studio-algo-artifact-quality-finding-model`

**Input**: a detector's assessment of one artifact (or artifact pair)

**Output**: an `ArtifactFinding` (advisory, read-only) and its serialised `to_dict` shape

**Steps**:
1. [x] - `p1` - Model a `Locus` — where in an artifact a finding sits — validating its field types and, on construction, that the path is a canonical project-relative POSIX path (non-empty, no leading `/`, no `\`, no `.`/`..`/empty `//` segments, no control chars), the optional line is a 1-based int, and the optional anchor is a non-empty control-char-free string; serialising only the fields that were set - `inst-aq-locus`
2. [x] - `p1` - Model an `ArtifactFinding` and validate it on construction — first field types, then values: advisory severity only (no `error`), a non-empty message, a structural finding carries no verdict and no judged-only metadata (`confidence`/`evidence_ok`), a judged finding must carry a detector-namespaced verdict (or `unjudgeable`), and `schema_version` pinned (an int, not a bool) to the one supported contract - `inst-aq-finding`
3. [x] - `p1` - Serialise an `ArtifactFinding` to the wire shape — every required key plus `schema_version`, the optional `related`/`verdict`/`confidence` only when set, with no combined score and no edit payload - `inst-aq-finding-serialize`

**Supporting**:
- [x] - `p1` - Module imports and the model constants: `SCHEMA_VERSION`, the detector / severity / kind vocabularies, and the shared `unjudgeable` verdict - `inst-aq-imports`
- [x] - `p1` - The versioned wire contract, handed out as a fresh deep copy by `finding_json_schema()` (never a mutable shared global) — `schema_version` pinned to the supported contract, the kind↔verdict rule encoded on the wire (structural carries no verdict or judged-only metadata, judged requires a verdict), path and non-blank patterns that mirror the constructor exactly (explicit whitespace class, not ECMA `\s`), optional keys only when set, and no score field or edit payload - `inst-aq-schema`

## 4. States (CDSL)

### Finding Lifecycle

- [ ] `p1` - **ID**: `cpt-studio-state-artifact-quality-finding`

A finding is **emitted** by a detector, **presented** to the user, and **acted on or dismissed** by them. It is never applied automatically. *(The lifecycle is realised once the detectors and command land in later tasks; the model here fixes the shape it moves through.)*

## 5. Definitions of Done

### Finding Model Contract

- [ ] `p1` - **ID**: `cpt-studio-dod-artifact-quality-finding-model`

The finding model is done when every detector can express its result as one `ArtifactFinding` — advisory, read-only, detector-namespaced verdict, no combined score — and a presentation layer can rely on the versioned wire contract from `finding_json_schema()`. *(Measured against the detectors as they land; the model + schema + their tests are the first, standalone deliverable.)*

## 6. Implementation Modules

| Module | Path | Responsibility |
|---|---|---|
| Artifact-Quality Finding Model | `skills/studio/scripts/studio/utils/artifact_quality.py` | The shared `ArtifactFinding` / `Locus` model, its `to_dict`, and the versioned JSON schema every detector and the presentation layer share |

## 7. Acceptance Criteria

- [x] A finding names exactly one detector, carries an advisory severity (`info` / `warn`, never `error`), and never carries a combined score or an edit payload
- [x] A structural finding has `verdict = None`; a judged finding carries a detector-namespaced verdict (or `unjudgeable`) — construction raises otherwise
- [x] `to_dict` emits the required keys plus `schema_version`, and omits `related` / `verdict` / `confidence` when unset
- [x] `finding_json_schema()` returns the versioned wire contract (a fresh copy) that validates a serialised finding, versioned by `schema_version`
