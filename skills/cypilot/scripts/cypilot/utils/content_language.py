"""Content language checker for Cypilot artifacts.

Scans Markdown documents for characters outside the allowed Unicode script
ranges.  Used by `cfc validate` (when `allowed_content_languages` is set in
workspace config) and the standalone `cfc check-language` command.

Language policy is configured via a list of language codes such as ["en"] or
["en", "ru"].  Each code maps to one or more Unicode block ranges; characters
outside all allowed ranges are flagged as violations.

@cpt-algo:cpt-cypilot-algo-traceability-validation-lang-scan:p1
"""
# @cpt-begin:cpt-cypilot-algo-traceability-validation-lang-scan:p1:inst-lang-scan-imports
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
# @cpt-end:cpt-cypilot-algo-traceability-validation-lang-scan:p1:inst-lang-scan-imports

# ---------------------------------------------------------------------------
# Unicode script ranges — maps language code → list of (start, end) inclusive
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-cypilot-algo-traceability-validation-lang-scan:p1:inst-script-ranges
SCRIPT_RANGES: Dict[str, List[Tuple[int, int]]] = {
    # Latin (Basic + Extended + Supplement) — always required for English
    "en": [
        (0x0000, 0x007F),   # Basic Latin (ASCII)
        (0x0080, 0x00FF),   # Latin-1 Supplement
        (0x0100, 0x017F),   # Latin Extended-A
        (0x0180, 0x024F),   # Latin Extended-B
        (0x0250, 0x02AF),   # IPA Extensions
        (0x02B0, 0x02FF),   # Spacing Modifier Letters
        (0x0300, 0x036F),   # Combining Diacritical Marks
        (0x2000, 0x206F),   # General Punctuation (em dash, ellipsis …)
        (0x2100, 0x214F),   # Letterlike Symbols (™ © ℗ …)
        (0x2190, 0x21FF),   # Arrows (→ ← ↑ ↓)
        (0x2200, 0x22FF),   # Mathematical Operators
        (0x2500, 0x257F),   # Box Drawing (ASCII diagrams)
        (0x25A0, 0x25FF),   # Geometric Shapes
        (0x2600, 0x26FF),   # Miscellaneous Symbols (✓ ✗)
        (0x2700, 0x27BF),   # Dingbats (✅ ❌)
        (0xFE50, 0xFE6F),   # Small Form Variants
        (0xFF00, 0xFFEF),   # Halfwidth/Fullwidth Forms
    ],
    # Russian / Cyrillic
    "ru": [
        (0x0400, 0x04FF),   # Cyrillic
        (0x0500, 0x052F),   # Cyrillic Supplement
        (0x2DE0, 0x2DFF),   # Cyrillic Extended-A
        (0xA640, 0xA69F),   # Cyrillic Extended-B
    ],
    # Arabic
    "ar": [
        (0x0600, 0x06FF),   # Arabic
        (0x0750, 0x077F),   # Arabic Supplement
        (0xFB50, 0xFDFF),   # Arabic Presentation Forms-A
        (0xFE70, 0xFEFF),   # Arabic Presentation Forms-B
    ],
    # Chinese (CJK)
    "zh": [
        (0x4E00, 0x9FFF),   # CJK Unified Ideographs
        (0x3400, 0x4DBF),   # CJK Extension A
        (0x3000, 0x303F),   # CJK Symbols and Punctuation
    ],
    # Japanese
    "ja": [
        (0x3040, 0x309F),   # Hiragana
        (0x30A0, 0x30FF),   # Katakana
        (0x4E00, 0x9FFF),   # CJK (shared with Chinese)
        (0x3000, 0x303F),   # CJK Symbols
    ],
    # Korean
    "ko": [
        (0xAC00, 0xD7AF),   # Hangul Syllables
        (0x1100, 0x11FF),   # Hangul Jamo
        (0x3130, 0x318F),   # Hangul Compatibility Jamo
    ],
    # Hebrew
    "he": [
        (0x0590, 0x05FF),   # Hebrew
        (0xFB1D, 0xFB4F),   # Hebrew Presentation Forms
    ],
    # Devanagari (Hindi, etc.)
    "hi": [
        (0x0900, 0x097F),   # Devanagari
        (0xA8E0, 0xA8FF),   # Devanagari Extended
    ],
    # Thai
    "th": [
        (0x0E00, 0x0E7F),   # Thai
    ],
    # Georgian
    "ka": [
        (0x10A0, 0x10FF),   # Georgian
        (0x2D00, 0x2D2F),   # Georgian Supplement
    ],
    # Armenian
    "hy": [
        (0x0530, 0x058F),   # Armenian
        (0xFB13, 0xFB17),   # Armenian Ligatures
    ],
}
# @cpt-end:cpt-cypilot-algo-traceability-validation-lang-scan:p1:inst-script-ranges

