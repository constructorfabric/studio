"""Tests for codebase.py - Constructor Studio code traceability marker parsing."""
import os
import pytest
from pathlib import Path
from textwrap import dedent

from studio.utils import document
from studio.utils import error_codes as EC
from studio.utils.codebase import (
    CodeFile,
    ScopeMarker,
    BlockMarker,
    CodeReference,
    load_code_file,
    read_code_text,
    validate_code_file,
    cross_validate_code,
    scan_registered_codebase_references,
)


class _FakeCodebaseEntry:
    def __init__(self, path, extensions):
        self.path = path
        self.extensions = extensions


class _FakeMeta:
    def __init__(self, entries):
        self._entries = entries

    def iter_all_codebase(self):
        return iter((entry, None) for entry in self._entries)

    def is_ignored(self, rel_path: str) -> bool:
        return False


class _FakeCtx:
    def __init__(self, project_root: Path, entries):
        self.project_root = project_root
        self.meta = _FakeMeta(entries)


class TestScanRegisteredCodebaseReferences:
    """Shared marker-scan helper used by both `list-ids` and `where-used` (OLE-42)."""

    def test_finds_block_marker_references(self, tmp_path: Path):
        code_dir = tmp_path / "src"
        code_dir.mkdir()
        (code_dir / "auth.py").write_text(
            dedent("""
                # @cpt-begin:cpt-myapp-feature-auth-flow-login:p1:inst-check-creds
                def login():
                    pass
                # @cpt-end:cpt-myapp-feature-auth-flow-login:p1:inst-check-creds
            """)
        )
        ctx = _FakeCtx(tmp_path, [_FakeCodebaseEntry(code_dir, [".py"])])

        hits, code_files_scanned, code_files_skipped = scan_registered_codebase_references(ctx)

        assert code_files_scanned == 1
        assert code_files_skipped == 0
        assert len(hits) == 1
        assert hits[0]["id"] == "cpt-myapp-feature-auth-flow-login"
        assert hits[0]["artifact_type"] == "CODE"
        assert hits[0]["inst"] == "check-creds"

    def test_default_ignored_directories_are_skipped_without_explicit_ignore(self, tmp_path: Path):
        code_dir = tmp_path / "src"
        code_dir.mkdir()
        vendored = code_dir / "node_modules" / "pkg"
        vendored.mkdir(parents=True)
        (vendored / "lib.py").write_text(
            "# @cpt-begin:cpt-vendored-thing:p1:inst-noop\npass\n# @cpt-end:cpt-vendored-thing:p1:inst-noop\n"
        )
        ctx = _FakeCtx(tmp_path, [_FakeCodebaseEntry(code_dir, [".py"])])

        hits, code_files_scanned, code_files_skipped = scan_registered_codebase_references(ctx)

        assert code_files_scanned == 0
        # Counted, not silent. `skipped` means "ignored, oversized, or
        # unparsable", and an excluded vendored file is the first of those --
        # reporting 0 scanned and 0 skipped would say there was nothing here
        # when in fact there was a file the policy declined to scan.
        assert code_files_skipped == 1
        assert hits == []

    def test_the_size_ceiling_applies_to_the_bytes_read_not_to_an_earlier_look(self, tmp_path: Path, monkeypatch):
        """A `stat` followed by an unbounded read trusted the measurement, so a file that
        grew between the two was read whole. The scan reads through the bounded reader:
        a file that is past the ceiling at the moment it is read is declined, whatever
        an earlier look at it said."""
        from studio.utils import codebase as codebase_module

        monkeypatch.setattr(codebase_module, "_MAX_CODE_FILE_BYTES", 40)
        code_dir = tmp_path / "src"
        code_dir.mkdir()
        big = code_dir / "big.py"
        # Valid content, so the old stat-then-read path would have *scanned* the grown
        # file rather than rejected a malformed marker; only the ceiling declines it.
        big.write_text("pass\n")
        real = codebase_module.read_code_text

        def grows_then_reads(path, **kwargs):
            with path.open("a", encoding="utf-8") as handle:
                handle.write("pass\n" * 20)
            return real(path, **kwargs)
        monkeypatch.setattr(codebase_module, "read_code_text", grows_then_reads)
        ctx = _FakeCtx(tmp_path, [_FakeCodebaseEntry(code_dir, [".py"])])

        hits, code_files_scanned, code_files_skipped = scan_registered_codebase_references(ctx)

        assert (hits, code_files_scanned, code_files_skipped) == ([], 0, 1)

    def test_oversized_file_is_skipped_not_read(self, tmp_path: Path, monkeypatch):
        from studio.utils import codebase as codebase_module

        monkeypatch.setattr(codebase_module, "_MAX_CODE_FILE_BYTES", 10)
        code_dir = tmp_path / "src"
        code_dir.mkdir()
        (code_dir / "big.py").write_text(
            "# @cpt-begin:cpt-big-thing:p1:inst-noop\npass\n# @cpt-end:cpt-big-thing:p1:inst-noop\n"
        )
        ctx = _FakeCtx(tmp_path, [_FakeCodebaseEntry(code_dir, [".py"])])

        hits, code_files_scanned, code_files_skipped = scan_registered_codebase_references(ctx)

        assert code_files_scanned == 0
        assert code_files_skipped == 1
        assert hits == []

    def test_codebase_entry_escaping_project_root_is_skipped(self, tmp_path: Path):
        outside = tmp_path.parent / f"{tmp_path.name}-outside"
        outside.mkdir(exist_ok=True)
        (outside / "escape.py").write_text(
            "# @cpt-begin:cpt-escape-thing:p1:inst-noop\npass\n# @cpt-end:cpt-escape-thing:p1:inst-noop\n"
        )
        project_root = tmp_path / "project"
        project_root.mkdir()
        try:
            rel_escape = "../" + os.path.relpath(outside, project_root).replace(os.sep, "/")
        except ValueError:
            pytest.skip("cannot construct a relative escape path on this platform")
        ctx = _FakeCtx(project_root, [_FakeCodebaseEntry(Path(rel_escape), [".py"])])

        hits, code_files_scanned, code_files_skipped = scan_registered_codebase_references(ctx)

        assert code_files_scanned == 0
        assert hits == []

    def test_entry_code_files_are_sorted_for_determinism(self, tmp_path: Path):
        from studio.utils.codebase import resolve_entry_code_files

        code_dir = tmp_path / "src"
        code_dir.mkdir()
        for name in ("zeta.py", "alpha.py", "mid.py"):
            (code_dir / name).write_text("pass\n")

        paths, excluded = resolve_entry_code_files(code_dir, [".py"], project_root=tmp_path)

        assert [p.name for p in paths] == ["alpha.py", "mid.py", "zeta.py"]
        assert excluded == 0

    def test_ignored_code_file_fails_closed_when_containment_cannot_be_established(self, tmp_path: Path):
        from studio.utils.codebase import _is_ignored_code_file

        unrelated = tmp_path.parent / f"{tmp_path.name}-unrelated" / "file.py"
        unrelated.parent.mkdir(parents=True, exist_ok=True)
        unrelated.write_text("pass\n")
        ctx = _FakeCtx(tmp_path / "project-root-does-not-exist", [])

        assert _is_ignored_code_file(unrelated, ctx) is True

    def test_scan_fans_out_to_reachable_workspace_sources(self, tmp_path: Path):
        from studio.utils.context import SourceContext, WorkspaceContext

        primary_src = tmp_path / "primary" / "src"
        primary_src.mkdir(parents=True)
        (primary_src / "primary.py").write_text(
            "# @cpt-begin:cpt-primary-thing:p1:inst-noop\npass\n# @cpt-end:cpt-primary-thing:p1:inst-noop\n"
        )
        primary_ctx = _FakeCtx(tmp_path / "primary", [_FakeCodebaseEntry(primary_src, [".py"])])

        member_root = tmp_path / "member"
        member_src = member_root / "src"
        member_src.mkdir(parents=True)
        (member_src / "member.py").write_text(
            "# @cpt-begin:cpt-member-thing:p1:inst-noop\npass\n# @cpt-end:cpt-member-thing:p1:inst-noop\n"
        )
        member_meta = _FakeMeta([_FakeCodebaseEntry(member_src, [".py"])])

        ws = WorkspaceContext(primary=primary_ctx)
        ws.sources = {
            "member": SourceContext(name="member", path=member_root, role="full", meta=member_meta),
        }

        hits, code_files_scanned, code_files_skipped = scan_registered_codebase_references(ws)

        assert code_files_scanned == 2
        ids = {h["id"] for h in hits}
        assert ids == {"cpt-primary-thing", "cpt-member-thing"}

    def test_scan_skips_unreachable_workspace_sources(self, tmp_path: Path):
        from studio.utils.context import SourceContext, WorkspaceContext

        primary_ctx = _FakeCtx(tmp_path, [])
        ws = WorkspaceContext(primary=primary_ctx)
        ws.sources = {
            "member": SourceContext(name="member", path=None, role="full", reachable=False),
        }

        hits, code_files_scanned, code_files_skipped = scan_registered_codebase_references(ws)

        assert hits == []
        assert code_files_scanned == 0


