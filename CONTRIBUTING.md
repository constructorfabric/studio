# Contributing to Constructor Studio


<!-- toc -->

- [Prerequisites](#prerequisites)
- [Development Setup](#development-setup)
- [Generated Agent Integrations](#generated-agent-integrations)
- [Project Architecture (Self-Hosted Bootstrap)](#project-architecture-self-hosted-bootstrap)
  - [Critical Rule](#critical-rule)
- [Versioning](#versioning)
  - [Version Locations](#version-locations)
  - [Releasing a New Version](#releasing-a-new-version)
- [Branch and Release Workflow](#branch-and-release-workflow)
- [Commit Requirements (DCO)](#commit-requirements-dco)
  - [How to sign off](#how-to-sign-off)
  - [Retroactive sign-off](#retroactive-sign-off)
  - [Why DCO?](#why-dco)
- [CI Pipeline](#ci-pipeline)
  - [Running CI Locally](#running-ci-locally)
  - [Makefile Targets](#makefile-targets)
  - [GitHub Actions](#github-actions)
- [Prompt Tests (cf-skill UX)](#prompt-tests-cf-skill-ux)
  - [Prerequisites](#prerequisites-1)
  - [Running](#running)
  - [Tuning](#tuning)
  - [Adding scenarios](#adding-scenarios)
  - [What to do when a scenario fails](#what-to-do-when-a-scenario-fails)
- [Making Changes](#making-changes)
  - [Code Changes](#code-changes)
  - [Architecture / Spec Changes](#architecture--spec-changes)
- [Pull Request Process](#pull-request-process)
- [Code Style and Conventions](#code-style-and-conventions)
- [Questions?](#questions)

<!-- /toc -->

Thank you for your interest in contributing to Constructor Studio! This guide covers the development workflow, versioning scheme, bootstrap architecture, commit requirements, and CI pipeline.

---

## Prerequisites

- **Python 3.11+** (uses `tomllib` from stdlib)
- **Git**
- **pipx** (recommended for global CLI and test tooling)
- **make**
- **Docker** (for local CI via `act`)
- **[act](https://github.com/nektos/act)** (runs GitHub Actions locally)
- **[actionlint](https://github.com/rhysd/actionlint)** (lints workflow files)

## Development Setup

```bash
# Clone the repo
git clone https://github.com/constructorfabric/studio.git
cd studio

# Install the cfs/constructor-studio CLI proxy (referred to as the CLI surface in the README glossary) from local source
make install-proxy

# Bootstrap: sync .bootstrap/ from local source
make update

# Generate local AI coding tool integrations
make generate-agents

# Run full CI locally (mirrors GitHub Actions exactly)
make ci
```

---

## Generated Agent Integrations

Host integration files are generated local artifacts and are intentionally not
tracked in git. Before starting development, refresh both the self-hosted
bootstrap and all agent integrations:

```bash
make update
make generate-agents
```

`make generate-agents` runs Constructor Studio from `.bootstrap/.core/` and
omits `--agent`, so it regenerates all supported host integrations.

---

## Project Architecture (Self-Hosted Bootstrap)

Constructor Studio builds itself. The repo is simultaneously the **source code** and a **self-hosted Constructor Studio project** with its own `.bootstrap/` setup directory.

```
studio/                           # Project root
├── skills/studio/                # CANONICAL source: skill engine + scripts
├── src/studio_proxy/             # CANONICAL source: CLI proxy (thin shell)
├── schemas/                      # CANONICAL source: JSON schemas
├── architecture/                 # CANONICAL source: PRD, DESIGN, DECOMPOSITION, features
├── requirements/                 # CANONICAL source: checklists
├── .bootstrap/                   # Self-hosted setup directory (cf-studio-path = ".bootstrap")
│   ├── .core/                    #   READ-ONLY mirror of skills/, schemas/, architecture/, etc.
│   ├── .gen/                     #   AUTO-GENERATED aggregates (AGENTS.md, SKILL.md, README.md)
│   └── config/                   #   User-editable config + kit outputs (core.toml, artifacts.toml, kits/)
├── tests/                        # Test suite
└── Makefile                      # CI targets
```

### Critical Rule

> **Do not edit files under `.bootstrap/` directly when contributing.**
> In this self-hosted repo, `.bootstrap/` is a bootstrap copy of a Constructor Studio version used
> to develop Constructor Studio itself — similar to bootstrapping a compiler.
> This is a repo-specific self-hosted setup, not the general user-project layout described in the README.
> Treat `.bootstrap/.core/` and `.bootstrap/.gen/` as generated bootstrap mirrors that are
> intentionally **not tracked in git**. Always edit the canonical source files under project
> root (`skills/`, `kits/`, `schemas/`, `architecture/`, `requirements/`, etc.).
> Before starting work, run `make update` and `make generate-agents` so your local bootstrap
> copy and agent integrations are in sync with the canonical source. Re-run `make update`
> whenever you need to refresh the local bootstrap for manual verification, but do not commit
> `.bootstrap/.core/`, `.bootstrap/.gen/`, or generated host integration files.

The `make update` command runs `cfs update --source . --force`, which:
1. Copies canonical sources into `.bootstrap/.core/`
2. Regenerates `.bootstrap/.gen/` aggregates
3. Updates kit files in `.bootstrap/config/kits/`

---

## Versioning

A release is a **GitHub Release and its tag**, and nothing else (ADR-0021). No file in the
repository is bumped to make a release.

### Version Locations

| What | Where the version comes from |
|------|------------------------------|
| **CLI proxy** (`constructor-studio`, installed with `pipx`) | The Git tag, through `setuptools_scm` (`dynamic = ["version"]` in `pyproject.toml`). A build from `vX.Y.Z` reports `X.Y.Z`. |
| **Skill bundle** in the user's cache, and the core installed in a project | The latest published GitHub Release, or the ref the user asked for, recorded with its provenance (`cfs --version` shows it). |
| `skills/studio/scripts/studio/__init__.py` (`__version__`) | Not a release version. `make check-versions` uses it only to check that `.bootstrap/` is in sync, so it is not bumped for a release. |
| `.bootstrap/version.toml`, `.bootstrap/whatsnew.toml` | This repository's own pinned Studio version. They are updated **after** a release, in step 8 below. |

### Releasing a New Version

1. **Choose the cut point.** Pick a commit on `main` whose CI is green, and decide which merged
   pull requests the release includes. Anything merged after the cut point waits for the next one.

2. **Cut the release branch from `main`**, never from the previous tag. A release built from an
   older tag and assembled by cherry-picks ships a tree that is not on `main` (#257).
   ```bash
   git push origin <sha>:refs/heads/release/vX.Y.Z
   ```
   CI runs on `release/**`, so the branch is tested as soon as it exists.

3. **Stabilise, fixes first on `main`.** A fix lands on `main` by pull request, then goes into the
   release branch with `git cherry-pick -x`. Before tagging, the branch must hold nothing `main`
   lacks, so this prints nothing:
   ```bash
   git log --cherry-pick --right-only --no-merges origin/main...origin/release/vX.Y.Z
   ```

4. **Verify locally** on the release branch head:
   ```bash
   make check-versions validate self-check validate-kits spec-coverage declared-stops test-gates
   make test
   ```

5. **Write the release notes.** They are user-facing only and in English: what changed for
   someone using `cfs` and the skills, not CI, tests or refactors. They are shown to users by
   `cfs update` as "What's New", so state behaviour changes plainly and check each claim
   against the release branch. Follow the shape of the previous release: `## What's New`,
   `## Bug Fixes`, and a **Full Changelog** link.

6. **Publish the GitHub Release.** This creates the tag on the release branch head:
   ```bash
   gh release create vX.Y.Z --target <release-branch-head-sha> \
       --title vX.Y.Z --notes-file notes.md --latest
   ```

7. **Smoke-test the published release** in an isolated home, the way a user installs it:
   ```bash
   export HOME=$(mktemp -d) PIPX_HOME=$HOME/pipx PIPX_BIN_DIR=$HOME/bin
   pipx install "git+https://github.com/constructorfabric/studio.git@vX.Y.Z"
   $HOME/bin/cfs --version   # package X.Y.Z; skill cache vX.Y.Z, verified
   ```

8. **Bump this repository's own pin** in a pull request to `main`. Set `version` and
   `requested_ref` in `.bootstrap/version.toml` to `vX.Y.Z`, and add the release's
   `[whatsnew."vX.Y.Z"]` section to the top of `.bootstrap/whatsnew.toml`. Copy that section
   from the `whatsnew.toml` the smoke test's `cfs` wrote under `$HOME/.cf-studio/cache/`, so it
   is the same text users see.

---

## Branch and Release Workflow

```
main                          # Every change lands here first; CI must pass
└── release/vX.Y.Z            # Cut from main at the release's cut point; tagged vX.Y.Z
```

- Feature and fix branches start from `main` and merge into `main` by pull request.
- A release branch receives only cherry-picks of fixes already on `main`.
- The tag `vX.Y.Z` is created on the release branch head by publishing the GitHub Release.

---

## Commit Requirements (DCO)

All commits **must** include a `Signed-off-by` line — the [Developer Certificate of Origin](https://developercertificate.org/) (DCO).

### How to sign off

```bash
# Every commit must use -s
git commit -s -m "feat(validate): add cross-reference checking"
```

This appends:
```
Signed-off-by: Your Name <your.email@example.com>
```

### Retroactive sign-off

If you forgot `-s`, amend the last commit:
```bash
git commit --amend -s --no-edit
```

For multiple commits:
```bash
git rebase --signoff HEAD~N
```

### Why DCO?

The project uses Apache-2.0 license. DCO certifies that you wrote the contribution (or have the right to submit it) and agree to the project's license terms.

---

## CI Pipeline

### Running CI Locally

`make ci` runs the **same workflow** as GitHub Actions, locally via [act](https://github.com/nektos/act) in Docker, excluding jobs that require GitHub-hosted context `act` cannot reconstruct: **SonarQube** (needs `SONAR_TOKEN`) and **code-ranker** (a GitHub-only reusable workflow needing checkout/event context). Single source of truth — `.github/workflows/ci.yml`.

```bash
# Run full CI (auto-detects arm64/amd64)
make ci

# Override act flags if needed
make ci ACT_FLAGS="--container-architecture linux/amd64"
```

Jobs run sequentially and stop on first failure. On Apple Silicon, containers run natively as arm64. Matrix jobs are limited to Python 3.13 by default to avoid Docker resource exhaustion.

`make lint-ci` lints the workflow files with `actionlint` (also runs as part of `make ci`).

### Makefile Targets

All CI is driven through `make`. No virtual environment required — tools run via `pipx`.

| Target | What it does | CI? |
|--------|-------------|-----|
| `make ci` | Run full CI locally via act (mirrors GitHub Actions) | — |
| `make lint-ci` | Lint GitHub Actions workflow files | — |
| `make test` | Run full test suite via `pipx run pytest` | Yes |
| `make test-verbose` | Tests with verbose output | — |
| `make test-quick` | Fast tests only (skip `@pytest.mark.slow`) | — |
| `make test-coverage` | Tests + coverage report (≥90% required) | Yes |
| `make validate` | Run `cfs validate` — deterministic artifact validation | Yes |
| `make self-check` | Validate SDLC kit examples against their own templates | Yes |
| `make validate-kits` | Validate all registered kits | Yes |
| `make check-versions` | Check version consistency across components | Yes |
| `make spec-coverage` | Check spec coverage (≥90% overall, ≥60% per file) | Yes |
| `make pylint` | Pylint static analysis (staged rollout) | Yes |
| `make vulture` | Dead code scan (report only) | — |
| `make vulture-ci` | Dead code scan (fails on findings) | Yes |
| `make install` | Install pytest + pytest-cov via pipx | — |
| `make install-proxy` | Reinstall `cfs`/`constructor-studio` CLI from local source | — |
| `make install-prompt-tests` | Pre-cache `promptfoo` for cf-skill UX tests (see [Prompt Tests](#prompt-tests-cf-skill-ux)) | — |
| `make test-prompts` | Run cf-skill UX pilot through real `claude` + `codex` CLIs | — |
| `make test-prompts-view` | Open promptfoo HTML report for the last `test-prompts` run | — |
| `make update` | Sync `.bootstrap/` from local source | — |
| `make clean` | Remove `__pycache__`, `.pyc`, `.pytest_cache` | — |

### GitHub Actions

CI runs on pushes and PRs for `main` and `release/**` branches. The workflow has ten job definitions; the Python matrices expand them into separate runner jobs:

1. **Test** — uninstrumented `make test` on Python 3.11, 3.12, 3.13, and 3.14
2. **Coverage** — `make test-coverage` on Python 3.14 (≥90% gate)
3. **Enforcement Gates** — seeded violations must fail and known-good fixtures must pass
4. **SonarQube** — coverage scan only when `SONAR_TOKEN` is available; otherwise the whole job is skipped
5. **Pylint** — `make pylint` static analysis (staged rollout configured in `pyproject.toml`)
6. **Vulture** — `make vulture-ci` dead code scan
7. **Versions** — `make check-versions` (proxy sync, bootstrap sync)
8. **Declared Stops** — `make declared-stops`: fails when a workflow declares more stops than `architecture/baselines/declared-stops.json` records, or is missing from it
9. **Spec Coverage** — `make spec-coverage` (≥90% overall, ≥60% per file)
10. **Validate Artifacts and Kits** — `make validate`, `make self-check`, and `make validate-kits` in one job per Python 3.11–3.14 version; later checks still run after an earlier validation failure unless cancelled

All applicable checks should pass before merge.

---

## Prompt Tests (cf-skill UX)

`tests/prompts/cf-ux/` is a [promptfoo](https://www.promptfoo.dev/)-driven
pilot that exercises the `cf` skill end-to-end through the **real**
`claude` and `codex` CLIs to catch UX regressions (routing, skill
selection, anti-improvisation, gate behavior) that unit tests can't see.

Each test runs in a fresh `tempfile.mkdtemp()` sandbox that is bootstrapped
via the in-tree studio engine (no network calls — `CACHE_DIR` is patched
to the repo root) plus `cfs generate-agents` for both `claude` and `openai`
integrations. Sandboxes are tracked and cleaned via `atexit`,
SIGTERM/SIGINT/SIGHUP handlers, and pid-aliveness sweep, so a killed
promptfoo worker never leaks a tmpdir.

### Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| `node` / `npx` | Runs `promptfoo` via npx | https://github.com/nvm-sh/nvm |
| `claude` | Claude Code CLI (provider + grader) | https://docs.claude.com/en/docs/claude-code |
| `codex`  | OpenAI Codex CLI (provider) | https://developers.openai.com/codex/cli |
| `cfs`    | Studio CLI for sandbox init | `make install-proxy` |

Both CLIs must be authenticated (subscription or API key) — the tests
consume real API tokens.

### Running

```bash
make install-prompt-tests   # pre-flight + warm the npx cache
make test-prompts           # full pilot (~3 min on cheap models)
make test-prompts-view      # open the HTML report
```

### Tuning

| Env / Make var | Default | Notes |
|---|---|---|
| `PROMPTFOO_VERSION` | `latest` | Pin to a specific promptfoo release. |
| `PROMPT_TESTS_TIMEOUT_MS` | `900000` | Worker timeout — needs headroom for cold sandbox. |
| `CF_UX_CLAUDE_MODEL` | `claude-haiku-4-5` | Override per-test claude model. |
| `CF_UX_CLAUDE_EFFORT` | `low` | Claude reasoning effort. |
| `CF_UX_CODEX_MODEL` | `gpt-5.6-sol` | Override per-test codex model. Set this when the default slug is withdrawn — run `codex` to see what the account is entitled to. |
| `CF_UX_CODEX_EFFORT` | `low` | Codex reasoning effort (`minimal` is incompatible with tools). |
| `CF_UX_CODEX_CONTEXT` | `128000` | Codex context window (default 400k is wasteful for these). |
| `CF_UX_GRADER_MODEL` | `claude-haiku-4-5` | Override LLM-rubric judge model. |
| `CF_UX_SHARED_SANDBOX` | unset | Path to a pre-initialized sandbox to reuse across tests. |
| `CF_UX_KEEP_SANDBOX` | `0` | Set to `1` to keep the sandbox after a run for inspection. |
| `CF_UX_CODEX_DISABLE_PLUGINS` | unset | Comma-separated `name@marketplace` plugins to pass `enabled=false` to codex (only for isolation debugging — the skill should win in any aggressive environment by default). |

### Adding scenarios

Edit `tests/prompts/cf-ux/promptfooconfig.yaml`. Each scenario is a
`{vars: {user_message: ...}, assert: [...]}` block. Use the shared
`*skill_state_rubric` YAML anchor for the LLM-rubric assertion that
checks for any legitimate cf-skill structural state (gate / inputs /
workflow framing / refusal). Scenario-specific guards (e.g. "must not
fabricate findings") go in an additional `llm-rubric` block.

### What to do when a scenario fails

The pilot is designed to surface **real** UX bugs, not just rubric
miscalibrations. When a scenario fails:

1. Run `CF_UX_KEEP_SANDBOX=1 make test-prompts` to keep the sandbox for
   inspection.
2. Reproduce the call manually with `--json` to see the model's tool-
   call trace (`codex exec ... --json` or `claude -p ... --output-format
   stream-json`).
3. If cf-skill lost skill selection to a competing skill (e.g.
   `superpowers:brainstorming`), strengthen the relevant
   `description` field in `workflows/*.md` or `skills/studio/SKILL.md`
   so cf wins by description authority — do **not** disable the
   competing plugin as a fix; cf must hold in aggressive environments.
4. If cf-skill was selected but didn't follow its protocol, strengthen
   the umbrella `skills/studio/SKILL.md` (Anti-Improvisation Hard Rule
   or Proxy-Workflow Mode Handshake) rather than duplicating logic into
   proxy workflow bodies — proxies must stay thin.

See `tests/prompts/cf-ux/README.md` for the full layout and next-steps
list.

---

## Making Changes

### Code Changes

1. Edit canonical files under `skills/studio/scripts/studio/` (skill engine), `src/studio_proxy/` (CLI proxy), or other project-root source directories
2. Do not patch mirrored files under `.bootstrap/` directly
3. If you need a live manual check against the bootstrap copy, run `make update`, perform the test, and then revert `.bootstrap/` back to the previous state before opening the PR
4. Add or update tests in `tests/`
5. Verify: `make test && make validate`

### Architecture / Spec Changes

1. Edit files under `architecture/` (PRD, DESIGN, DECOMPOSITION, features)
2. If adding new CDSL (Constructor DSL) entries, run `cfs toc <file>` to regenerate the table of contents (separate from `cfs validate-toc`, which checks an existing TOC)
3. If adding `@cpt-*` (Canonical Provenance Trace) code markers, run `cfs validate` to verify traceability (all coverage checks must pass)
4. Verify: `make validate`

---

## Pull Request Process

1. Ensure all CI checks pass locally:
   ```bash
   make ci
   ```

2. Every commit is signed off (DCO):
   ```bash
   git commit -s -m "type(scope): description"
   ```

3. PR description should include:
   - What changed and why
   - Version bumps (if any)
   - Which `make` targets were run

4. For spec changes, include `cfs validate` output showing PASS status

---

## Code Style and Conventions

- **Zero third-party dependencies** — Python stdlib only (skill engine and proxy)
- **Python 3.11+** — use `tomllib`, `pathlib`, type hints
- **No comments or docstrings added/removed** unless explicitly requested
- **Existing code style** — follow patterns in surrounding code
- **Tests** — add tests for new functionality; never delete or weaken existing tests
- **Traceability** — new algorithms/flows in feature specs should have corresponding `@cpt-*` markers in code

---

## Questions?

Open an issue on GitHub or start a discussion. We're happy to help!