# Language codes that are recognized by this module.
# @cpt-begin:cpt-cypilot-algo-traceability-validation-lang-scan:p1:inst-supported-langs
SUPPORTED_LANGUAGES: List[str] = sorted(SCRIPT_RANGES.keys())
# @cpt-end:cpt-cypilot-algo-traceability-validation-lang-scan:p1:inst-supported-langs

# Always-allowed: emoji and zero-width / directional markers that are
# language-neutral and widely used in Markdown.
# @cpt-begin:cpt-cypilot-algo-traceability-validation-lang-scan:p1:inst-common-ranges
_COMMON_RANGES: List[Tuple[int, int]] = [
    (0x1F300, 0x1F9FF),  # Emoji (common in Markdown ✅ 🔥)
    (0x200B, 0x200F),    # Zero-width / directional markers
    (0xFEFF, 0xFEFF),    # BOM
]
# @cpt-end:cpt-cypilot-algo-traceability-validation-lang-scan:p1:inst-common-ranges

# ---------------------------------------------------------------------------
# Structural line filters — these lines are always skipped to reduce noise
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-cypilot-algo-traceability-validation-lang-scan:p1:inst-skip-patterns
# Fenced code blocks: lines between ``` or ~~~ are skipped entirely.
_FENCE_START: re.Pattern = re.compile(r"^\s*(`{3,}|~{3,})")

# Lines whose entire content matches one of these patterns are skipped.
_SKIP_LINE_PATTERNS: List[re.Pattern] = [
    re.compile(r"^\s*<!--.*-->"),       # HTML comments (single-line)
    re.compile(r"^\s*\|.*`cpt-.*`"),    # Traceability ID table rows
    re.compile(r"^\s*@cpt"),            # Cypilot markers (@cpt-begin, etc.)
]
# @cpt-end:cpt-cypilot-algo-traceability-validation-lang-scan:p1:inst-skip-patterns

# ---------------------------------------------------------------------------
# Violation
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-cypilot-algo-traceability-validation-lang-scan:p1:inst-violation-datamodel

class LangScanError(Exception):
    """Raised when a file cannot be read for language scanning."""

    def __init__(self, path: Path, cause: Exception) -> None:
        super().__init__(f"Cannot read {path}: {cause}")
        self.path = path
        self.cause = cause


@dataclass
class LangViolation:
    """A single line that contains disallowed characters."""

    path: Path
    lineno: int
    line: str                        # Raw line content (stripped of newline)
    chars: List[Tuple[int, str]]     # (code_point, character) pairs

    def bad_chars_preview(self, limit: int = 8) -> str:
        """Return a short string of the disallowed characters."""
        return "".join(ch for _, ch in self.chars[:limit])

    def line_preview(self, limit: int = 90) -> str:
        """Return a truncated, stripped version of the line for display."""
        s = self.line.strip()
        return s[:limit] + ("…" if len(s) > limit else "")

# @cpt-end:cpt-cypilot-algo-traceability-validation-lang-scan:p1:inst-violation-datamodel

# ---------------------------------------------------------------------------
# Range helpers
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-cypilot-algo-traceability-validation-lang-scan:p1:inst-range-helpers