class TestScopeMarkerParsing:
    """Test parsing of scope markers like @cpt-flow:{id}:p{N}."""

    def test_parse_flow_marker(self, tmp_path: Path):
        code = dedent("""
            # @cpt-flow:cpt-myapp-feature-auth-flow-login:p1
            def login_flow(request):
                pass
        """)
        code_file = tmp_path / "auth.py"
        code_file.write_text(code)

        cf, errs = CodeFile.from_path(code_file)
        assert not errs
        assert cf is not None
        assert len(cf.scope_markers) == 1
        assert cf.scope_markers[0].kind == "flow"
        assert cf.scope_markers[0].id == "cpt-myapp-feature-auth-flow-login"
        assert cf.scope_markers[0].phase == 1

    def test_parse_algo_marker(self, tmp_path: Path):
        code = dedent("""
            // @cpt-algo:cpt-myapp-feature-search-algo-rank:p2
            function rankResults(items) {
                return items;
            }
        """)
        code_file = tmp_path / "search.ts"
        code_file.write_text(code)

        cf, errs = CodeFile.from_path(code_file)
        assert not errs
        assert len(cf.scope_markers) == 1
        assert cf.scope_markers[0].kind == "algo"
        assert cf.scope_markers[0].id == "cpt-myapp-feature-search-algo-rank"
        assert cf.scope_markers[0].phase == 2

    def test_parse_multiple_markers(self, tmp_path: Path):
        code = dedent("""
            # @cpt-req:cpt-myapp-feature-auth-req-validate:p1
            def validate_input(data):
                pass

            # @cpt-flow:cpt-myapp-feature-auth-flow-login:p1
            def login(request):
                pass

            # @cpt-test:cpt-myapp-feature-auth-test-login:p3
            def test_login():
                pass
        """)
        code_file = tmp_path / "auth.py"
        code_file.write_text(code)

        cf, errs = CodeFile.from_path(code_file)
        assert not errs
        assert len(cf.scope_markers) == 3
        kinds = [m.kind for m in cf.scope_markers]
        assert "req" in kinds
        assert "flow" in kinds
        assert "test" in kinds


class TestBlockMarkerParsing:
    """Test parsing of block markers @cpt-begin/end."""

    def test_parse_block_marker(self, tmp_path: Path):
        code = dedent("""
            # @cpt-begin:cpt-myapp-feature-auth-flow-login:p1:inst-validate-creds
            def validate_credentials(username, password):
                if not username or not password:
                    raise ValidationError("Missing credentials")
                return authenticate(username, password)
            # @cpt-end:cpt-myapp-feature-auth-flow-login:p1:inst-validate-creds
        """)
        code_file = tmp_path / "auth.py"
        code_file.write_text(code)

        cf, errs = CodeFile.from_path(code_file)
        assert not errs
        assert len(cf.block_markers) == 1
        assert cf.block_markers[0].id == "cpt-myapp-feature-auth-flow-login"
        assert cf.block_markers[0].phase == 1
        assert cf.block_markers[0].inst == "validate-creds"
        assert len(cf.block_markers[0].content) > 0

    def test_block_markers_not_parsed_as_scope_markers(self, tmp_path: Path):
        code = dedent("""
            # @cpt-begin:cpt-myapp-feature-auth-flow-login:p1:inst-validate
            def validate():
                return True
            # @cpt-end:cpt-myapp-feature-auth-flow-login:p1:inst-validate
        """)
        code_file = tmp_path / "auth.py"
        code_file.write_text(code)

        cf, errs = CodeFile.from_path(code_file)
        assert not errs
        assert cf is not None
        assert len(cf.scope_markers) == 0
        assert len(cf.block_markers) == 1

    def test_unclosed_block_error(self, tmp_path: Path):
        code = dedent("""
            # @cpt-begin:cpt-myapp-feature-auth-flow-login:p1:inst-validate
            def validate():
                pass
            # missing @cpt-end
        """)
        code_file = tmp_path / "auth.py"
        code_file.write_text(code)

        cf, errs = CodeFile.from_path(code_file)
        assert len(errs) == 1
        assert errs[0]["code"] == EC.MARKER_BEGIN_NO_END

    def test_orphan_end_error(self, tmp_path: Path):
        code = dedent("""
            def validate():
                pass
            # @cpt-end:cpt-myapp-feature-auth-flow-login:p1:inst-validate
        """)
        code_file = tmp_path / "auth.py"
        code_file.write_text(code)

        cf, errs = CodeFile.from_path(code_file)
        assert len(errs) == 1
        assert errs[0]["code"] == EC.MARKER_END_NO_BEGIN

    def test_empty_block_error(self, tmp_path: Path):
        code = dedent("""
            # @cpt-begin:cpt-myapp-feature-auth-flow-login:p1:inst-validate
            # @cpt-end:cpt-myapp-feature-auth-flow-login:p1:inst-validate
        """)
        code_file = tmp_path / "auth.py"
        code_file.write_text(code)

        cf, errs = CodeFile.from_path(code_file)
        assert len(errs) == 1
        assert "Empty block" in errs[0]["message"]


