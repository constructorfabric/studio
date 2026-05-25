# Contributing to Constructor Studio


<!-- toc -->

- [Prerequisites](#prerequisites)
- [Development Setup](#development-setup)
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

# Install the cfs/constructor-studio CLI proxy from local source
make install-proxy

# Bootstrap: sync .bootstrap/ from local source
make update

# Run full CI locally (mirrors GitHub Actions exactly)
make ci
```

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
> Treat `.bootstrap/.core/` and `.bootstrap/.gen/` as read-only mirrors.
> Always edit the canonical source files under project root (`skills/`, `kits/`,
> `schemas/`, `architecture/`, `requirements/`, etc.). Run `make update` only when you
> need to verify new behavior live against the bootstrap copy, for example during manual
> testing. After such a test, it is recommended to return `.bootstrap/` to its previous
> state, and the pull request should be clean of bootstrap-only changes.

The `make update` command runs `cfs update --source . --force`, which:
1. Copies canonical sources into `.bootstrap/.core/`
2. Regenerates `.bootstrap/.gen/` aggregates
3. Updates kit files in `.bootstrap/config/kits/`

---

## Versioning

Constructor Studio has **two independent version tracks**.

### Version Locations

| File | Example | What it versions | When to bump |
|------|---------|------------------|--------------|
| `skills/studio/scripts/studio/__init__.py` | `vX.Y.Z-beta` | **Skill engine** — the core validation/generation logic | Any change to skill engine code |
| `pyproject.toml` (`version`) | `X.Y.Z-beta` | **CLI proxy** — installed via `pipx` | Changes to proxy routing, caching, or resolution |

### Releasing a New Version

1. **Create a release branch** from `main`:
   ```bash
   git checkout main && git pull --rebase
   git checkout -b vX.Y.Z-beta
   ```

2. **Bump the skill engine version** in `skills/studio/scripts/studio/__init__.py`:
   ```python
   __version__ = "vX.Y.Z-beta"
   ```

3. **If proxy changed**, bump version in `pyproject.toml`:
   ```toml
   # pyproject.toml
   version = "X.Y.Z-beta"
   ```

4. **Sync bootstrap**:
   ```bash
   make update
   ```

5. **Verify** everything passes:
   ```bash
   make test
   make validate
   make self-check
   ```

6. **Tag and release** after merge to `main`:
   ```bash
   git tag vX.Y.Z-beta
   git push origin vX.Y.Z-beta
   ```

---

## Branch and Release Workflow

```
main                          # Stable, all CI must pass
└── vX.Y.Z-beta               # Feature/release branch
```

- Branch from `main` for each version
- All work happens on the version branch
- Merge to `main` via PR after CI passes
- Tag `main` after merge

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

`make ci` runs the **exact same workflow** as GitHub Actions, locally via [act](https://github.com/nektos/act) in Docker. Single source of truth — `.github/workflows/ci.yml`.

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
| `make check-versions` | Check version consistency across components | Yes |
| `make spec-coverage` | Check spec coverage (≥80% overall, ≥70% per file) | Yes |
| `make pylint` | Pylint static analysis (staged rollout) | Yes |
| `make vulture` | Dead code scan (report only) | — |
| `make vulture-ci` | Dead code scan (fails on findings) | Yes |
| `make install` | Install pytest + pytest-cov via pipx | — |
| `make install-proxy` | Reinstall `cfs`/`constructor-studio` CLI from local source | — |
| `make update` | Sync `.bootstrap/` from local source | — |
| `make clean` | Remove `__pycache__`, `.pyc`, `.pytest_cache` | — |

### GitHub Actions

CI runs on every push to `main` and every PR targeting `main`. Nine parallel jobs:

1. **Test** — `make test` on Python 3.11, 3.12, 3.13, 3.14
2. **Coverage** — `make test-coverage` on Python 3.14 (≥90% gate)
3. **SonarQube** — SonarCloud scan with coverage reporting (requires `SONAR_TOKEN` secret)
4. **Pylint** — `make pylint` static analysis (staged rollout — currently 12 checks enabled)
5. **Vulture** — `make vulture-ci` dead code scan
6. **Versions** — `make check-versions` (proxy sync, bootstrap sync)
7. **Spec Coverage** — `make spec-coverage` (≥80% overall, ≥70% per file)
8. **Validate** — `make validate` + `make self-check` on Python 3.11–3.14
9. **Validate Kits** — `make validate-kits` on Python 3.11–3.14

All jobs must pass before merge.

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
2. If adding new CDSL entries, run `cfs toc <file>` to regenerate the table of contents
3. If adding `@cpt-*` code markers, run `cfs validate` to verify traceability (138/138 coverage)
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
