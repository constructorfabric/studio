"""Tests for Manifest V2 schema parsing.

Covers: ManifestV2, AgentEntry, SkillEntry, WorkflowEntry, RuleEntry,
ManifestLayer, ManifestLayerState, and parse_manifest_v2().
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from studio.utils.manifest import (
    AgentEntry,
    ComponentEntry,
    ManifestLayer,
    ManifestLayerState,
    ManifestV2,
    RuleEntry,
    SkillEntry,
    WorkflowEntry,
    _parse_base_fields,
    load_manifest,
    parse_manifest_v2,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_V2_FULL = """\
[manifest]
version = "2.0"
includes = ["../parent/manifest.toml"]

[[agents]]
id = "reviewer"
description = "Code reviewer agent"
prompt_file = "prompts/reviewer.md"
mode = "readonly"
isolation = true
model = "opus"
tools = ["Read", "Grep"]
color = "#FF0000"
memory_dir = ".memory/reviewer"
agents = ["claude"]
role = "analyze"
target = "codebase"
provider = "openai"
reasoning_effort = "high"
context_window = "max"

[[skills]]
id = "deploy"
description = "Deployment skill"
prompt_file = "skills/deploy.md"

[[workflows]]
id = "release"
description = "Release workflow"
prompt_file = "workflows/release.md"

[[rules]]
id = "no-console-log"
description = "Ban console.log in production"
source = "rules/no-console-log.md"

[[hooks]]
id = "pre-commit"
command = "lint"

[[permissions]]
id = "fs-read"
scope = "project"
"""

_V1_COMPAT = """\
[manifest]
version = "1.0"
root = "{cf-studio-path}/config/kits/test"

[[resources]]
id = "agents_md"
source = "agents/AGENTS.md"
default_path = "config/AGENTS.md"
type = "file"
description = "Agent definitions"
user_modifiable = true
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_parse_v2_full_manifest():
    """parse_manifest_v2 parses v2.0 with all component sections."""
    with TemporaryDirectory() as tmpdir:
        mpath = Path(tmpdir) / "manifest.toml"
        mpath.write_text(_V2_FULL)

        result = parse_manifest_v2(mpath)

        assert isinstance(result, ManifestV2)
        assert result.version == "2.0"
        assert result.includes == ["../parent/manifest.toml"]

        # Agents
        assert len(result.agents) == 1
        agent = result.agents[0]
        assert isinstance(agent, AgentEntry)
        assert agent.id == "reviewer"
        assert agent.mode == "readonly"
        assert agent.isolation is True
        assert agent.model == "opus"
        assert agent.tools == ["Read", "Grep"]
        assert agent.disallowed_tools == []
        assert agent.color == "#FF0000"
        assert agent.memory_dir == ".memory/reviewer"
        assert agent.agents == ["claude"]
        assert agent.role == "analyze"
        assert agent.target == "codebase"
        assert agent.provider == "openai"
        assert agent.reasoning_effort == "high"
        assert agent.context_window == "max"

        # Skills
        assert len(result.skills) == 1
        assert isinstance(result.skills[0], SkillEntry)
        assert result.skills[0].id == "deploy"

        # Workflows
        assert len(result.workflows) == 1
        assert isinstance(result.workflows[0], WorkflowEntry)
        assert result.workflows[0].id == "release"

        # Rules
        assert len(result.rules) == 1
        assert isinstance(result.rules[0], RuleEntry)
        assert result.rules[0].id == "no-console-log"


def test_load_manifest_accepts_numeric_v2_version_for_compatibility():
    """load_manifest keeps accepting numeric TOML versions accepted by the parser."""
    with TemporaryDirectory() as tmpdir:
        kit = Path(tmpdir)
        mpath = kit / "manifest.toml"
        mpath.write_text(
            """\
[manifest]
version = 2.0

[[agents]]
id = "reviewer"
description = "Code reviewer agent"
""",
            encoding="utf-8",
        )

        result = load_manifest(kit)

        assert isinstance(result, ManifestV2)
        assert result.version == "2.0"
        assert result.agents[0].id == "reviewer"