class TestCodeFileInterface:
    """Test CodeFile interface methods (similar to Artifact)."""

    def test_list_ids(self, tmp_path: Path):
        code = dedent("""
            # @cpt-flow:cpt-myapp-feature-auth-flow-login:p1
            def login():
                pass

            # @cpt-begin:cpt-myapp-feature-auth-flow-login:p1:inst-validate
            def validate():
                pass
            # @cpt-end:cpt-myapp-feature-auth-flow-login:p1:inst-validate
        """)
        code_file = tmp_path / "auth.py"
        code_file.write_text(code)

        cf, _ = CodeFile.from_path(code_file)
        ids = cf.list_ids()
        assert "cpt-myapp-feature-auth-flow-login" in ids

    def test_get_content(self, tmp_path: Path):
        code = dedent("""
            # @cpt-begin:cpt-myapp-feature-auth-flow-login:p1:inst-validate
            def validate():
                return True
            # @cpt-end:cpt-myapp-feature-auth-flow-login:p1:inst-validate
        """)
        code_file = tmp_path / "auth.py"
        code_file.write_text(code)

        cf, _ = CodeFile.from_path(code_file)
        content = cf.get("cpt-myapp-feature-auth-flow-login")
        assert content is not None
        assert "def validate" in content

    def test_get_by_inst(self, tmp_path: Path):
        code = dedent("""
            # @cpt-begin:cpt-myapp-feature-auth-flow-login:p1:inst-validate
            def validate():
                return True
            # @cpt-end:cpt-myapp-feature-auth-flow-login:p1:inst-validate

            # @cpt-begin:cpt-myapp-feature-auth-flow-login:p1:inst-authenticate
            def authenticate():
                return True
            # @cpt-end:cpt-myapp-feature-auth-flow-login:p1:inst-authenticate
        """)
        code_file = tmp_path / "auth.py"
        code_file.write_text(code)

        cf, _ = CodeFile.from_path(code_file)
        content = cf.get_by_inst("validate")
        assert content is not None
        assert "def validate" in content

        content2 = cf.get_by_inst("authenticate")
        assert content2 is not None
        assert "def authenticate" in content2


class TestCrossValidation:
    """Test cross-validation between code and artifacts."""

    def test_orphaned_marker_error(self, tmp_path: Path):
        code = dedent("""
            # @cpt-flow:cpt-myapp-feature-unknown-flow-missing:p1
            def unknown():
                pass
        """)
        code_file = tmp_path / "auth.py"
        code_file.write_text(code)

        cf, _ = CodeFile.from_path(code_file)
        artifact_ids = {"cpt-myapp-feature-auth-flow-login"}  # different ID
        to_code_ids = set()

        result = cross_validate_code([cf], artifact_ids, to_code_ids, "FULL")
        assert len(result["errors"]) == 1
        assert "not defined in any artifact" in result["errors"][0]["message"]

    def test_missing_coverage_error(self, tmp_path: Path):
        code = dedent("""
            # @cpt-flow:cpt-myapp-feature-auth-flow-login:p1
            def login():
                pass
        """)
        code_file = tmp_path / "auth.py"
        code_file.write_text(code)

        cf, _ = CodeFile.from_path(code_file)
        artifact_ids = {"cpt-myapp-feature-auth-flow-login", "cpt-myapp-feature-auth-flow-logout"}
        to_code_ids = {"cpt-myapp-feature-auth-flow-login", "cpt-myapp-feature-auth-flow-logout"}

        result = cross_validate_code([cf], artifact_ids, to_code_ids, "FULL")
        # Should have error for missing logout marker
        coverage_errors = [e for e in result["errors"] if e["type"] == "coverage"]
        assert len(coverage_errors) == 1
        assert "cpt-myapp-feature-auth-flow-logout" in coverage_errors[0]["id"]

    def test_docs_only_prohibits_markers(self, tmp_path: Path):
        code = dedent("""
            # @cpt-flow:cpt-myapp-feature-auth-flow-login:p1
            def login():
                pass
        """)
        code_file = tmp_path / "auth.py"
        code_file.write_text(code)

        cf, _ = CodeFile.from_path(code_file)
        result = cross_validate_code([cf], set(), set(), traceability="DOCS-ONLY")
        assert len(result["errors"]) == 1
        assert "DOCS-ONLY" in result["errors"][0]["message"]

    def test_full_traceability_pass(self, tmp_path: Path):
        code = dedent("""
            # @cpt-flow:cpt-myapp-feature-auth-flow-login:p1
            def login():
                pass
        """)
        code_file = tmp_path / "auth.py"
        code_file.write_text(code)

        cf, _ = CodeFile.from_path(code_file)
        artifact_ids = {"cpt-myapp-feature-auth-flow-login"}
        to_code_ids = {"cpt-myapp-feature-auth-flow-login"}

        result = cross_validate_code([cf], artifact_ids, to_code_ids, "FULL")
        assert len(result["errors"]) == 0


