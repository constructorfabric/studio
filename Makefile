# @cpt-algo:cpt-studio-spec-init-structure-change-infrastructure:p1
.PHONY: test test-verbose test-quick test-coverage test-coverage-diff validate validate-examples validate-feature validate-code validate-code-feature self-check validate-kits validate-kits-sdlc vulture vulture-ci pylint install install-pipx install-proxy install-prompt-tests clean help check-pytest check-pytest-cov check-pipx check-vulture check-pylint check-versions check-prompt-tests bootstrap-init bootstrap-repair update update-local seed-cache ensure-bootstrap generate-agents spec-coverage ci lint-ci test-prompts test-prompts-view

# Detect container architecture for act (arm64 on Apple Silicon, amd64 otherwise)
UNAME_M := $(shell uname -m)
ifeq ($(UNAME_M),arm64)
  ACT_ARCH := linux/arm64
else ifeq ($(UNAME_M),aarch64)
  ACT_ARCH := linux/arm64
else
  ACT_ARCH := linux/amd64
endif
ACT_FLAGS ?= --container-architecture $(ACT_ARCH)

PYTHON ?= python3
PIPX ?= pipx
CFS ?= cfs
BOOTSTRAP_STUDIO ?= .bootstrap/.core/skills/studio/scripts/studio.py
SOURCE_STUDIO ?= skills/studio/scripts/studio.py
PYTEST_PIPX ?= $(PIPX) run --spec pytest pytest
PYTEST_PIPX_COV ?= $(PIPX) run --spec pytest-cov pytest
VULTURE_PIPX ?= $(PIPX) run --spec vulture vulture
PYLINT_PIPX ?= $(PIPX) run --spec pylint pylint
DIFF_COVER_PIPX ?= $(PIPX) run --spec diff-cover diff-cover
DIFF_COVER_COMPARE ?= main
DIFF_COVER_MIN ?= 80
VULTURE_MIN_CONF ?= 0
PYLINT_TARGETS ?= src/studio_proxy skills/studio/scripts/studio

# Prompt-tests (cf-skill UX pilot, tests/prompts/cf-ux/)
PROMPTFOO_VERSION ?= latest
PROMPTFOO ?= npx -y promptfoo@$(PROMPTFOO_VERSION)
PROMPT_TESTS_DIR ?= tests/prompts/cf-ux
PROMPT_TESTS_TIMEOUT_MS ?= 900000

# Default target
help:
	@echo "Constructor Studio Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  make test                          - Run all tests"
	@echo "  make test-verbose                  - Run tests with verbose output"
	@echo "  make test-quick                    - Run fast tests only (skip slow integration tests)"
	@echo "  make test-coverage                 - Run tests with coverage report"
	@echo "  make test-coverage-diff            - Coverage for diff vs main (≥$(DIFF_COVER_MIN)%)"
	@echo "  make validate-examples             - Validate requirements examples under examples/requirements"
	@echo "  make validate                      - Validate core methodology spec"
	@echo "  make self-check                    - Validate SDLC examples against their templates"
	@echo "  make validate-kits                 - Validate all registered kits"
	@echo "  make validate-kits-sdlc            - Validate kits/sdlc kit by path"
	@echo "  make check-versions                - Check version consistency across components"
	@echo "  make spec-coverage                 - Check spec coverage (≥90% overall, ≥60% per file)"
	@echo "  make vulture                       - Scan python code for dead code (report only, does not fail)"
	@echo "  make vulture-ci                    - Scan python code for dead code (fails if findings)"
	@echo "  make ci                            - Run full CI pipeline locally"
	@echo "  make lint-ci                       - Lint GitHub Actions workflow files"
	@echo "  make install                       - Install Python dependencies"
	@echo "  make install-proxy                 - Reinstall cfs proxy from local source"
	@echo "  make install-prompt-tests          - Pre-cache promptfoo for cf-skill UX tests"
	@echo "  make test-prompts                  - Run cf-skill UX pilot (claude + codex)"
	@echo "  make test-prompts-view             - Open promptfoo HTML report for last run"
	@echo "  make bootstrap-init                - Initialize .bootstrap from local source"
	@echo "  make bootstrap-repair              - Repair generated .bootstrap runtime files"
	@echo "  make update-local                  - Update .bootstrap from local source"
	@echo "  make update                        - Alias for update-local"
	@echo "  make generate-agents               - Generate all local agent integrations"
	@echo "  make clean                         - Remove Python cache files"
	@echo "  make help                          - Show this help message"