def test_parse_v2_agent_defaults_extended_selector_fields():
    """Omitted extended agent selector fields use generator-compatible defaults."""
    with TemporaryDirectory() as tmpdir:
        mpath = Path(tmpdir) / "manifest.toml"
        mpath.write_text(
            """\
[manifest]
version = "2.0"

[[agents]]
id = "reviewer"
description = "Code reviewer agent"
"""
        )

        result = parse_manifest_v2(mpath)
        agent = result.agents[0]

        assert agent.role == "any"
        assert agent.target == "any"
        assert agent.provider == "anthropic"
        assert agent.reasoning_effort is None
        assert agent.context_window is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mode", "bogus"),
        ("role", "review"),
        ("target", "docs"),
        ("provider", "ollama"),
        ("reasoning_effort", "ultra"),
        ("context_window", "huge"),
        ("model", "cf:tier:invalid-tier"),
    ],
)
def test_parse_v2_rejects_invalid_agent_selector_fields(field, value):
    """V2 manifests must reject invalid generated-agent selector values."""
    with TemporaryDirectory() as tmpdir:
        mpath = Path(tmpdir) / "manifest.toml"
        mpath.write_text(
            f"""\
[manifest]
version = "2.0"

[[agents]]
id = "reviewer"
description = "Code reviewer agent"
{field} = "{value}"
"""
        )

        with pytest.raises(ValueError, match=field):
            parse_manifest_v2(mpath)


def test_parse_v1_backward_compatibility():
    """parse_manifest_v2 wraps v1.0 manifests as ManifestV2 with resources only."""
    with TemporaryDirectory() as tmpdir:
        mpath = Path(tmpdir) / "manifest.toml"
        mpath.write_text(_V1_COMPAT)

        result = parse_manifest_v2(mpath)

        assert isinstance(result, ManifestV2)
        assert result.version == "1.0"
        assert result.agents == []
        assert result.skills == []
        assert result.workflows == []
        assert result.rules == []
        assert len(result.resources) == 1
        assert result.resources[0].id == "agents_md"
        assert result.resources[0].type == "file"


def test_v1_load_manifest_still_works():
    """Existing load_manifest() function continues to work for v1 manifests."""
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        mpath = root / "manifest.toml"
        mpath.write_text(_V1_COMPAT)

        result = load_manifest(root)

        assert result is not None
        assert result.version == "1.0"
        assert len(result.resources) == 1
        assert result.resources[0].id == "agents_md"


def test_extended_agent_schema_fields():
    """AgentEntry supports tools, color, memory_dir, model, disallowed_tools."""
    toml_content = """\
[manifest]
version = "2.0"

[[agents]]
id = "helper"
description = "Helper agent"
model = "fast"
disallowed_tools = ["Bash", "Write"]
color = "blue"
memory_dir = ".mem/helper"
"""
    with TemporaryDirectory() as tmpdir:
        mpath = Path(tmpdir) / "manifest.toml"
        mpath.write_text(toml_content)

        result = parse_manifest_v2(mpath)

        agent = result.agents[0]
        assert agent.model == "fast"
        assert agent.disallowed_tools == ["Bash", "Write"]
        assert agent.tools == []
        assert agent.color == "blue"
        assert agent.memory_dir == ".mem/helper"


def test_tools_disallowed_tools_mutual_exclusivity():
    """parse_manifest_v2 raises ValueError when both tools and disallowed_tools set."""
    toml_content = """\
[manifest]
version = "2.0"

[[agents]]
id = "bad-agent"
tools = ["Read"]
disallowed_tools = ["Write"]
"""
    with TemporaryDirectory() as tmpdir:
        mpath = Path(tmpdir) / "manifest.toml"
        mpath.write_text(toml_content)

        with pytest.raises(ValueError, match="mutually exclusive") as exc_info:
            parse_manifest_v2(mpath)
        assert "bad-agent" in str(exc_info.value)