class TestLoadCodeFile:
    """Test load_code_file wrapper function."""

    def test_load_existing_file(self, tmp_path: Path):
        code = "# @cpt-flow:cpt-myapp-flow-test:p1\ndef foo(): pass\n"
        code_file = tmp_path / "test.py"
        code_file.write_text(code)

        cf, errs = load_code_file(code_file)
        assert cf is not None
        assert not errs
        assert len(cf.scope_markers) == 1

    def test_load_nonexistent_file(self, tmp_path: Path):
        cf, errs = load_code_file(tmp_path / "nonexistent.py")
        assert cf is None
        assert len(errs) == 1
        assert errs[0]["type"] == "file"
        assert errs[0]["code"] == EC.FILE_READ_ERROR

    def test_an_oversized_file_has_its_own_error_code(self, tmp_path: Path):
        """Distinct from a read failure, so a caller can branch on the code instead of
        re-measuring the file or parsing the message."""
        code_file = tmp_path / "big.py"
        code_file.write_text("x = 1\n" * 100)

        cf, errs = load_code_file(code_file, max_bytes=16)

        assert cf is None
        assert [e["code"] for e in errs] == [EC.FILE_TOO_LARGE]

    def test_the_ceiling_bounds_the_bytes_read_not_a_prior_stat(self, tmp_path: Path, monkeypatch):
        """stat-then-read let a file growing in between slip past the limit it had just
        been checked against. The reader no longer measures the file at all."""
        code_file = tmp_path / "test.py"
        code_file.write_text("# @cpt-flow:cpt-myapp-flow-test:p1\ndef foo(): pass\n")
        real_stat = Path.stat

        def _stat_fails(self, *a, **k):
            if self == code_file:
                raise OSError("stat refused")
            return real_stat(self, *a, **k)
        monkeypatch.setattr(Path, "stat", _stat_fails)

        cf, errs = load_code_file(code_file, max_bytes=1000)
        assert cf is not None and not errs
        assert load_code_file(code_file, max_bytes=8)[1][0]["code"] == EC.FILE_TOO_LARGE

    def test_from_text_parses_without_touching_the_file(self, tmp_path: Path):
        cf, errs = CodeFile.from_text(tmp_path / "ghost.py", "# @cpt-flow:cpt-myapp-flow-test:p1\n")

        assert cf is not None and not errs
        assert len(cf.scope_markers) == 1


class TestReadCodeText:
    """The shared bounded reader: the ceiling applies to the bytes read, too-large has
    its own code, and everything else that stops a read is a read error."""

    def test_a_file_exactly_at_the_limit_is_read_whole(self, tmp_path: Path):
        path = tmp_path / "f.py"
        path.write_bytes(b"x" * 16)

        assert read_code_text(path, max_bytes=16) == ("x" * 16, [])

    def test_one_byte_over_the_limit_is_too_large(self, tmp_path: Path):
        path = tmp_path / "f.py"
        path.write_bytes(b"x" * 17)

        text, errs = read_code_text(path, max_bytes=16)

        assert text is None
        assert [e["code"] for e in errs] == [EC.FILE_TOO_LARGE]

    def test_a_non_positive_limit_disables_the_ceiling(self, tmp_path: Path):
        path = tmp_path / "f.py"
        path.write_bytes(b"x" * 5000)

        assert read_code_text(path, max_bytes=0) == ("x" * 5000, [])
        assert read_code_text(path, max_bytes=-1) == ("x" * 5000, [])

    def test_a_missing_file_is_a_read_error(self, tmp_path: Path):
        text, errs = read_code_text(tmp_path / "missing.py")

        assert text is None
        assert [e["code"] for e in errs] == [EC.FILE_READ_ERROR]

    def test_invalid_utf8_is_a_read_error_not_too_large(self, tmp_path: Path):
        path = tmp_path / "f.py"
        path.write_bytes(b"\xff\xfe not text")

        text, errs = read_code_text(path, max_bytes=100)

        assert text is None
        assert [e["code"] for e in errs] == [EC.FILE_READ_ERROR]

    def test_nul_bytes_are_binary_by_the_same_rule_the_document_reader_uses(self, tmp_path: Path):
        path = tmp_path / "f.py"
        path.write_bytes(b"# @cpt-flow:cpt-myapp-flow-test:p1\n\x00rest")

        text, errs = read_code_text(path)

        assert text is None
        assert [e["code"] for e in errs] == [EC.FILE_READ_ERROR]

    def test_the_binary_rule_is_one_predicate_shared_with_the_document_reader(self, tmp_path: Path, monkeypatch):
        """Both readers call `document.is_binary`, so the rule cannot drift between them.
        Swapping the predicate turns a plain text file binary for both at once — which
        two hand-kept literal checks, agreeing only by convention, could not do."""
        path = tmp_path / "f.py"
        path.write_bytes(b"x = 1\n")
        monkeypatch.setattr(document, "is_binary", lambda raw: True)

        text, errs = read_code_text(path)

        assert text is None
        assert [e["code"] for e in errs] == [EC.FILE_READ_ERROR]
        assert document.read_text_safe(path) is None


class TestFromTextParity:
    """`from_text` must parse exactly as `from_path` does, or a pre-read caller and a
    path-based one would disagree about the same file."""

    @pytest.mark.parametrize("text", [
        "# @cpt-flow:cpt-myapp-flow-test:p1\n# @cpt-begin:cpt-myapp-flow-test:p1:inst-a\nx = 1\n"
        "# @cpt-end:cpt-myapp-flow-test:p1:inst-a\n",
        "# @cpt-end:cpt-myapp-flow-test:p1:inst-never-opened\n",
        "# @cpt-begin:cpt-myapp-flow-test:p1:inst-a\nx = 1\n# @cpt-end:cpt-myapp-flow-other:p1:inst-a\n",
        "# @cpt-begin:cpt-myapp-flow-test:p1:inst-a\nx = 1\n",
    ], ids=["valid", "dangling-end", "mismatched-id", "unclosed"])
    def test_from_text_and_from_path_agree(self, tmp_path: Path, text: str):
        path = tmp_path / "f.py"
        path.write_text(text, encoding="utf-8")

        via_path = CodeFile.from_path(path)
        via_text = CodeFile.from_text(path, text)

        assert (via_path[0] is None) == (via_text[0] is None)
        assert via_path[1] == via_text[1], "same errors, same order"
        if via_path[0] is not None and via_text[0] is not None:
            assert via_path[0].scope_markers == via_text[0].scope_markers
            assert via_path[0].block_markers == via_text[0].block_markers
            assert via_path[0].references == via_text[0].references


