# Contract/Doc Gaps Review — 2026-06

<!-- toc -->

- [Overview](#overview)
- [Gap 1: Root Runtime Metadata Lifecycle Spec](#gap-1-root-runtime-metadata-lifecycle-spec)
- [Gap 2: Generated Agent Output Contract Spec](#gap-2-generated-agent-output-contract-spec)
- [Gap 3: Human vs JSON Output Contract Spec](#gap-3-human-vs-json-output-contract-spec)

<!-- /toc -->

## Overview

This note captures architecture-level gaps that are materially exercised by
contracts and `_e2e` tests but are still scattered across multiple docs instead
of being specified once as authoritative behavior.

## Gap 1: Root Runtime Metadata Lifecycle Spec

Why it matters:

- `_e2e` tests enforce that commands such as `info`, `agents`, and
  `validate-toc` are read-only.
- setup and migration flows explicitly rewrite root `AGENTS.md` and `CLAUDE.md`
  managed blocks.
- legacy migration and repair semantics already include dirty-file and backup
  behavior.

What is missing:

- one dedicated spec for root managed block format, lifecycle, rewrite triggers,
  dirty-file safety, migration from legacy markers, and read-only invariants

Recommended home:

- new spec under `architecture/specs/root-runtime-metadata.md`

## Gap 2: Generated Agent Output Contract Spec

Why it matters:

- `generate-agents` and `agents` have a stable public contract across multiple
  providers
- canonical kit manifests now include `public`, `generated_targets`, and nested
  `subagents`
- `_e2e` covers partial-success reporting, provider-specific skip reasons,
  generated path ownership, legacy cleanup, and `.gitignore` integration

What is missing:

- one authoritative spec for generated output locations, ownership model,
  detection markers, provider capability matrix, partial-result schema, and
  cleanup rules

Recommended home:

- new spec under `architecture/specs/generated-agent-outputs.md`

## Gap 3: Human vs JSON Output Contract Spec

Why it matters:

- `_e2e` distinguishes human-mode summaries from machine JSON contracts
- statuses such as `OK`, `FOUND`, `NOT_FOUND`, `PASS`, `WARN`, `FAIL`,
  `PARTIAL`, and `CONFIG_ERROR` are externally observable
- several commands guarantee read-only behavior in both modes

What is missing:

- one normalized status taxonomy and output-shape spec across JSON mode and
  human mode, including when partial success is fatal vs non-fatal

Recommended home:

- new spec under `architecture/specs/output-contracts.md`