def test_hooks_and_permissions_accepted_and_ignored():
    """parse_manifest_v2 accepts [[hooks]] and [[permissions]] without error."""
    with TemporaryDirectory() as tmpdir:
        mpath = Path(tmpdir) / "manifest.toml"
        mpath.write_text(_V2_FULL)

        result = parse_manifest_v2(mpath)

        # No hooks or permissions fields on ManifestV2 — they are silently ignored
        assert not hasattr(result, "hooks")
        assert not hasattr(result, "permissions")
        # Parsing succeeded without error
        assert result.version == "2.0"


def test_parse_error_missing_version():
    """parse_manifest_v2 raises ValueError with path info on missing version."""
    toml_content = """\
[manifest]
"""
    with TemporaryDirectory() as tmpdir:
        mpath = Path(tmpdir) / "manifest.toml"
        mpath.write_text(toml_content)

        with pytest.raises(ValueError, match="version") as exc_info:
            parse_manifest_v2(mpath)
        assert str(mpath) in str(exc_info.value)


def test_parse_error_invalid_toml():
    """parse_manifest_v2 raises ValueError on invalid TOML content."""
    with TemporaryDirectory() as tmpdir:
        mpath = Path(tmpdir) / "manifest.toml"
        mpath.write_text("this is not valid toml [[[")

        with pytest.raises(ValueError, match="TOML parse error"):
            parse_manifest_v2(mpath)


def test_parse_error_file_not_found():
    """parse_manifest_v2 raises ValueError when file does not exist."""
    with pytest.raises(ValueError, match="not found"):
        parse_manifest_v2(Path("/nonexistent/manifest.toml"))


def test_parse_error_unsupported_version():
    """parse_manifest_v2 raises ValueError for unsupported version."""
    toml_content = """\
[manifest]
version = "3.0"
"""
    with TemporaryDirectory() as tmpdir:
        mpath = Path(tmpdir) / "manifest.toml"
        mpath.write_text(toml_content)

        with pytest.raises(ValueError, match="unsupported") as exc_info:
            parse_manifest_v2(mpath)
        assert "3.0" in str(exc_info.value)


def test_parse_error_invalid_agent_id():
    """parse_manifest_v2 raises ValueError for invalid agent id."""
    toml_content = """\
[manifest]
version = "2.0"

[[agents]]
id = "Bad-Agent!"
"""
    with TemporaryDirectory() as tmpdir:
        mpath = Path(tmpdir) / "manifest.toml"
        mpath.write_text(toml_content)

        with pytest.raises(ValueError, match="Bad-Agent!"):
            parse_manifest_v2(mpath)


def test_manifest_layer_state_enum():
    """ManifestLayerState enum has all expected values."""
    assert ManifestLayerState.UNDISCOVERED.value == "UNDISCOVERED"
    assert ManifestLayerState.LOADED.value == "LOADED"
    assert ManifestLayerState.PARSE_ERROR.value == "PARSE_ERROR"
    assert ManifestLayerState.INCLUDE_ERROR.value == "INCLUDE_ERROR"
    assert len(ManifestLayerState) == 4  # update if a new state is added


def test_manifest_layer_dataclass():
    """ManifestLayer holds scope, path, manifest, and state."""
    layer = ManifestLayer(
        scope="project",
        path=Path("/some/path"),
        manifest=None,
        state=ManifestLayerState.UNDISCOVERED,
    )
    assert layer.scope == "project"
    assert layer.path == Path("/some/path")
    assert layer.manifest is None
    assert layer.state == ManifestLayerState.UNDISCOVERED


def test_v2_empty_component_sections():
    """parse_manifest_v2 handles v2.0 with no component sections."""
    toml_content = """\
[manifest]
version = "2.0"
"""
    with TemporaryDirectory() as tmpdir:
        mpath = Path(tmpdir) / "manifest.toml"
        mpath.write_text(toml_content)

        result = parse_manifest_v2(mpath)

        assert result.version == "2.0"
        assert result.agents == []
        assert result.skills == []
        assert result.workflows == []
        assert result.rules == []
        assert result.includes == []