class TestValidateCodeFile:
    """Test validate_code_file wrapper function."""

    def test_validate_valid_file(self, tmp_path: Path):
        code = "# @cpt-flow:cpt-myapp-flow-test:p1\ndef foo(): pass\n"
        code_file = tmp_path / "test.py"
        code_file.write_text(code)

        result = validate_code_file(code_file)
        assert result["errors"] == []
        assert result["warnings"] == []

    def test_validate_file_with_errors(self, tmp_path: Path):
        code = "# @cpt-begin:cpt-myapp-flow-test:p1:inst-foo\n# missing end\n"
        code_file = tmp_path / "test.py"
        code_file.write_text(code)

        result = validate_code_file(code_file)
        assert len(result["errors"]) == 1
        assert result["errors"][0]["code"] == EC.MARKER_BEGIN_NO_END

    def test_validate_nonexistent_file(self, tmp_path: Path):
        result = validate_code_file(tmp_path / "nonexistent.py")
        assert len(result["errors"]) == 1
        assert result["errors"][0]["type"] == "file"


class TestCodeFileList:
    """Test CodeFile.list() method."""

    def test_list_multiple_ids(self, tmp_path: Path):
        code = dedent("""
            # @cpt-begin:cpt-myapp-flow-a:p1:inst-a
            def a(): pass
            # @cpt-end:cpt-myapp-flow-a:p1:inst-a

            # @cpt-begin:cpt-myapp-flow-b:p1:inst-b
            def b(): pass
            # @cpt-end:cpt-myapp-flow-b:p1:inst-b
        """)
        code_file = tmp_path / "test.py"
        code_file.write_text(code)

        cf, _ = CodeFile.from_path(code_file)
        results = cf.list(["cpt-myapp-flow-a", "cpt-myapp-flow-b", "cpt-myapp-flow-c"])

        assert len(results) == 3
        assert "def a" in results[0]
        assert "def b" in results[1]
        assert results[2] is None  # Non-existent ID


class TestCodeFileGetScopeMarker:
    """Test getting content from scope markers (not just blocks)."""

    def test_get_scope_marker_content(self, tmp_path: Path):
        code = "# @cpt-flow:cpt-myapp-flow-test:p1\ndef foo(): pass\n"
        code_file = tmp_path / "test.py"
        code_file.write_text(code)

        cf, _ = CodeFile.from_path(code_file)
        content = cf.get("cpt-myapp-flow-test")
        # For scope markers, returns the raw line
        assert content is not None
        assert "@cpt-flow" in content

    def test_get_nonexistent_id(self, tmp_path: Path):
        code = "def foo(): pass\n"
        code_file = tmp_path / "test.py"
        code_file.write_text(code)

        cf, _ = CodeFile.from_path(code_file)
        content = cf.get("cpt-myapp-nonexistent")
        assert content is None

    def test_get_by_inst_nonexistent(self, tmp_path: Path):
        code = "def foo(): pass\n"
        code_file = tmp_path / "test.py"
        code_file.write_text(code)

        cf, _ = CodeFile.from_path(code_file)
        content = cf.get_by_inst("nonexistent")
        assert content is None


class TestDuplicateMarkerWarnings:
    """Test duplicate marker detection."""

    def test_duplicate_scope_marker_warning(self, tmp_path: Path):
        code = dedent("""
            # @cpt-flow:cpt-myapp-flow-test:p1
            def foo(): pass

            # @cpt-flow:cpt-myapp-flow-test:p1
            def bar(): pass
        """)
        code_file = tmp_path / "test.py"
        code_file.write_text(code)

        cf, _ = CodeFile.from_path(code_file)
        result = cf.validate()

        # Duplicate scope markers should produce an error
        assert len(result["errors"]) == 1
        assert "Duplicate scope marker" in result["errors"][0]["message"]

    def test_duplicate_begin_without_end(self, tmp_path: Path):
        code = dedent("""
            # @cpt-begin:cpt-myapp-flow-test:p1:inst-foo
            def foo(): pass
            # @cpt-begin:cpt-myapp-flow-test:p1:inst-foo
            def bar(): pass
            # @cpt-end:cpt-myapp-flow-test:p1:inst-foo
        """)
        code_file = tmp_path / "test.py"
        code_file.write_text(code)

        cf, errs = CodeFile.from_path(code_file)
        # Should have error about duplicate @cpt-begin
        assert any("Duplicate @cpt-begin" in e["message"] for e in errs)


class TestStateMarker:
    """Test state marker kind parsing."""

    def test_parse_state_marker(self, tmp_path: Path):
        code = "# @cpt-state:cpt-myapp-state-auth:p1\nauth_state = {}\n"
        code_file = tmp_path / "state.py"
        code_file.write_text(code)

        cf, errs = CodeFile.from_path(code_file)
        assert not errs
        assert len(cf.scope_markers) == 1
        assert cf.scope_markers[0].kind == "state"


class TestCodeFileLoad:
    """Test CodeFile.load() method edge cases."""

    def test_already_loaded(self, tmp_path: Path):
        code = "# @cpt-flow:cpt-myapp-flow-test:p1\ndef foo(): pass\n"
        code_file = tmp_path / "test.py"
        code_file.write_text(code)

        cf, errs = CodeFile.from_path(code_file)
        assert not errs

        # Call load again - should return empty errors (already loaded)
        errs2 = cf.load()
        assert errs2 == []


class TestCrossValidationEdgeCases:
    """Test edge cases in cross-validation."""

    def test_docs_only_with_no_markers(self, tmp_path: Path):
        code = "def foo(): pass\n"
        code_file = tmp_path / "test.py"
        code_file.write_text(code)

        code_obj, _ = CodeFile.from_path(code_file)
        result = cross_validate_code([code_obj], set(), set(), "DOCS-ONLY")
        # No markers in DOCS-ONLY mode should be fine
        assert len(result["errors"]) == 0

    def test_empty_code_files_list(self):
        result = cross_validate_code([], {"cpt-myapp-id"}, {"cpt-myapp-id"}, "FULL")
        # No code files - missing coverage errors for to_code IDs
        assert len(result["errors"]) == 1
        assert result["errors"][0]["type"] == "coverage"

    def test_multiple_code_files(self, tmp_path: Path):
        code1 = "# @cpt-flow:cpt-myapp-flow-a:p1\ndef a(): pass\n"
        code2 = "# @cpt-flow:cpt-myapp-flow-b:p1\ndef b(): pass\n"

        (tmp_path / "a.py").write_text(code1)
        (tmp_path / "b.py").write_text(code2)

        cf1, _ = CodeFile.from_path(tmp_path / "a.py")
        cf2, _ = CodeFile.from_path(tmp_path / "b.py")

        artifact_ids = {"cpt-myapp-flow-a", "cpt-myapp-flow-b"}
        to_code_ids = {"cpt-myapp-flow-a", "cpt-myapp-flow-b"}

        result = cross_validate_code([cf1, cf2], artifact_ids, to_code_ids, "FULL")
        assert len(result["errors"]) == 0