# Run all tests
check-pipx:
	@command -v $(PIPX) >/dev/null 2>&1 || { \
		echo ""; \
		echo "ERROR: pipx not found"; \
		echo ""; \
		echo "Install it with:"; \
		echo "  brew install pipx"; \
		echo "  pipx ensurepath"; \
		echo ""; \
		exit 1; \
	}

check-pytest: check-pipx
	@$(PYTEST_PIPX) --version >/dev/null 2>&1 || { \
		echo ""; \
		echo "ERROR: pytest is not runnable via pipx"; \
		echo ""; \
		echo "Install it with:"; \
		echo "  make install"; \
		echo ""; \
		exit 1; \
	}

check-pytest-cov: check-pytest
	@$(PYTEST_PIPX_COV) --help 2>/dev/null | grep -q -- '--cov' || { \
		echo ""; \
		echo "ERROR: pytest-cov not available (missing --cov option)"; \
		echo ""; \
		echo "Install it with:"; \
		echo "  make install"; \
		echo ""; \
		exit 1; \
	}

check-vulture: check-pipx
	@$(VULTURE_PIPX) --version >/dev/null 2>&1 || { \
		echo ""; \
		echo "ERROR: vulture is not runnable via pipx"; \
		echo ""; \
		echo "Install it with:"; \
		echo "  pipx install vulture"; \
		echo "or just run: make vulture (pipx run will download it)"; \
		echo ""; \
		exit 1; \
	}

check-pylint: check-pipx
	@$(PYLINT_PIPX) --version >/dev/null 2>&1 || { \
		echo ""; \
		echo "ERROR: pylint is not runnable via pipx"; \
		echo ""; \
		echo "Install it with:"; \
		echo "  pipx install pylint"; \
		echo "or just run: make pylint (pipx run will download it)"; \
		echo ""; \
		exit 1; \
	}

test: check-pytest
	@echo "Running Constructor Studio tests with pipx..."
	$(PYTEST_PIPX) tests/ -v --tb=short

# Run tests with verbose output
test-verbose: check-pytest
	@echo "Running Constructor Studio tests (verbose) with pipx..."
	$(PYTEST_PIPX) tests/ -vv

# Run quick tests only
test-quick: check-pytest
	@echo "Running quick tests with pipx..."
	$(PYTEST_PIPX) tests/ -v -m "not slow"

# Run tests with coverage
test-coverage: check-pytest-cov
	@echo "Running tests with coverage..."
	$(PYTEST_PIPX_COV) tests/ \
		--cov=skills/studio/scripts/studio \
		--cov-report=term-missing \
		--cov-report=json:coverage.json \
		--cov-report=xml:coverage.xml \
		--cov-report=html \
		-v --tb=short
	@$(PYTHON) scripts/check_coverage.py coverage.json --root skills/studio/scripts/studio --min 90 --exclude vendor/
	@echo ""
	@echo "Coverage report generated:"
	@echo "  HTML: htmlcov/index.html"
	@echo "  XML: coverage.xml"
	@echo "  Open with: open htmlcov/index.html"
	@if git rev-parse --verify $(DIFF_COVER_COMPARE) >/dev/null 2>&1 && \
	    ! git diff --quiet $(DIFF_COVER_COMPARE) -- 2>/dev/null; then \
		echo ""; \
		echo "Checking diff coverage vs $(DIFF_COVER_COMPARE) (min $(DIFF_COVER_MIN)%)..."; \
		$(DIFF_COVER_PIPX) coverage.xml \
			--compare-branch=$(DIFF_COVER_COMPARE) \
			--fail-under=$(DIFF_COVER_MIN) \
			--diff-range-notation='..' \
			--show-uncovered; \
	else \
		echo ""; \
		echo "Skipping diff coverage (no diff vs $(DIFF_COVER_COMPARE) or branch not found)"; \
	fi