def test_component_entry_inheritance():
    """AgentEntry, SkillEntry, WorkflowEntry, RuleEntry all inherit ComponentEntry."""
    assert issubclass(AgentEntry, ComponentEntry)
    assert issubclass(SkillEntry, ComponentEntry)
    assert issubclass(WorkflowEntry, ComponentEntry)
    assert issubclass(RuleEntry, ComponentEntry)


# ---------------------------------------------------------------------------
# _parse_base_fields — append_file support
# ---------------------------------------------------------------------------


class TestParseBaseFieldsAppendFile:
    """Cover append_file branch in _parse_base_fields (lines ~271-290)."""

    def test_append_file_reads_content_relative_to_git_root(self):
        """append_file resolves relative to nearest .git ancestor and reads content."""
        with TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            manifest_dir = repo / "cypilot" / "config"
            manifest_dir.mkdir(parents=True)
            manifest_path = manifest_dir / "manifest.toml"
            manifest_path.write_text("[manifest]\n", encoding="utf-8")
            extra = repo / "extra.md"
            extra.write_text("Appended content", encoding="utf-8")

            raw = {"id": "test", "append_file": "extra.md"}
            result = _parse_base_fields(raw, manifest_path=manifest_path)
            assert result["append"] == "Appended content"

    def test_append_file_reads_content_with_git_worktree_file(self):
        """append_file resolves relative to nearest .git file (worktree case)."""
        with TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / ".git").write_text("gitdir: /some/path/.git/worktrees/foo", encoding="utf-8")
            manifest_dir = repo / "cypilot" / "config"
            manifest_dir.mkdir(parents=True)
            manifest_path = manifest_dir / "manifest.toml"
            manifest_path.write_text("[manifest]\n", encoding="utf-8")
            extra = repo / "extra.md"
            extra.write_text("Worktree appended content", encoding="utf-8")

            raw = {"id": "test", "append_file": "extra.md"}
            result = _parse_base_fields(raw, manifest_path=manifest_path)
            assert result["append"] == "Worktree appended content"

    def test_append_file_prefers_active_worktree_checkout_over_main_repo(self):
        """append_file in a real worktree reads from that checkout, not the shared repo."""
        with TemporaryDirectory() as tmp:
            main = Path(tmp) / "main"
            main.mkdir()
            gitdir = main / ".git" / "worktrees" / "feature"
            gitdir.mkdir(parents=True)
            (main / "extra.md").write_text("stale main content", encoding="utf-8")

            worktree = Path(tmp) / "feature"
            worktree.mkdir()
            (worktree / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
            (worktree / "extra.md").write_text("active worktree content", encoding="utf-8")

            manifest_dir = worktree / "cypilot" / "config"
            manifest_dir.mkdir(parents=True)
            manifest_path = manifest_dir / "manifest.toml"
            manifest_path.write_text("[manifest]\n", encoding="utf-8")

            raw = {"id": "test", "append_file": "extra.md"}
            result = _parse_base_fields(raw, manifest_path=manifest_path)
            assert result["append"] == "active worktree content"

    def test_append_and_append_file_mutually_exclusive(self):
        """Supplying both append and append_file raises ValueError."""

        raw = {"id": "test", "append": "inline", "append_file": "extra.md"}
        with pytest.raises(ValueError, match="mutually exclusive"):
            _parse_base_fields(raw, manifest_path=Path("/dummy"))

    def test_append_file_missing_target_raises(self):
        """append_file pointing to non-existent file raises ValueError."""

        with TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            manifest_path = repo / "manifest.toml"
            manifest_path.write_text("[manifest]\n", encoding="utf-8")

            raw = {"id": "test", "append_file": "nonexistent.md"}
            with pytest.raises(ValueError, match="not found"):
                _parse_base_fields(raw, manifest_path=manifest_path)

    def test_append_file_without_manifest_path_raises(self):
        """append_file without manifest_path context raises ValueError."""

        raw = {"id": "test", "append_file": "extra.md"}
        with pytest.raises(ValueError, match="requires manifest_path"):
            _parse_base_fields(raw, manifest_path=None)

    def test_append_file_non_string_raises(self):
        """append_file that is not a string raises ValueError."""

        raw = {"id": "test", "append_file": 42}
        with pytest.raises(ValueError, match="must be a string"):
            _parse_base_fields(raw, manifest_path=Path("/dummy"))

    def test_append_file_absolute_path_rejected(self):
        """append_file with absolute path is rejected."""

        with TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            manifest_path = repo / "manifest.toml"
            manifest_path.write_text("[manifest]\n", encoding="utf-8")

            raw = {"id": "test", "append_file": "/etc/passwd"}
            with pytest.raises(ValueError, match="must be a relative path"):
                _parse_base_fields(raw, manifest_path=manifest_path)

    def test_append_file_traversal_rejected(self):
        """append_file that escapes repo root via ../ is rejected."""

        with TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            # Create a file outside the repo to prove it can't be read
            secret = Path(tmp) / "secret.md"
            secret.write_text("secret", encoding="utf-8")
            manifest_path = repo / "manifest.toml"
            manifest_path.write_text("[manifest]\n", encoding="utf-8")

            raw = {"id": "test", "append_file": "../secret.md"}
            with pytest.raises(ValueError, match="escapes repo root"):
                _parse_base_fields(raw, manifest_path=manifest_path)

    def test_append_file_no_git_ancestor_rejected(self):
        """append_file with no .git ancestor raises clear error."""

        with TemporaryDirectory() as tmp:
            # No .git anywhere — manifest at filesystem leaf
            deep = Path(tmp) / "a" / "b" / "c"
            deep.mkdir(parents=True)
            manifest_path = deep / "manifest.toml"
            manifest_path.write_text("[manifest]\n", encoding="utf-8")

            raw = {"id": "test", "append_file": "notes.md"}
            with pytest.raises(ValueError, match=r"no \.git ancestor"):
                _parse_base_fields(raw, manifest_path=manifest_path)


# ---------------------------------------------------------------------------
# V1 / V2 resource id character set
# ---------------------------------------------------------------------------


def test_v2_resource_id_allows_hyphens():
    """V2 manifests accept [[resources]] entries with hyphenated ids.

    The v2 component-id regex is ^[a-z][a-z0-9_-]*$ (hyphens allowed).
    _parse_resources() is shared but does not validate ids via
    _validate_component_id, so a hyphenated resource id must not raise.
    """
    toml_content = """\
[manifest]
version = "2.0"

[[resources]]
id = "my-resource"
source = "some/path.md"
default_path = "out/path.md"
type = "file"
description = "Hyphenated resource id"
"""
    with TemporaryDirectory() as tmpdir:
        mpath = Path(tmpdir) / "manifest.toml"
        mpath.write_text(toml_content)
        # Must not raise — hyphen is valid in v2 resource ids.
        result = parse_manifest_v2(mpath)
        assert result.version == "2.0"
        assert len(result.resources) == 1
        assert result.resources[0].id == "my-resource"


def test_v1_resource_id_rejects_hyphens():
    """V1 manifests reject [[resources]] entries with hyphens in the id.

    The v1 schema validator uses _ID_CHARS = lowercase + digits + '_' (no
    hyphen), matching ^[a-z][a-z0-9_]*$.  A hyphenated id must cause
    load_manifest to raise ValueError.
    """
    toml_content = """\
[manifest]
version = "1.0"
root = "{cf-studio-path}/config/kits/test"

[[resources]]
id = "my-resource"
source = "some/path.md"
default_path = "out/path.md"
type = "file"
description = "Hyphenated resource id"
"""
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        mpath = root / "manifest.toml"
        mpath.write_text(toml_content)
        # Must raise ValueError because hyphens are not in _ID_CHARS for v1.
        with pytest.raises(ValueError):
            load_manifest(root)