class TestCrossValidateForbiddenAndInstances:
    """Test forbidden_code_ids and artifact_instances branches."""

    def test_forbidden_code_id_emits_task_unchecked(self, tmp_path: Path):
        """forbidden_code_ids with a matching ref but no instructions → error."""
        code = "# @cpt-flow:cpt-myapp-feat-login:p1\ndef login(): pass\n"
        (tmp_path / "app.py").write_text(code)
        cf, _ = CodeFile.from_path(tmp_path / "app.py")

        artifact_ids = {"cpt-myapp-feat-login"}
        to_code_ids = set()
        forbidden = {"cpt-myapp-feat-login"}

        result = cross_validate_code(
            [cf], artifact_ids, to_code_ids,
            forbidden_code_ids=forbidden,
        )
        task_unchecked = [e for e in result["errors"] if e.get("code") == EC.CODE_TASK_UNCHECKED]
        assert len(task_unchecked) == 1
        assert "cpt-myapp-feat-login" in task_unchecked[0]["message"]

    def test_forbidden_code_id_skipped_when_instructions_incomplete(self, tmp_path: Path):
        """forbidden_code_ids skips error when artifact has uncovered instructions."""
        code = (
            "# @cpt-begin:cpt-myapp-feat-login:p1:inst-parse\n"
            "def parse(): pass\n"
            "# @cpt-end:cpt-myapp-feat-login:p1:inst-parse\n"
        )
        (tmp_path / "app.py").write_text(code)
        cf, _ = CodeFile.from_path(tmp_path / "app.py")

        artifact_ids = {"cpt-myapp-feat-login"}
        to_code_ids = set()
        forbidden = {"cpt-myapp-feat-login"}
        # Artifact defines two instructions but code only has one → skip error
        all_insts = {"cpt-myapp-feat-login": {"parse", "execute"}}

        result = cross_validate_code(
            [cf], artifact_ids, to_code_ids,
            forbidden_code_ids=forbidden,
            artifact_instances_all=all_insts,
        )
        task_unchecked = [e for e in result["errors"] if e.get("code") == EC.CODE_TASK_UNCHECKED]
        assert len(task_unchecked) == 0

    def test_artifact_instances_missing_instruction(self, tmp_path: Path):
        """artifact_instances with missing code instruction → CODE_INST_MISSING error."""
        code = (
            "# @cpt-begin:cpt-myapp-feat-login:p1:inst-parse\n"
            "def parse(): pass\n"
            "# @cpt-end:cpt-myapp-feat-login:p1:inst-parse\n"
        )
        (tmp_path / "app.py").write_text(code)
        cf, _ = CodeFile.from_path(tmp_path / "app.py")

        artifact_ids = {"cpt-myapp-feat-login"}
        to_code_ids = {"cpt-myapp-feat-login"}
        # Artifact expects both "parse" and "execute", code only has "parse"
        instances = {"cpt-myapp-feat-login": {"parse", "execute"}}

        result = cross_validate_code(
            [cf], artifact_ids, to_code_ids,
            artifact_instances=instances,
        )
        missing = [e for e in result["errors"] if e.get("code") == EC.CODE_INST_MISSING]
        assert len(missing) == 1
        assert "execute" in missing[0]["message"]

    def test_artifact_instances_orphan_instruction(self, tmp_path: Path):
        """Code has instruction not defined in artifact → CODE_INST_ORPHAN error."""
        code = (
            "# @cpt-begin:cpt-myapp-feat-login:p1:inst-parse\n"
            "def parse(): pass\n"
            "# @cpt-end:cpt-myapp-feat-login:p1:inst-parse\n"
            "# @cpt-begin:cpt-myapp-feat-login:p1:inst-extra\n"
            "def extra(): pass\n"
            "# @cpt-end:cpt-myapp-feat-login:p1:inst-extra\n"
        )
        (tmp_path / "app.py").write_text(code)
        cf, _ = CodeFile.from_path(tmp_path / "app.py")

        artifact_ids = {"cpt-myapp-feat-login"}
        to_code_ids = {"cpt-myapp-feat-login"}
        # Artifact only expects "parse", but code also has "extra"
        instances = {"cpt-myapp-feat-login": {"parse"}}

        result = cross_validate_code(
            [cf], artifact_ids, to_code_ids,
            artifact_instances=instances,
        )
        orphan = [e for e in result["errors"] if e.get("code") == EC.CODE_INST_ORPHAN]
        assert len(orphan) == 1
        assert "extra" in orphan[0]["message"]


class TestErrorFunction:
    """Test the error helper function."""

    def test_error_with_extra_fields(self, tmp_path: Path):
        from studio.utils.codebase import error

        err = error("test", "Test message", path=tmp_path / "test.py", line=10, custom="value")

        assert err["type"] == "test"
        assert err["message"] == "Test message"
        assert err["line"] == 10
        assert err["custom"] == "value"

    def test_error_none_extra_fields_ignored(self, tmp_path: Path):
        from studio.utils.codebase import error

        err = error("test", "Message", path=tmp_path, line=1, skip_none=None)

        assert "skip_none" not in err