# Run diff-coverage standalone (reuses existing coverage.xml)
test-coverage-diff:
	@if [ ! -f coverage.xml ]; then \
		echo "ERROR: coverage.xml not found. Run 'make test-coverage' first."; \
		exit 1; \
	fi
	@if git rev-parse --verify $(DIFF_COVER_COMPARE) >/dev/null 2>&1 && \
	    ! git diff --quiet $(DIFF_COVER_COMPARE) -- 2>/dev/null; then \
		echo "Checking diff coverage vs $(DIFF_COVER_COMPARE) (min $(DIFF_COVER_MIN)%)..."; \
		$(DIFF_COVER_PIPX) coverage.xml \
			--compare-branch=$(DIFF_COVER_COMPARE) \
			--fail-under=$(DIFF_COVER_MIN) \
			--diff-range-notation='..' \
			--show-uncovered; \
	else \
		echo "Skipping diff coverage (no diff vs $(DIFF_COVER_COMPARE) or branch not found)"; \
	fi

vulture: check-vulture
	@echo "Running vulture dead-code scan (excluding tests by scanning only skills/studio/scripts/studio)..."
	@echo "Tip: raise/lower VULTURE_MIN_CONF to reduce false positives (current: $(VULTURE_MIN_CONF))."
	@$(VULTURE_PIPX) skills/studio/scripts/studio vulture_whitelist.py --exclude '*/vendor/*' --min-confidence $(VULTURE_MIN_CONF) || true

vulture-ci: check-vulture
	@echo "Running vulture dead-code scan (CI mode, fails if findings)..."
	$(VULTURE_PIPX) skills/studio/scripts/studio vulture_whitelist.py --exclude '*/vendor/*' --min-confidence $(VULTURE_MIN_CONF)

pylint: check-pylint
	@echo "Running pylint..."
	PYTHONPATH=src:skills/studio/scripts $(PYLINT_PIPX) $(PYLINT_TARGETS)

# Spec coverage check (Constructor Studio system only)
spec-coverage: ensure-bootstrap
	@echo "Checking spec coverage (Constructor Studio system)..."
	$(PYTHON) $(BOOTSTRAP_STUDIO) spec-coverage --system studio --min-coverage 90 --min-file-coverage 60 --min-granularity 0.44

# Check version consistency
check-versions:
	@$(PYTHON) scripts/check_versions.py

# Initialize .bootstrap from local source. Repeat runs repair generated runtime files.
bootstrap-init: seed-cache
	@echo "Initializing .bootstrap from local source..."
	$(PYTHON) $(SOURCE_STUDIO) init --project-root . --install-dir .bootstrap --kit-tracking tracked --kit-tracking sdlc=ignored --yes

# Repair generated .bootstrap runtime files without updating tracked kit files.
bootstrap-repair: seed-cache
	@echo "Repairing generated .bootstrap runtime files from local source..."
	$(PYTHON) $(SOURCE_STUDIO) init --project-root . --install-dir .bootstrap --kit-tracking tracked --kit-tracking sdlc=ignored --yes

# Backward-compatible alias: update means local self-hosted update in this repo.
update: update-local

# Update .bootstrap from local source. Kit files are skipped by default by cfs update.
update-local: seed-cache
	@if [ ! -f "$(BOOTSTRAP_STUDIO)" ]; then \
		$(PYTHON) $(SOURCE_STUDIO) init --project-root . --install-dir .bootstrap --kit-tracking tracked --kit-tracking sdlc=ignored --yes; \
	else \
		$(PYTHON) $(SOURCE_STUDIO) update --project-root . -y; \
	fi

seed-cache:
	@echo "Seeding Constructor Studio cache from tracked source..."
	PYTHONPATH=src $(PYTHON) scripts/seed_local_cache.py .

ensure-bootstrap:
	@if [ ! -f "$(BOOTSTRAP_STUDIO)" ]; then \
		echo "Bootstrap studio entrypoint missing; running make bootstrap-init..."; \
		$(MAKE) bootstrap-init; \
	fi

generate-agents: ensure-bootstrap
	@echo "Generating all Constructor Studio agent integrations..."
	$(PYTHON) $(BOOTSTRAP_STUDIO) generate-agents -y

# Validate core methodology spec
validate: ensure-bootstrap
	$(CFS) validate

