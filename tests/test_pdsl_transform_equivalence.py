"""
Baseline assertions over PDSL-transformed agent and workflow files.

The goal is to catch future regressions where a PDSL "cleanup" pass drops
behavioral invariants (MUST / MUST_NOT / FORBID / REQUIRE / STOP_TURN /
INVARIANTS clauses). The frozen baseline below was captured at commit
<HEAD>; if a future commit reduces a count below the baseline, the test
fails — prompting the author to confirm the drop is intentional and
update the baseline.

This is a "non-decreasing keyword density" test. It is intentionally
shallow — it does not validate semantic equivalence. For that, run
`cf-pdsl review` interactively against the changed files (see the
optional opt-in test at the bottom).
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_AGENTS = REPO_ROOT / "skills" / "studio" / "agents"

# Frozen baseline of executable-keyword counts per agent file.
# Update only when an intentional rule consolidation lowers a count.
# Format: filename -> {keyword: minimum_count}
BASELINE = {
    "cf-brainstorm-expert": {
        "MUST": 20,
        "MUST_NOT": 11,
        "FORBID": 0,
        "REQUIRE": 2,
        "STOP_TURN": 2,
        "INVARIANTS": 0,
    },
    "cf-code-bug-finder": {
        "MUST": 6,
        "MUST_NOT": 3,
        "FORBID": 2,
        "REQUIRE": 6,
        "STOP_TURN": 1,
        "INVARIANTS": 0,
    },
    "cf-generate-author": {
        "MUST": 18,
        "MUST_NOT": 3,
        "FORBID": 0,
        "REQUIRE": 0,
        "STOP_TURN": 0,
        "INVARIANTS": 0,
    },
    "cf-migrate-migrator": {
        "MUST": 14,
        "MUST_NOT": 15,
        "FORBID": 0,
        "REQUIRE": 0,
        "STOP_TURN": 1,
        "INVARIANTS": 1,
    },
    "cf-pdsl-reviewer": {
        "MUST": 8,
        "MUST_NOT": 4,
        "FORBID": 1,
        "REQUIRE": 0,
        "STOP_TURN": 1,
        "INVARIANTS": 1,
    },
    "cf-semantic-reviewer-code": {
        "MUST": 5,
        "MUST_NOT": 5,
        "FORBID": 0,
        "REQUIRE": 1,
        "STOP_TURN": 1,
        "INVARIANTS": 0,
    },
    "storytelling-gate": {
        "MUST": 54,
        "MUST_NOT": 8,
        "FORBID": 0,
        "REQUIRE": 1,
        "STOP_TURN": 0,
        "INVARIANTS": 1,
    },
    "cf-analyze-planner": {
        "MUST": 18,
        "MUST_NOT": 9,
        "FORBID": 0,
        "REQUIRE": 0,
        "STOP_TURN": 0,
        "INVARIANTS": 0,
    },
}

KEYWORDS = ("MUST", "MUST_NOT", "FORBID", "REQUIRE", "STOP_TURN", "INVARIANTS")


def _count_keywords(text: str) -> dict[str, int]:
    counts = {}
    for kw in KEYWORDS:
        counts[kw] = len(re.findall(rf"\b{re.escape(kw)}\b", text))
    return counts


class TestPDSLTransformEquivalence(unittest.TestCase):
    """Asserts non-decreasing keyword density in PDSL-transformed agents."""

    def test_baseline_files_exist(self):
        for name in BASELINE:
            self.assertTrue(
                (SKILLS_AGENTS / f"{name}.md").exists(),
                f"Baseline agent {name}.md missing from disk",
            )

    def test_keyword_counts_non_decreasing(self):
        for name, floor in BASELINE.items():
            text = (SKILLS_AGENTS / f"{name}.md").read_text(encoding="utf-8")
            actual = _count_keywords(text)
            for kw, min_count in floor.items():
                self.assertGreaterEqual(
                    actual[kw],
                    min_count,
                    f"{name}.md: {kw} count {actual[kw]} below baseline {min_count}. "
                    f"If intentional, lower the baseline and add a comment explaining why.",
                )


# Future enhancement: add an opt-in invocation of `cf-pdsl review` here to
# validate semantic equivalence interactively against changed files.
# This would require a live LLM session and is not suitable for CI regression
# gating, but could be wired in as a separate make target (e.g. make pdsl-review).

if __name__ == "__main__":
    unittest.main()