class TestOverlappingEntriesAreScannedOnce:
    """`resolve_entry_code_files` deduplicates within one entry's own walk, and nothing
    spanned entries. So when one registered entry is a parent of another, every file
    under the overlap was parsed and counted once per covering entry — inflating
    `files_scanned` and duplicating each CPT hit, which feeds the coverage numbers. A
    registry mistake read as *more* coverage rather than as a mistake.
    """

    def _project(self, tmp_path: Path):
        nested = tmp_path / "src" / "pkg"
        nested.mkdir(parents=True)
        (nested / "auth.py").write_text(
            dedent("""
                # @cpt-begin:cpt-myapp-feature-auth-flow-login:p1:inst-check-creds
                def login():
                    pass
                # @cpt-end:cpt-myapp-feature-auth-flow-login:p1:inst-check-creds
            """)
        )
        return tmp_path / "src", nested

    def test_a_file_covered_by_two_entries_is_counted_once(self, tmp_path: Path):
        parent, child = self._project(tmp_path)
        ctx = _FakeCtx(tmp_path, [_FakeCodebaseEntry(parent, [".py"]),
                                  _FakeCodebaseEntry(child, [".py"])])

        hits, scanned, skipped = scan_registered_codebase_references(ctx)

        assert scanned == 1, "the same file must not be parsed once per covering entry"
        assert len(hits) == 1, "a duplicated hit inflates coverage"
        assert skipped == 0, "'skipped' means ignored/oversized/unparsable — this was none of those"

    def test_the_overlap_is_reported_rather_than_silently_absorbed(
            self, tmp_path: Path, caplog):
        """The registry is the thing that wants correcting. Deduplicating quietly would
        leave the overlap in place for the next reader to rediscover."""
        import logging

        parent, child = self._project(tmp_path)
        ctx = _FakeCtx(tmp_path, [_FakeCodebaseEntry(parent, [".py"]),
                                  _FakeCodebaseEntry(child, [".py"])])

        with caplog.at_level(logging.WARNING):
            scan_registered_codebase_references(ctx)

        assert any("overlap" in r.getMessage() for r in caplog.records)

    def test_entries_that_do_not_overlap_are_unaffected(self, tmp_path: Path):
        """The dedupe must not start dropping distinct files."""
        for name in ("a", "b"):
            d = tmp_path / name
            d.mkdir()
            (d / f"{name}.py").write_text(
                dedent(f"""
                    # @cpt-begin:cpt-myapp-feature-auth-flow-{name}:p1:inst-x
                    def f():
                        pass
                    # @cpt-end:cpt-myapp-feature-auth-flow-{name}:p1:inst-x
                """)
            )
        ctx = _FakeCtx(tmp_path, [_FakeCodebaseEntry(tmp_path / "a", [".py"]),
                                  _FakeCodebaseEntry(tmp_path / "b", [".py"])])

        hits, scanned, _skipped = scan_registered_codebase_references(ctx)

        assert scanned == 2
        assert len(hits) == 2