# Validate SDLC examples against templates
self-check: ensure-bootstrap
	@echo "Running self-check: validating SDLC examples against templates..."
	$(CFS) self-check

# Validate all registered kits
validate-kits: ensure-bootstrap
	@echo "Validating all registered kits..."
	$(CFS) validate-kits

# Validate kits/sdlc kit by path
validate-kits-sdlc: ensure-bootstrap
	@echo "Validating kits/sdlc..."
	$(CFS) validate-kits kits/sdlc

# Install Python dependencies
install-pipx: check-pipx
	@echo "Installing pytest + pytest-cov via pipx..."
	@$(PIPX) install pytest >/dev/null 2>&1 || $(PIPX) upgrade pytest
	@$(PIPX) inject pytest pytest-cov
	@echo "Done. If pytest is not found, run: pipx ensurepath (then restart your shell)."

install: install-pipx

# Reinstall cfs/constructor-studio proxy from local source
install-proxy: check-pipx
	$(PIPX) install --force .

# cf-skill UX prompt-tests (tests/prompts/cf-ux/) -----------------------------
#
# Dependencies the tests need at runtime:
#   - node / npx        (for promptfoo)
#   - claude CLI        (provider + grader)
#   - codex  CLI        (provider)
#   - cfs    CLI        (sandbox init via the local studio engine — already
#                        installed by `make install-proxy`)
#
# Test runs spin up fresh `cfs init`-ed tmpdir sandboxes and consume real
# Claude / Codex API tokens. Defaults to cheap models (Haiku 4.5, gpt-5.4-mini
# at low effort, 128k context); override via CF_UX_* env vars — see
# tests/prompts/cf-ux/README.md.
check-prompt-tests:
	@command -v node >/dev/null 2>&1 || { \
		echo ""; \
		echo "ERROR: node not found (needed for npx promptfoo)"; \
		echo "  Install via nvm:  https://github.com/nvm-sh/nvm"; \
		echo ""; \
		exit 1; \
	}
	@command -v claude >/dev/null 2>&1 || { \
		echo ""; \
		echo "ERROR: claude CLI not found"; \
		echo "  Install:  https://docs.claude.com/en/docs/claude-code"; \
		echo ""; \
		exit 1; \
	}
	@command -v codex >/dev/null 2>&1 || { \
		echo ""; \
		echo "ERROR: codex CLI not found"; \
		echo "  Install:  https://developers.openai.com/codex/cli"; \
		echo ""; \
		exit 1; \
	}
	@command -v $(CFS) >/dev/null 2>&1 || { \
		echo ""; \
		echo "ERROR: cfs not found — run \`make install-proxy\` first"; \
		echo ""; \
		exit 1; \
	}

install-prompt-tests: check-prompt-tests
	@echo "Pre-caching promptfoo@$(PROMPTFOO_VERSION) via npx..."
	@$(PROMPTFOO) --version >/dev/null
	@echo "Done. Run prompt tests with:  make test-prompts"

test-prompts: check-prompt-tests
	@echo "Running cf-skill UX pilot in $(PROMPT_TESTS_DIR)..."
	@cd $(PROMPT_TESTS_DIR) && \
		REQUEST_TIMEOUT_MS=$(PROMPT_TESTS_TIMEOUT_MS) $(PROMPTFOO) eval --no-cache

test-prompts-view:
	@cd $(PROMPT_TESTS_DIR) && $(PROMPTFOO) view
# --------------------------------------------------------------------------

# Lint CI workflow files
lint-ci:
	@echo "Linting GitHub Actions workflows..."
	actionlint

# Run CI via act in Docker (mirrors .github/workflows/ci.yml exactly)
# Runs jobs sequentially — stops on first failure.
# Auto-detects arm64/amd64. Override: make ci ACT_FLAGS="--your-flags"
ci: lint-ci
	@for job in $$(act push --list $(ACT_FLAGS) 2>/dev/null | tail -n +2 | awk '{print $$2}' | grep -v '^sonarqube$$'); do \
		echo "▶ Running job: $$job"; \
		act push -j $$job $(ACT_FLAGS) || exit 1; \
	done
	@echo ""
	@echo "✓ All CI jobs passed."

# Clean Python cache
clean:
	@echo "Cleaning Python cache files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean complete"
