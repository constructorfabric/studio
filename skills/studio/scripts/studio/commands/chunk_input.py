"""
Chunk oversized workflow input into deterministic line-bounded files.

@cpt-flow:cpt-studio-flow-execution-plans-chunk-raw-input:p1
@cpt-algo:cpt-studio-algo-execution-plans-chunk-normalize-input:p1
@cpt-algo:cpt-studio-algo-execution-plans-chunk-ranges:p1
@cpt-algo:cpt-studio-algo-execution-plans-chunk-write:p1
@cpt-state:cpt-studio-state-execution-plans-raw-input-package:p1
@cpt-dod:cpt-studio-dod-execution-plans-raw-input:p1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from ..utils.ui import ui

logger = logging.getLogger(__name__)

DEFAULT_MAX_LINES = 300
DEFAULT_THRESHOLD_LINES = 500
CHUNK_FILE_RE = re.compile(r"^\d+-\d+-.+-part-\d+\.[^.]+$")
DIRECT_PROMPT_FILE = "direct-prompt.md"
PACKAGE_MANIFEST_FILE = "manifest.json"


def _warn_chunk_input(message: str) -> None:
    logger.warning("chunk-input: %s", message)


# @cpt-begin:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-parse-args
class _ChunkInputArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)
# @cpt-end:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-parse-args


# @cpt-begin:cpt-studio-algo-execution-plans-chunk-normalize-input:p1:inst-normalize-newlines
def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")
# @cpt-end:cpt-studio-algo-execution-plans-chunk-normalize-input:p1:inst-normalize-newlines


def _line_count(text: str) -> int:
    return len(_normalize_newlines(text).splitlines())


# @cpt-begin:cpt-studio-algo-execution-plans-chunk-normalize-input:p1:inst-slugify-source
def _slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback
# @cpt-end:cpt-studio-algo-execution-plans-chunk-normalize-input:p1:inst-slugify-source


# @cpt-begin:cpt-studio-algo-execution-plans-chunk-normalize-input:p1:inst-read-file-source
def _read_source(path_str: str, index: int) -> Dict[str, object]:
    path = Path(path_str).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")
    text = _normalize_newlines(path.read_text(encoding="utf-8"))
    label = _slugify(path.stem, f"input-{index:02d}")
    return {
        "kind": "file",
        "label": label,
        "display_name": path.name,
        "path": path.as_posix(),
        "text": text,
        "line_count": _line_count(text),
    }
# @cpt-end:cpt-studio-algo-execution-plans-chunk-normalize-input:p1:inst-read-file-source


# @cpt-begin:cpt-studio-algo-execution-plans-chunk-normalize-input:p1:inst-read-stdin-source
def _read_stdin_source(stdin_label: str) -> Dict[str, object]:
    text = _normalize_newlines(sys.stdin.read())
    if not text.strip():
        raise ValueError("No stdin input provided")
    label = _slugify(stdin_label, "direct-input")
    return {
        "kind": "stdin",
        "label": label,
        "display_name": stdin_label,
        "path": None,
        "text": text,
        "line_count": _line_count(text),
    }
# @cpt-end:cpt-studio-algo-execution-plans-chunk-normalize-input:p1:inst-read-stdin-source


# @cpt-begin:cpt-studio-algo-execution-plans-chunk-ranges:p1:inst-return-ranges
def _chunk_ranges(total_lines: int, max_lines: int) -> List[Tuple[int, int]]:
    if total_lines <= 0:
        return [(1, 0)]
    ranges: List[Tuple[int, int]] = []
    start = 1
    while start <= total_lines:
        end = min(start + max_lines - 1, total_lines)
        ranges.append((start, end))
        start = end + 1
    return ranges
# @cpt-end:cpt-studio-algo-execution-plans-chunk-ranges:p1:inst-return-ranges


# @cpt-begin:cpt-studio-algo-execution-plans-chunk-write:p1:inst-write-direct-prompt
def _write_special_source_files(
    sources: Sequence[Dict[str, object]],
    output_dir: Path,
) -> None:
    for source in sources:
        if source["kind"] != "stdin":
            continue
        raw_path = output_dir / DIRECT_PROMPT_FILE
        raw_text = str(source["text"])
        if raw_text and not raw_text.endswith("\n"):
            raw_text += "\n"
        raw_path.write_text(raw_text, encoding="utf-8")
        source["stored_file"] = DIRECT_PROMPT_FILE
# @cpt-end:cpt-studio-algo-execution-plans-chunk-write:p1:inst-write-direct-prompt


# @cpt-begin:cpt-studio-algo-execution-plans-chunk-write:p1:inst-clean-stale
def _preserve_non_generated(src_dir: Path, dst_dir: Path) -> None:
    """Copy non-generated files and subdirectories from *src_dir* into *dst_dir*."""
    if not src_dir.exists():
        return
    for child in src_dir.iterdir():
        target = dst_dir / child.name
        if target.exists():
            continue
        if child.is_dir():
            shutil.copytree(child, target)
        elif child.is_file():
            if child.name in {DIRECT_PROMPT_FILE, PACKAGE_MANIFEST_FILE} or CHUNK_FILE_RE.match(child.name):
                continue
            shutil.copy2(child, target)
# @cpt-end:cpt-studio-algo-execution-plans-chunk-write:p1:inst-clean-stale


# @cpt-begin:cpt-studio-algo-execution-plans-chunk-write:p1:inst-build-input-signature
def _build_input_signature(sources: Sequence[Dict[str, object]]) -> Tuple[str, List[Dict[str, object]]]:
    source_records: List[Dict[str, object]] = []
    signature_records: List[Dict[str, object]] = []
    for source in sources:
        content_sha256 = hashlib.sha256(str(source["text"]).encode("utf-8")).hexdigest()
        source_records.append({
            "kind": source["kind"],
            "label": source["label"],
            "display_name": source["display_name"],
            "path": source["path"],
            "line_count": int(source["line_count"]),
            "content_sha256": content_sha256,
        })
        # Signature excludes presentation-only metadata (label, display_name)
        # so that stdin-label changes do not break reuse of identical content.
        signature_records.append({
            "kind": source["kind"],
            "path": source["path"],
            "content_sha256": content_sha256,
        })
    payload = json.dumps(signature_records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), source_records
# @cpt-end:cpt-studio-algo-execution-plans-chunk-write:p1:inst-build-input-signature


# @cpt-begin:cpt-studio-algo-execution-plans-chunk-write:p1:inst-write-package-manifest
def _write_package_manifest(
    sources: Sequence[Dict[str, object]],
    chunks: Sequence[Dict[str, object]],
    output_dir: Path,
    max_lines: int,
) -> str:
    input_signature, source_records = _build_input_signature(sources)
    manifest = {
        "version": 1,
        "input_signature": input_signature,
        "total_sources": len(sources),
        "total_lines": sum(int(source["line_count"]) for source in sources),
        "max_lines": max_lines,
        "direct_prompt_file": next(
            (
                str(source.get("stored_file"))
                for source in sources
                if source["kind"] == "stdin" and source.get("stored_file")
            ),
            None,
        ),
        "sources": source_records,
        "chunks": [
            {
                "file": chunk["file"],
                "source_kind": chunk["source_kind"],
                "source": chunk["source"],
                "source_path": chunk["source_path"],
                "source_label": chunk["source_label"],
                "part": chunk["part"],
                "part_count": chunk["part_count"],
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"],
                "line_count": chunk["line_count"],
            }
            for chunk in chunks
        ],
    }
    manifest_path = output_dir / PACKAGE_MANIFEST_FILE
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return input_signature
# @cpt-end:cpt-studio-algo-execution-plans-chunk-write:p1:inst-write-package-manifest


# @cpt-begin:cpt-studio-algo-execution-plans-chunk-write:p1:inst-finalize-written-paths
def _finalize_written_paths(
    sources: Sequence[Dict[str, object]],
    chunks: Sequence[Dict[str, object]],
    output_dir: Path,
) -> None:
    for source in sources:
        stored_file = source.get("stored_file")
        if stored_file:
            source["stored_path"] = (output_dir / str(stored_file)).as_posix()
    for chunk in chunks:
        chunk["path"] = (output_dir / str(chunk["file"])).as_posix()
# @cpt-end:cpt-studio-algo-execution-plans-chunk-write:p1:inst-finalize-written-paths


def _build_chunk_records(
    source: Dict[str, object],
    source_index: int,
    lines: List[str],
    ranges: List[Tuple[int, int]],
    staging_dir: Path,
    chunk_index: int,
) -> Tuple[List[Dict[str, object]], int]:
    # @cpt-begin:cpt-studio-algo-execution-plans-chunk-write:p1:inst-write-chunk-file
    chunk_records: List[Dict[str, object]] = []
    total_parts = len(ranges)
    for part_number, (start, end) in enumerate(ranges, start=1):
        selected = lines[start - 1 : end] if end >= start else []
        chunk_text = "\n".join(selected)
        if chunk_text and not chunk_text.endswith("\n"):
            chunk_text += "\n"
        filename = (
            f"{chunk_index:03d}-{source_index:02d}-{source['label']}-"
            f"part-{part_number:02d}.md"
        )
        (staging_dir / filename).write_text(chunk_text, encoding="utf-8")
        chunk_records.append({
            "file": filename,
            "source_kind": source["kind"],
            "source": source["display_name"],
            "source_path": source["path"],
            "source_label": source["label"],
            "part": part_number,
            "part_count": total_parts,
            "start_line": start,
            "end_line": end,
            "line_count": max(0, end - start + 1),
        })
        chunk_index += 1
    return chunk_records, chunk_index
    # @cpt-end:cpt-studio-algo-execution-plans-chunk-write:p1:inst-write-chunk-file


def _swap_chunk_output(output_dir: Path, staging_dir: Path) -> Tuple[Path | None, bool]:
    # @cpt-begin:cpt-studio-algo-execution-plans-chunk-write:p1:inst-clean-stale
    preserve_ok = True
    backup_dir: Path | None = None
    if output_dir.exists():
        backup_dir = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.backup-", dir=output_dir.parent))
        backup_dir.rmdir()
        output_dir.replace(backup_dir)
        try:
            _preserve_non_generated(backup_dir, staging_dir)
        except OSError as exc:
            _warn_chunk_input(
                f"failed to preserve non-generated files from {backup_dir} into {staging_dir}: {exc}"
            )
            backup_dir.replace(output_dir)
            preserve_ok = False
            return backup_dir, preserve_ok
    staging_dir.replace(output_dir)
    return backup_dir, preserve_ok
    # @cpt-end:cpt-studio-algo-execution-plans-chunk-write:p1:inst-clean-stale

# @cpt-begin:cpt-studio-algo-execution-plans-chunk-write:p1:inst-clean-stale
def _cleanup_chunk_swap(backup_dir: Path | None, output_dir: Path, preserve_ok: bool, swap_succeeded: bool) -> None:
    if swap_succeeded and backup_dir is not None and backup_dir.exists():
        if preserve_ok:
            shutil.rmtree(backup_dir, ignore_errors=True)
        return
    if backup_dir is None or not backup_dir.exists() or backup_dir == output_dir:
        return
    if output_dir.exists():
        try:
            _preserve_non_generated(backup_dir, output_dir)
            shutil.rmtree(backup_dir, ignore_errors=True)
        except OSError as exc:
            raise OSError(
                f"failed to restore preserved files from {backup_dir} into {output_dir}: {exc}"
            ) from exc
    # @cpt-end:cpt-studio-algo-execution-plans-chunk-write:p1:inst-clean-stale


def _parse_chunk_args(argv: List[str]):
    # @cpt-begin:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-parse-args
    parser = _ChunkInputArgumentParser(
        prog="chunk-input",
        description=(
            "Chunk workflow input into line-bounded files for plan execution; "
            "use --include-stdin to combine prompt text with file paths"
        ),
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Input file paths. If omitted, read direct prompt text from stdin only.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where chunk files will be written",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_MAX_LINES,
        help=f"Maximum lines per chunk (default: {DEFAULT_MAX_LINES})",
    )
    parser.add_argument(
        "--threshold-lines",
        type=int,
        default=DEFAULT_THRESHOLD_LINES,
        help=(
            "Oversized-input threshold that should force planning "
            f"(default: {DEFAULT_THRESHOLD_LINES})"
        ),
    )
    parser.add_argument(
        "--stdin-label",
        default="direct-input",
        help="Logical source label to use when reading input from stdin",
    )
    parser.add_argument(
        "--include-stdin",
        action="store_true",
        help="When file paths are provided, also read direct prompt text from stdin as an extra input source",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute input signature and source metadata without writing any files",
    )
    return parser.parse_args(argv)
    # @cpt-end:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-parse-args


def _load_chunk_sources(args):
    # @cpt-begin:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-read-sources
    sources = [_read_source(path_str, idx) for idx, path_str in enumerate(args.paths, start=1)]
    if args.paths and args.include_stdin:
        sources.insert(0, _read_stdin_source(args.stdin_label))
    elif not sources:
        sources = [_read_stdin_source(args.stdin_label)]
    return sources
    # @cpt-end:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-read-sources


def _chunk_count(source: Dict[str, object], max_lines: int) -> int:
    line_count = int(source["line_count"])
    return math.ceil(line_count / max_lines) if line_count else 1


def _source_result(source: Dict[str, object], max_lines: int) -> Dict[str, object]:
    return {
        "kind": source["kind"],
        "label": source["label"],
        "display_name": source["display_name"],
        "path": source["path"],
        "stored_path": source.get("stored_path"),
        "line_count": source["line_count"],
        "chunk_count": _chunk_count(source, max_lines),
    }


def _dry_run_result(
    args,
    output_dir: Path,
    sources: Sequence[Dict[str, object]],
    total_lines: int,
) -> Dict[str, object]:
    # @cpt-begin:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-dry-run
    input_signature, _ = _build_input_signature(sources)
    return {
        "status": "OK",
        "dry_run": True,
        "output_dir": output_dir.as_posix(),
        "total_sources": len(sources),
        "total_lines": total_lines,
        "max_lines": args.max_lines,
        "threshold_lines": args.threshold_lines,
        "input_signature": input_signature,
        "plan_required": total_lines > args.threshold_lines,
        "sources": [_source_result(source, args.max_lines) for source in sources],
    }
    # @cpt-end:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-dry-run


def _written_chunk_result(
    args,
    output_dir: Path,
    sources,
    chunks,
    input_signature: str,
    package_manifest: str,
    total_lines: int,
) -> Dict[str, object]:
    # @cpt-begin:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-return-result
    return {
        "status": "OK",
        "output_dir": output_dir.as_posix(),
        "total_sources": len(sources),
        "total_lines": total_lines,
        "max_lines": args.max_lines,
        "threshold_lines": args.threshold_lines,
        "input_signature": input_signature,
        "package_manifest": package_manifest,
        "plan_required": total_lines > args.threshold_lines,
        "direct_prompt_file": next(
            (
                str(source.get("stored_path"))
                for source in sources
                if source["kind"] == "stdin" and source.get("stored_path")
            ),
            None,
        ),
        "chunk_count": len(chunks),
        "chunks": chunks,
        "sources": [_source_result(source, args.max_lines) for source in sources],
    }
    # @cpt-end:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-return-result


def _chunk_input_error(message: str) -> int:
    ui.result({"status": "ERROR", "message": message})
    return 1


def _validate_chunk_threshold_args(args) -> int | None:
    # @cpt-begin:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-evaluate-threshold
    if args.max_lines <= 0:
        return _chunk_input_error("--max-lines must be > 0")
    if args.threshold_lines <= 0:
        return _chunk_input_error("--threshold-lines must be > 0")
    return None
    # @cpt-end:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-evaluate-threshold


def _resolve_chunk_output_dir(output_dir: Path) -> int | None:
    # @cpt-begin:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-prepare-output
    if output_dir.exists() and not output_dir.is_dir():
        return _chunk_input_error(f"--output-dir path exists and is not a directory: {output_dir}")
    return None
    # @cpt-end:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-prepare-output


def _human_dry_chunk_result(data: Dict[str, object]) -> None:
    ui.header("Chunk Input (dry run)")
    ui.info(f"{data['total_sources']} input source(s), {data['total_lines']} lines total")
    ui.detail("input_signature", str(data["input_signature"]))
    ui.detail("plan_required", "yes" if bool(data["plan_required"]) else "no")


def _human_chunk_result(data: Dict[str, object]) -> None:
    ui.header("Chunk Input")
    ui.info(
        f"Prepared {data['chunk_count']} chunk(s) from {data['total_sources']} input source(s) "
        f"({data['total_lines']} lines total)"
    )
    ui.detail("output_dir", str(data["output_dir"]))
    if data.get("direct_prompt_file"):
        ui.detail("direct_prompt_file", str(data["direct_prompt_file"]))
    ui.detail("plan_required", "yes" if bool(data["plan_required"]) else "no")
    for chunk in data["chunks"]:
        ui.file_action(str(chunk["path"]), "created")


# @cpt-begin:cpt-studio-algo-execution-plans-chunk-write:p1:inst-write-chunk-file
def _write_chunks(
    sources: Sequence[Dict[str, object]],
    output_dir: Path,
    max_lines: int,
) -> Tuple[List[Dict[str, object]], str, str]:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=output_dir.parent))
    backup_dir: Path | None = None
    preserve_ok = True
    swap_succeeded = False
    chunks: List[Dict[str, object]] = []
    try:
        _write_special_source_files(sources, staging_dir)
        chunk_index = 1
        for source_index, source in enumerate(sources, start=1):
            text = str(source["text"])
            lines = text.splitlines() if text else []
            chunk_records, chunk_index = _build_chunk_records(
                source,
                source_index,
                lines,
                _chunk_ranges(len(lines), max_lines),
                staging_dir,
                chunk_index,
            )
            chunks.extend(chunk_records)
        input_signature = _write_package_manifest(sources, chunks, staging_dir, max_lines)
        backup_dir, preserve_ok = _swap_chunk_output(output_dir, staging_dir)
        if not preserve_ok:
            raise OSError("failed to preserve non-generated files")
        _finalize_written_paths(sources, chunks, output_dir)
        swap_succeeded = True
        return chunks, input_signature, (output_dir / PACKAGE_MANIFEST_FILE).as_posix()
    except BaseException:
        if backup_dir is not None and backup_dir.exists() and not output_dir.exists():
            backup_dir.replace(output_dir)
        raise
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        _cleanup_chunk_swap(backup_dir, output_dir, preserve_ok, swap_succeeded)
# @cpt-end:cpt-studio-algo-execution-plans-chunk-write:p1:inst-write-chunk-file


def cmd_chunk_input(argv: List[str]) -> int:
    """Chunk workflow input into deterministic files bounded by max lines."""
    # @cpt-begin:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-parse-args
    try:
        args = _parse_chunk_args(argv)
    except ValueError as exc:
        return _chunk_input_error(str(exc))
    # @cpt-end:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-parse-args

    validation_error = _validate_chunk_threshold_args(args)
    if validation_error is not None:
        return validation_error

    # @cpt-begin:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-read-sources
    try:
        sources = _load_chunk_sources(args)
    except (FileNotFoundError, OSError, UnicodeDecodeError, ValueError) as exc:
        return _chunk_input_error(str(exc))
    # @cpt-end:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-read-sources

    # @cpt-begin:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-evaluate-threshold
    total_lines = sum(int(source["line_count"]) for source in sources)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir_error = _resolve_chunk_output_dir(output_dir)
    if output_dir_error is not None:
        return output_dir_error
    # @cpt-end:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-evaluate-threshold

    # @cpt-begin:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-dry-run
    result_rc = 0
    if args.dry_run:
        result = _dry_run_result(args, output_dir, sources, total_lines)
        ui.result(result, human_fn=_human_dry_chunk_result)
    else:
        # @cpt-begin:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-prepare-output
        try:
            chunks, input_signature, package_manifest = _write_chunks(sources, output_dir, args.max_lines)
        except OSError as exc:
            return _chunk_input_error(f"Failed to write chunks: {exc}")
        # @cpt-end:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-prepare-output

        # @cpt-begin:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-return-result
        result = _written_chunk_result(
            args, output_dir, sources, chunks, input_signature, package_manifest, total_lines
        )
        ui.result(result, human_fn=_human_chunk_result)
        # @cpt-end:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-return-result
    # @cpt-end:cpt-studio-flow-execution-plans-chunk-raw-input:p1:inst-dry-run
    return result_rc


__all__ = ["cmd_chunk_input"]