class TestACandidateIsResolvedOnce:
    """Three independent `resolve()` calls per scanned file, two of them discarded.

    The dedup identity, the ignored-directory test and the containment test each
    resolved the same path. The dedup's was also the only one of the three that
    was unguarded, so an unresolvable candidate escaped a function whose other
    two resolutions both treat that as an ordinary skip (#236 review).
    """

    def test_each_candidate_is_resolved_exactly_once(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from collections import Counter

        from studio.utils.codebase import resolve_entry_code_files

        (tmp_path / "src").mkdir()
        target = tmp_path / "src" / "a.py"
        target.write_text("x = 1", encoding="utf-8")

        counts: Counter[str] = Counter()
        real_resolve = Path.resolve

        def _counting_resolve(self, *args, **kwargs):
            counts[str(self)] += 1
            return real_resolve(self, *args, **kwargs)

        monkeypatch.setattr(Path, "resolve", _counting_resolve)

        files, _ = resolve_entry_code_files(
            tmp_path / "src", [".py"], project_root=tmp_path, seen=set())

        assert files == [target]
        assert counts[str(target)] == 1, (
            f"the candidate was resolved {counts[str(target)]} times, not once")

    def test_an_unresolvable_candidate_is_excluded_rather_than_raised(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The dedup path used to let this propagate out of the whole scan."""
        from studio.utils.codebase import resolve_entry_code_files

        (tmp_path / "src").mkdir()
        good = tmp_path / "src" / "good.py"
        good.write_text("x = 1", encoding="utf-8")
        bad = tmp_path / "src" / "bad.py"
        bad.write_text("x = 2", encoding="utf-8")

        real_resolve = Path.resolve

        def _resolve_or_loop(self, *args, **kwargs):
            if self.name == "bad.py":
                raise OSError(40, "Too many levels of symbolic links")
            return real_resolve(self, *args, **kwargs)

        monkeypatch.setattr(Path, "resolve", _resolve_or_loop)

        files, excluded = resolve_entry_code_files(
            tmp_path / "src", [".py"], project_root=tmp_path, seen=set())

        assert files == [good], "one unresolvable file must not lose the rest of the scan"
        assert excluded == 1, "the unresolvable file still has to count against the total"


class TestASingleFileEntryIsDedupedToo:
    """`seen` makes the count honest across entries — in every branch, not most.

    The single-file branch returned before `seen` was consulted, so a file both
    registered in its own right and covered by a directory entry was counted
    under both. That is the exact double count `seen` was added to end, surviving
    in the one branch that skipped it (#236 review).
    """

    @staticmethod
    def _entry(path, root, seen):
        from studio.utils.codebase import resolve_entry_code_files
        return resolve_entry_code_files(path, [".py"], project_root=root, seen=seen)

    def test_a_file_already_counted_under_a_directory_is_not_counted_again(
            self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        target = tmp_path / "src" / "a.py"
        target.write_text("x = 1", encoding="utf-8")
        seen: set = set()

        first, _ = self._entry(tmp_path / "src", tmp_path, seen)
        second, excluded = self._entry(target, tmp_path, seen)

        assert first == [target]
        assert second == [], "the directory entry already covered this file"
        assert excluded == 0, "a file decided earlier is neither counted nor excluded"

    def test_it_works_in_the_other_order_too(self, tmp_path: Path) -> None:
        """Registry order is not guaranteed, so the file entry must register itself."""
        (tmp_path / "src").mkdir()
        target = tmp_path / "src" / "a.py"
        target.write_text("x = 1", encoding="utf-8")
        other = tmp_path / "src" / "b.py"
        other.write_text("y = 2", encoding="utf-8")
        seen: set = set()

        first, _ = self._entry(target, tmp_path, seen)
        second, _ = self._entry(tmp_path / "src", tmp_path, seen)

        assert first == [target]
        assert second == [other], "the file entry did not register itself in `seen`"

    def test_without_a_shared_set_the_behaviour_is_exactly_as_before(
            self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        target = tmp_path / "src" / "a.py"
        target.write_text("x = 1", encoding="utf-8")

        first, _ = self._entry(tmp_path / "src", tmp_path, None)
        second, _ = self._entry(target, tmp_path, None)

        assert first == [target]
        assert second == [target], "omitting `seen` must not start deduplicating"


class TestASymlinkNeverClaimsItsTargetsIdentity:
    """A link resolves to the file it points at, and `seen` is keyed on identity.

    Registering the resolved path for a symlink claimed the *target's* identity,
    so the real file -- reached later in the same walk, or under another entry --
    looked already-decided and left the scan, while the link that displaced it was
    excluded anyway. `candidates` is a set, so which of the two was reached first
    moved with `PYTHONHASHSEED`: the same tree scanned twice could report
    different files (#236 review).
    """

    @staticmethod
    def _entry(path, root, seen):
        from studio.utils.codebase import resolve_entry_code_files
        return resolve_entry_code_files(path, [".py"], project_root=root, seen=seen)

    @staticmethod
    def _tree(tmp_path):
        (tmp_path / "src").mkdir()
        real = tmp_path / "src" / "real.py"
        real.write_text("x = 1", encoding="utf-8")
        link = tmp_path / "src" / "link.py"
        link.symlink_to(real)
        return real, link

    def test_the_real_file_survives_whichever_was_reached_first(self, tmp_path: Path) -> None:
        real, _link = self._tree(tmp_path)

        files, _ = self._entry(tmp_path / "src", tmp_path, set())

        assert files == [real], "the symlink displaced the file it points at"

    def test_the_real_file_survives_across_entries_too(self, tmp_path: Path) -> None:
        """A symlink under one entry must not hide a real file covered by another."""
        real, link = self._tree(tmp_path)
        (tmp_path / "other").mkdir()
        seen: set = set()

        first, _ = self._entry(link, tmp_path, seen)
        second, _ = self._entry(tmp_path / "src", tmp_path, seen)

        assert first == [], "a symlink entry is still excluded"
        assert real in second, "the symlink registered its target and hid the real file"

    def test_a_link_reached_by_two_overlapping_entries_is_excluded_once(
            self, tmp_path: Path) -> None:
        """Keying on its own path has to keep the exclusion deduped, too.

        Two registered directories where one contains the other, which is the
        overlap `seen` was added for. Both walks reach the same link and the same
        file; the second must find them already decided.
        """
        real, _link = self._tree(tmp_path)
        seen: set = set()

        first, excluded_first = self._entry(tmp_path, tmp_path, seen)
        second, excluded_second = self._entry(tmp_path / "src", tmp_path, seen)

        assert first == [real]
        assert excluded_first == 1, "the link is the one skip"
        assert second == [], "the file was already decided under the parent entry"
        assert excluded_second == 0, "the same link was counted against the total twice"

    def test_the_totals_still_add_up(self, tmp_path: Path) -> None:
        """`scanned + skipped` has to equal what was actually there."""
        real, _link = self._tree(tmp_path)

        files, excluded = self._entry(tmp_path / "src", tmp_path, set())

        assert files == [real]
        assert excluded == 1, "two candidates, one file and one link: the link is the skip"


class TestASymlinkLoopIsAnOrdinaryExclusion:
    """A loop in a registered tree is one unreadable candidate, not a failed scan.

    `Path.resolve()` raises `RuntimeError` on a loop up to Python 3.12 and `OSError`
    from 3.13; the handlers caught only the second, so on 3.11 and 3.12 one loop
    aborted the whole scan (#236 review). Built from real links rather than a
    patched `resolve`, because the defect *was* which exception the real call
    raises -- a fake that raises `OSError` is exactly the test that passed while
    the scan crashed. On 3.13+ this passes with or without the fix.
    """

    @staticmethod
    def _looped_tree(tmp_path: Path) -> Path:
        src = tmp_path / "src"
        src.mkdir()
        (src / "ok.py").write_text("x = 1\n", encoding="utf-8")
        (src / "a.py").symlink_to("b.py")
        (src / "b.py").symlink_to("a.py")
        return src

    def test_the_scan_survives_and_counts_the_loop_as_excluded(self, tmp_path: Path) -> None:
        from studio.utils.codebase import resolve_entry_code_files

        src = self._looped_tree(tmp_path)

        files, excluded = resolve_entry_code_files(src, [".py"], project_root=tmp_path)

        assert [f.name for f in files] == ["ok.py"]
        assert excluded == 2, "each link of the loop is one excluded candidate"

    def test_a_shared_seen_set_does_not_change_that(self, tmp_path: Path) -> None:
        from studio.utils.codebase import resolve_entry_code_files

        src = self._looped_tree(tmp_path)
        seen: set = set()

        files, excluded = resolve_entry_code_files(src, [".py"], project_root=tmp_path, seen=seen)

        assert [f.name for f in files] == ["ok.py"] and excluded == 2

    def test_a_loop_as_the_entry_itself_is_not_an_error(self, tmp_path: Path) -> None:
        """A guard, not a regression test: `exists()` is False on a loop, so the entry
        is dropped before anything resolves it, with or without the fix. Pinned so
        that reordering those two checks cannot bring the crash back."""
        from studio.utils.codebase import resolve_entry_code_files

        (tmp_path / "x.py").symlink_to("y.py")
        (tmp_path / "y.py").symlink_to("x.py")

        assert resolve_entry_code_files(tmp_path / "x.py", [".py"], project_root=tmp_path) == ([], 0)


class TestAnUnresolvableEntryIsOneExclusion:
    """The entry itself is resolved once, up front, and a failure there is one
    excluded entry -- for a file entry and a directory entry alike. That guard had no
    test of its own; the loop tests only reach the candidates inside an entry
    (#236 review)."""

    @staticmethod
    def _entry_cannot_resolve(monkeypatch, entry: Path, exc: Exception) -> None:
        real = Path.resolve

        def _resolve(self, *args, **kwargs):
            if self == entry:
                raise exc
            return real(self, *args, **kwargs)

        monkeypatch.setattr(Path, "resolve", _resolve)

    @pytest.mark.parametrize("exc", [OSError(40, "Too many levels of symbolic links"),
                                     RuntimeError("Symlink loop")],
                             ids=["oserror", "runtimeerror"])
    @pytest.mark.parametrize("kind", ["file", "directory"])
    def test_the_entry_is_excluded_not_raised(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind, exc) -> None:
        from studio.utils.codebase import resolve_entry_code_files

        if kind == "file":
            entry = tmp_path / "one.py"
            entry.write_text("x = 1\n", encoding="utf-8")
        else:
            entry = tmp_path / "src"
            entry.mkdir()
            (entry / "one.py").write_text("x = 1\n", encoding="utf-8")
        self._entry_cannot_resolve(monkeypatch, entry, exc)

        assert resolve_entry_code_files(entry, [".py"], project_root=tmp_path) == ([], 1)
