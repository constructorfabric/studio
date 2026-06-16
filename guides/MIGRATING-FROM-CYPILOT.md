# Migrating from Cypilot to Constructor Studio

A concise, step-by-step guide. Migration runs in **two stages**: a deterministic mechanical step (one CLI call) and a post-deterministic intelligent cleanup orchestrated by `cf migrate from cypilot`.

<!-- toc -->

- [Stage 1 — Deterministic (Mechanical) Migration](#stage-1--deterministic-mechanical-migration)
- [Stage 2 — Post-Deterministic Cleanup (`cf migrate from cypilot`)](#stage-2--post-deterministic-cleanup-cf-migrate-from-cypilot)
- [What Is NOT Touched](#what-is-not-touched)
- [Final Manual Checks](#final-manual-checks)
- [How to Invoke](#how-to-invoke)

<!-- /toc -->

---

## Stage 1 — Deterministic (Mechanical) Migration

A single CLI call performs the fixed-scope transforms: directory copy, managed-block swap (`@cpt:root-agents → @cf:root-agents`), TOML/Markdown rewrites across a fixed file list, and the `format = "Cypilot" → "CFS"` rename inside `[kits.*]` tables.

**Step 1.** Ensure a clean working tree (`git status`) and create a backup branch.

**Step 2.** Run exactly one of:
- Fresh install: `cfs init --migrate-from-cypilot=yes`
- Existing install: `cfs update --migrate-from-cypilot=yes`

**Step 3.** Verify Stage 2 preconditions:
- Root `AGENTS.md` now contains `<!-- @cf:root-agents -->` (no longer `@cpt:`).
- `{cf-studio-path}/config/core.toml` exists.

---

## Stage 2 — Post-Deterministic Cleanup (`cf migrate from cypilot`)

The orchestrator loads the shared Studio runtime first, then dispatches scanner, planner, migrator, and verifier subagents through the standard dispatch gate. You can approve a dispatch once, approve subagents for the session, run the work inline, or stop. It cleans up everything the mechanical step does not touch: source code, CI configs, build files, docs outside the fixed list, shell scripts, agent integrations (`.claude/`, `.cursor/`, `.codex/`, `.windsurf/`), and workspaces.

**Step 4. E0 — Preconditions.** The orchestrator re-validates the marker and `core.toml`. If it fails, re-run Stage 1.

**Step 5. E1 — Scanner (read-only).** Approve the scanner dispatch when prompted. Subagent `cf-migrate-scanner` emits a structured findings list of residual `cypilot / cpt / Cypilot / Cyber Pilot` references. No files are modified.

**Step 6. E2 — Planner (read-only).** Approve the planner dispatch when prompted. `cf-migrate-planner` groups findings into three categories:
- **A** — auto-fixable (unambiguous string substitutions);
- **B** — needs-review (context-sensitive);
- **C** — cascade (rename to `.studio-workspace.toml`, cascade migration into workspace member repos, regenerate IDE integrations via `cfs generate-agents`).

**Step 7. E3 — Migrator (write).** The orchestrator prints the full plan, then offers a menu:
- `1` — apply category A only;
- `2` — apply A and walk through B interactively;
- `3` — A + B + start C (cascade commands are **printed**, not auto-executed);
- `4` — pick specific items;
- `N` — skip.

A safe starting choice is `1`. The migrator writes using Constructor Studio target identifiers: `.studio-workspace.toml`, `skills/studio/`, CLI `cfs`, cache `~/.cf-studio/cache/`, registry `constructorfabric/studio`.

Before the write-capable migrator runs, Studio resolves the session git write policy. Choose `commit`, `stage`, or `none`. The migration can still inspect git state in `none` mode, but it must not stage or commit unless the selected policy permits it and the workflow asks for that action.

**Step 8. E4 — Verifier (read-only).** Approve the verifier dispatch when prompted. Re-scans and diffs against the migration manifest. Returns either *All clean* or a residue list.

Normal `cfs generate-agents` now preserves legacy Cypilot / Cyber Constructor artifacts. During migration cleanup, use the explicit cleanup path:

```bash
cfs generate-agents --remove-cypilot yes
```

The orchestrated migration invokes the same explicit removal mode for affected host integrations.

**Step 9. E5 — Migrator ↔ Verifier loop.** If residue remains, repeat E3 → E4. **Hard cap: 3 verifier iterations**, after which the orchestrator moves to E6 with remaining items listed for manual review.

**Step 10. E6 — Final Report.** You receive a summary: applied vs. skipped counts, outstanding manual work, cascade commands to run by hand (e.g. `cfs init --migrate-from-cypilot=yes` in each workspace member repo), and suggested next steps.

---

## What Is NOT Touched

- Files outside `project_root`.
- Anything inside `{cf-studio-path}/.core/` or `{cf-studio-path}/.gen/` — generated Studio runtime, repaired by `cfs init`/`cfs update`.
- `@cpt-*` / `@cpt:*` markers inside constructor-studio's own source — by v1.0.0 design these are intentionally preserved and routed to needs-review (B).

---

## Final Manual Checks

1. `git diff` — spot-check identifier substitutions.
2. Run tests / lint / CI locally.
3. For multi-repo workspaces — execute the printed C-category commands in each member repo.
4. Run `cfs generate-agents --remove-cypilot yes` if `.claude/`, `.cursor/`, `.codex/`, or `.windsurf/` integrations were modified and you want legacy Cypilot artifacts removed. Use plain `cfs generate-agents` only when you want to preserve them.
5. Commit on a dedicated branch → open a PR labelled "cypilot → constructor-studio migration".

---

## How to Invoke

Inside a chat with the `cf` skill active, type:

```
cf migrate from cypilot
```

(or `migrate-from-cypilot`). The orchestrator will walk you through phases E0–E6, using the shared subagent approval gate for each dispatch group unless you approve subagents for the session.