def _merge_ranges(ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Sort and merge overlapping or adjacent intervals.

    Required so that binary search in is_allowed() works correctly when
    ranges from different language tables overlap or are adjacent.
    """
    if not ranges:
        return []
    sorted_r = sorted(ranges, key=lambda r: r[0])
    merged: List[Tuple[int, int]] = [sorted_r[0]]
    for start, end in sorted_r[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end + 1:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def build_allowed_ranges(languages: List[str]) -> List[Tuple[int, int]]:
    """Merge Unicode ranges for all given language codes into a sorted,
    non-overlapping list suitable for binary search via is_allowed().

    Unknown language codes are silently ignored — callers should validate
    against SUPPORTED_LANGUAGES before calling if they need strict checking.
    """
    ranges: List[Tuple[int, int]] = list(_COMMON_RANGES)
    for lang in languages:
        ranges.extend(SCRIPT_RANGES.get(lang.lower(), []))
    return _merge_ranges(ranges)


def is_allowed(cp: int, ranges: List[Tuple[int, int]]) -> bool:
    """Binary search: return True if code point cp is within any allowed range."""
    lo, hi = 0, len(ranges) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        start, end = ranges[mid]
        if start <= cp <= end:
            return True
        if cp < start:
            hi = mid - 1
        else:
            lo = mid + 1
    return False

# @cpt-end:cpt-cypilot-algo-traceability-validation-lang-scan:p1:inst-range-helpers

# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-cypilot-algo-traceability-validation-lang-scan:p1:inst-scan-file

def scan_file(
    path: Path,
    allowed_ranges: List[Tuple[int, int]],
) -> List[LangViolation]:
    """Scan a single file and return all language violations.

    Fenced code blocks (``` / ~~~) and structural lines (HTML comments,
    traceability table rows, @cpt markers) are automatically skipped.
    """
    violations: List[LangViolation] = []
    in_fence = False

    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        raise LangScanError(path, exc) from exc

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        if _FENCE_START.match(raw_line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if any(p.match(raw_line) for p in _SKIP_LINE_PATTERNS):
            continue

        bad: List[Tuple[int, str]] = [
            (ord(ch), ch)
            for ch in raw_line
            if not is_allowed(ord(ch), allowed_ranges)
        ]
        if bad:
            violations.append(LangViolation(
                path=path,
                lineno=lineno,
                line=raw_line.rstrip("\n"),
                chars=bad,
            ))

    return violations

# @cpt-end:cpt-cypilot-algo-traceability-validation-lang-scan:p1:inst-scan-file

# @cpt-begin:cpt-cypilot-algo-traceability-validation-lang-scan:p1:inst-scan-paths
def scan_paths(
    roots: List[Path],
    allowed_ranges: List[Tuple[int, int]],
    extensions: Optional[List[str]] = None,
    ignore_patterns: Optional[List[str]] = None,
) -> List[LangViolation]:
    """Recursively scan files under the given paths and return all violations.

    Only files whose extensions appear in *extensions* are scanned (default:
    ``[".md"]``).  Files whose path matches any glob in *ignore_patterns*
    (matched against the absolute path string) are skipped — useful for
    translation specs, language-processor test fixtures, or vendor docs.
    """
    import fnmatch

    if extensions is None:
        extensions = [".md"]
    ext_set = {e.lower() for e in extensions}
    ignore_list = list(ignore_patterns) if ignore_patterns else []
    all_violations: List[LangViolation] = []

    def _is_ignored(file_path: Path) -> bool:
        path_str = str(file_path)
        return any(fnmatch.fnmatch(path_str, pat) for pat in ignore_list)

    for root in roots:
        if root.is_file():
            if root.suffix.lower() in ext_set and not _is_ignored(root):
                all_violations.extend(scan_file(root, allowed_ranges))
        elif root.is_dir():
            for file_path in sorted(root.rglob("*")):
                if file_path.suffix.lower() in ext_set and not _is_ignored(file_path):
                    all_violations.extend(scan_file(file_path, allowed_ranges))

    return all_violations

# @cpt-end:cpt-cypilot-algo-traceability-validation-lang-scan:p1:inst-scan-paths


__all__ = [
    "SCRIPT_RANGES",
    "SUPPORTED_LANGUAGES",
    "LangScanError",
    "LangViolation",
    "build_allowed_ranges",
    "is_allowed",
    "scan_file",
    "scan_paths",
]
