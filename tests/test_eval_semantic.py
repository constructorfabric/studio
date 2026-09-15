"""Tests for the semantic-coverage engine (utils.eval_semantic).

The headline is the adversarial pair: a marked block implementing the *wrong* behaviour must be
surfaced as a weak link and judged non-covered, while a faithful implementation must not be
touched by the judge at all. The rest pin the honesty guards: unjudgeable-not-zero, the
evidence (hallucination) guard, defensive degradation, and the advisory-never-gates discipline.
"""
from __future__ import annotations

import random
from pathlib import Path
from typing import Callable, List, Optional

import pytest

from studio.utils import eval_semantic as sem
from studio.utils.eval_semantic import (Pairing, SemanticReply, SemanticReport, assess,
                                        calibrate, coverage_scope, evidence_present, load_gold,
                                        overlap_score, rank_pairings, reference_stub_judge,
                                        resolve_requirement, tokenize)

# A requirement with a clear domain vocabulary, and two code blocks: one faithful, one wrong.
_REQUIREMENT = ("Validate the user email address format and reject a malformed address before "
                "saving the record.")
_CORRECT_CODE = ("def validate_email(address):\n"
                 "    if not email_format(address):\n"
                 "        reject_malformed(address)\n"
                 "    return save_record(address)")
_WRONG_CODE = ("def compute_tax(amount):\n"
               "    rate = lookup_rate(amount)\n"
               "    return amount * rate")


def _pairing(block_id: str, code: str, requirement: Optional[str],
             path: str = "mod.py", start_line: int = 10) -> Pairing:
    return Pairing(block_id=block_id, inst=f"inst-{block_id}", path=path,
                   start_line=start_line, code=code, requirement=requirement)


class _SpyJudge:
    """A judge_fn that records the ids it was asked to judge and returns a fixed verdict."""

    def __init__(self, verdict: str = sem.SEM_WRONG, quote: str = "") -> None:
        self.calls: List[str] = []
        self._verdict = verdict
        self._quote = quote

    def __call__(self, request: sem.SemanticRequest) -> SemanticReply:
        self.calls.append(request.block_id)
        return SemanticReply(self._verdict, "spy", self._quote)


# --- tokenisation + overlap ------------------------------------------------

def test_tokenize_splits_camel_and_snake_and_drops_stopwords() -> None:
    tokens = tokenize("validateEmail user_email and the RECORD")
    assert {"validate", "email", "user", "record"} <= tokens
    assert "and" not in tokens  # stopwords dropped
    assert "the" not in tokens


def test_overlap_below_token_floor_is_none_not_zero() -> None:
    # Too few domain tokens on the requirement side → unjudgeable, never a false 0.
    assert overlap_score(_CORRECT_CODE, "do it") is None


def test_overlap_is_fraction_of_requirement_tokens_present() -> None:
    # Pinned to the exact value — the denominator is the REQUIREMENT token count (not code, not
    # Jaccard). Asserting only >= threshold would not catch a denominator regression.
    assert overlap_score(_CORRECT_CODE, _REQUIREMENT) == 0.7
    # A case where the requirement-denominator and code-denominator answers differ, pinned to the
    # requirement-denominator value (2/4); a code denominator would give 2/7 ~= 0.29.
    assert overlap_score("alpha beta zeta eta theta iota kappa", "alpha beta gamma delta") == 0.5


# --- the adversarial pair (headline) ---------------------------------------

def test_adversarial_wrong_is_flagged_and_correct_is_not_even_judged() -> None:
    spy = _SpyJudge(verdict=sem.SEM_WRONG)
    report = assess([_pairing("correct", _CORRECT_CODE, _REQUIREMENT),
                     _pairing("wrong", _WRONG_CODE, _REQUIREMENT)], judge_fn=spy)
    judged = {f.block_id: f for f in report.findings}
    # The wrong block is surfaced as a weak link and judged; the faithful one is not.
    assert "wrong" in judged
    assert judged["wrong"].verdict == sem.SEM_WRONG
    assert "correct" not in judged
    assert spy.calls == ["wrong"]  # pre-filter-first: no model call on the strong block


def test_prefilter_first_no_model_call_when_all_blocks_are_strong() -> None:
    spy = _SpyJudge()
    report = assess([_pairing("a", _CORRECT_CODE, _REQUIREMENT)], judge_fn=spy)
    assert spy.calls == []
    assert report.findings == []
    assert report.assessed == 0
    # accounted for as presumed-covered, not silently dropped
    assert report.presumed_covered == 1


def test_report_accounts_for_every_in_scope_block() -> None:
    report = assess([_pairing("strong", _CORRECT_CODE, _REQUIREMENT),
                     _pairing("weak", _WRONG_CODE, _REQUIREMENT),
                     _pairing("gap", _WRONG_CODE, None)], judge_fn=_SpyJudge())
    assert report.assessed == 1
    assert report.presumed_covered == 1
    assert len(report.unjudgeable) == 1


# --- honesty: unjudgeable-not-zero -----------------------------------------

def test_missing_requirement_is_unjudgeable_not_judged() -> None:
    report = assess([_pairing("noreq", _WRONG_CODE, None)], judge_fn=_SpyJudge())
    assert report.findings == []
    assert [u.block_id for u in report.unjudgeable] == ["noreq"]
    assert "no retrievable requirement" in report.unjudgeable[0].reason


def test_below_floor_requirement_is_unjudgeable() -> None:
    report = assess([_pairing("tiny", _WRONG_CODE, "do it")], judge_fn=_SpyJudge())
    assert [u.block_id for u in report.unjudgeable] == ["tiny"]


def test_no_judge_wired_makes_every_weak_link_unjudgeable() -> None:
    report = assess([_pairing("wrong", _WRONG_CODE, _REQUIREMENT)], judge_fn=None)
    assert report.findings == []                                     # nothing got a real verdict
    assert any(u.block_id == "wrong" for u in report.unjudgeable)  # surfaced as a coverage gap


# --- the evidence (hallucination) guard ------------------------------------

def test_evidence_present_normalises_whitespace() -> None:
    assert evidence_present("a   b\n c", "a b c")
    assert not evidence_present("real code here", "fabricated quote")
    assert not evidence_present("code", "")  # an empty quote is not evidence


def test_fabricated_quote_sets_evidence_not_ok() -> None:
    spy = _SpyJudge(verdict=sem.SEM_WRONG, quote="this text is not in the code")
    report = assess([_pairing("wrong", _WRONG_CODE, _REQUIREMENT)], judge_fn=spy)
    assert report.findings[0].evidence_ok is False


def test_real_quote_sets_evidence_ok() -> None:
    spy = _SpyJudge(verdict=sem.SEM_WRONG, quote="rate = lookup_rate(amount)")
    report = assess([_pairing("wrong", _WRONG_CODE, _REQUIREMENT)], judge_fn=spy)
    assert report.findings[0].evidence_ok is True


# --- defensive degradation --------------------------------------------------

def test_judge_that_raises_degrades_to_unjudgeable() -> None:
    def boom(_request: sem.SemanticRequest) -> SemanticReply:
        raise RuntimeError("model down")

    report = assess([_pairing("wrong", _WRONG_CODE, _REQUIREMENT)], judge_fn=boom)
    assert report.findings == []
    assert any(u.block_id == "wrong" for u in report.unjudgeable)


@pytest.mark.parametrize("reply", [None, object(), SemanticReply("bogus")])
def test_malformed_reply_is_unjudgeable(reply: object) -> None:
    report = assess([_pairing("wrong", _WRONG_CODE, _REQUIREMENT)],
                    judge_fn=lambda _r: reply)
    assert report.findings == []
    assert any(u.block_id == "wrong" for u in report.unjudgeable)


# --- advisory never gates ---------------------------------------------------

def test_report_carries_no_gate_signal() -> None:
    report = assess([_pairing("wrong", _WRONG_CODE, _REQUIREMENT)],
                    judge_fn=_SpyJudge(sem.SEM_WRONG))
    # A wrong verdict produces a finding but nothing resembling a pass/fail/exit gate.
    assert isinstance(report, SemanticReport)
    assert not any(hasattr(report, attr) for attr in ("gate", "exit_code", "passed"))


# --- the frozen coverage-report scope --------------------------------------

def test_excluded_files_are_skipped_before_ranking() -> None:
    report = assess([_pairing("wrong", _WRONG_CODE, _REQUIREMENT, path="skip.py")],
                    judge_fn=_SpyJudge(),
                    report={"excluded": [{"path": "skip.py", "reason": "x", "declared_by": "config"}]})
    assert report.findings == []
    assert report.unjudgeable == []


def test_whole_file_claims_are_prioritised_in_ranking() -> None:
    weak_plain = _pairing("plain", _WRONG_CODE, _REQUIREMENT, path="plain.py")
    weak_claim = _pairing("claim", _WRONG_CODE, _REQUIREMENT, path="claim.py")
    ranked = rank_pairings([weak_plain, weak_claim], priority_paths=["claim.py"])
    assert ranked[0].pairing.path == "claim.py"  # prioritised file bubbles to the top


def test_report_missing_the_fields_yields_empty_scope() -> None:
    scope = coverage_scope({"some_other_key": 1})
    assert scope.excluded == set()
    assert scope.prioritised == []
    assert coverage_scope(None).excluded == set()  # a None report never errors


# --- the reference stub -----------------------------------------------------

def test_reference_stub_buckets_by_overlap() -> None:
    covered = reference_stub_judge(sem.build_semantic_request(
        sem.Ranked(_pairing("c", _CORRECT_CODE, _REQUIREMENT), 0.0, True, "x")))
    wrong = reference_stub_judge(sem.build_semantic_request(
        sem.Ranked(_pairing("w", _WRONG_CODE, _REQUIREMENT), 0.0, True, "x")))
    assert covered.verdict == sem.SEM_COVERED
    assert wrong.verdict == sem.SEM_WRONG
    assert covered.evidence_quote  # a real line, so the evidence guard can verify it


def test_reference_stub_on_empty_code_is_wrong_with_no_quote() -> None:
    reply = reference_stub_judge(sem.SemanticRequest("e", _REQUIREMENT, "", "prompt"))
    assert reply.verdict == sem.SEM_WRONG
    assert reply.evidence_quote == ""


# --- the requirement resolver ----------------------------------------------

def test_resolve_requirement_reads_scoped_doc(tmp_path: Path) -> None:
    doc = tmp_path / "feature.md"
    doc.write_text("### cpt-studio-algo-demo\nThe demo requirement text.\n", encoding="utf-8")
    assert resolve_requirement(doc, "cpt-studio-algo-demo") == "The demo requirement text."
    assert resolve_requirement(doc, "cpt-studio-algo-absent") is None


# --- gold + calibration -----------------------------------------------------

def test_load_gold_valid_and_malformed(tmp_path: Path) -> None:
    good = tmp_path / "gold.toml"
    good.write_text('[gold]\nverdict = "wrong"\nrationale = "off"\n', encoding="utf-8")
    loaded = load_gold(good)
    assert loaded is not None
    assert loaded.verdict == "wrong"

    bad = tmp_path / "bad.toml"
    bad.write_text('[gold]\nverdict = "nonsense"\n', encoding="utf-8")
    assert load_gold(bad) is None
    assert load_gold(tmp_path / "missing.toml") is None
    assert load_gold(None) is None


def test_calibrate_reports_accuracy_and_consistency() -> None:
    cases = [(_pairing("w", _WRONG_CODE, _REQUIREMENT), sem.SemanticGold("wrong")),
             (_pairing("c", _CORRECT_CODE, _REQUIREMENT), sem.SemanticGold("covered"))]
    result = calibrate(cases, reference_stub_judge, runs=3)
    assert result.accuracy == 1.0            # stub agrees with both human labels
    assert result.consistency == 1.0         # deterministic stub → no run-to-run variance
    assert set(result.covered) == {"w", "c"}


def test_calibrate_empty_is_none_not_zero() -> None:
    result = calibrate([], reference_stub_judge)
    assert result.accuracy is None
    assert result.consistency is None


def test_non_string_verdict_is_unjudgeable_not_raise() -> None:
    # A reply whose verdict is a truthy non-string (e.g. 123) must degrade to unjudgeable, not raise
    # an AttributeError — this runs outside any try/except and calibration calls it directly.
    class _IntVerdict:
        verdict = 123

    assert sem._reply_to_verdict(_IntVerdict()) == sem.SEM_UNJUDGEABLE


def test_calibration_excludes_a_crashing_judge() -> None:
    # A judge_fn that raises is an operational failure, not a disagreement — the case is excluded,
    # not scored as a mismatch, so a transient crash never deflates accuracy.
    def boom(_request: sem.SemanticRequest) -> SemanticReply:
        raise RuntimeError("model down")

    cal = calibrate([(_pairing("c", _WRONG_CODE, _REQUIREMENT), sem.SemanticGold("wrong"))],
                    boom, runs=2)
    assert "c" in cal.excluded
    assert cal.accuracy is None            # the only case crashed → nothing scored
    assert cal.per_case == []


def test_calibration_excludes_an_unscoreable_pairing() -> None:
    # A pairing with no requirement (unjudgeable at the pre-filter) is excluded from calibration,
    # not judged on empty input and scored as a mismatch.
    cal = calibrate([(_pairing("noreq", _WRONG_CODE, None), sem.SemanticGold("wrong"))],
                    reference_stub_judge, runs=2)
    assert "noreq" in cal.excluded
    assert cal.accuracy is None


def test_prompt_fields_are_bounded() -> None:
    # A huge code block must not produce an unbounded prompt; the interpolated fields are capped,
    # while the structured request field stays full for the evidence guard.
    huge = "x = 1\n" * 5000
    req = sem.build_semantic_request(sem.Ranked(_pairing("big", huge, _REQUIREMENT), 0.0, True, "x"))
    assert len(req.prompt) < sem._PROMPT_FIELD_CAP * 3   # bounded, not ~30k
    assert "[…truncated]" in req.prompt
    assert req.code == huge                              # the structured field is not truncated


# --- deep-review hardening (verified findings M1, M2, M3, M5, m2, excluded-count) ---

def test_non_string_evidence_quote_and_rationale_do_not_sink_assessment() -> None:
    # a host returning a non-string evidence_quote/rationale must not crash out of _judge_one
    # (its try only wraps the model call) and sink assess()/calibrate() — degrade the fields.
    class _BadReply:
        verdict = "wrong"
        evidence_quote = 42                 # non-string
        rationale = ["not", "a", "string"]  # non-string

    report = assess([_pairing("wrong", _WRONG_CODE, _REQUIREMENT)], judge_fn=lambda _r: _BadReply())
    assert report.findings[0].verdict == sem.SEM_WRONG       # verdict still parsed, no crash
    assert report.findings[0].evidence_ok is False           # non-string quote is not evidence
    cal = calibrate([(_pairing("w", _WRONG_CODE, _REQUIREMENT), sem.SemanticGold("wrong"))],
                    lambda _r: _BadReply(), runs=2)
    assert cal.accuracy == 1.0                               # scored without raising


def test_calibration_excludes_an_unknown_verdict_reply() -> None:
    # a reply mapping to UNJUDGEABLE for a non-crash reason (unknown verdict) is excluded, not
    # scored as a mismatch that deflates accuracy.
    cal = calibrate([(_pairing("u", _WRONG_CODE, _REQUIREMENT), sem.SemanticGold("wrong"))],
                    lambda _r: SemanticReply("maybe"), runs=2)
    assert "u" in cal.excluded
    assert cal.accuracy is None


def test_calibration_does_not_exclude_a_real_verdict_mentioning_an_error() -> None:
    # a genuine verdict must not be excluded just because its free-text rationale mentions an
    # error phrase — exclusion keys off the verdict, not a rationale substring.
    reply = SemanticReply("wrong", "the branch where judge_fn raised is not covered")
    cal = calibrate([(_pairing("r", _WRONG_CODE, _REQUIREMENT), sem.SemanticGold("wrong"))],
                    lambda _r: reply, runs=2)
    assert cal.excluded == []
    assert cal.accuracy == 1.0


def test_calibration_accuracy_below_one_on_disagreement() -> None:
    # accuracy must be able to fall below 1 — a stub verdict that disagrees with gold is a miss.
    cases = [(_pairing("hit", _WRONG_CODE, _REQUIREMENT), sem.SemanticGold("wrong")),      # stub wrong == gold
             (_pairing("miss", _CORRECT_CODE, _REQUIREMENT), sem.SemanticGold("wrong"))]   # stub covered != gold
    cal = calibrate(cases, reference_stub_judge, runs=2)
    assert cal.accuracy == 0.5
    assert 0.0 < cal.accuracy < 1.0


def test_calibration_consistency_below_one_for_a_flaky_judge() -> None:
    # consistency must be able to fall below 1 — a judge that varies run-to-run.
    calls = {"n": 0}

    def flaky(_request: sem.SemanticRequest) -> SemanticReply:
        calls["n"] += 1
        return SemanticReply("covered" if calls["n"] % 2 else "wrong")

    cal = calibrate([(_pairing("f", _CORRECT_CODE, _REQUIREMENT), sem.SemanticGold("covered"))],
                    flaky, runs=3)
    assert cal.consistency is not None
    assert cal.consistency < 1.0                 # covered, wrong, covered → majority 2/3


def test_reference_stub_partial_bucket() -> None:
    # a mid-overlap block (~0.2, in [threshold/2, threshold)) buckets to PARTIAL.
    partial_code = "def validate_thing(item):\n    email_field = item\n    return compute_other(item)"
    req = sem.build_semantic_request(sem.Ranked(_pairing("p", partial_code, _REQUIREMENT), 0.2, True, "x"))
    assert reference_stub_judge(req).verdict == sem.SEM_PARTIAL


def test_report_counts_excluded_file_blocks() -> None:
    # excluded-count: blocks in a human-excluded file are counted (skipped_excluded), not dropped.
    report = assess([_pairing("keep", _WRONG_CODE, _REQUIREMENT, path="keep.py"),
                     _pairing("s1", _WRONG_CODE, _REQUIREMENT, path="skip.py"),
                     _pairing("s2", _WRONG_CODE, _REQUIREMENT, path="skip.py")],
                    judge_fn=_SpyJudge(sem.SEM_WRONG),
                    report={"excluded": [{"path": "skip.py"}]})
    assert report.skipped_excluded == 2
    assert report.assessed == 1                  # only the kept block was judged


# --- deep-review round 2 (M1 design fix, M2 crash, M3 minority-unjudgeable, M5 accounting) ---

def test_whole_file_claim_block_is_always_judged_despite_high_overlap() -> None:
    # a whole_file_claims (prioritised) file's overlap is untrustworthy — a high-overlap block
    # there must be JUDGED, not waved through as presumed_covered (the engine's headline purpose).
    spy = _SpyJudge(sem.SEM_WRONG)
    report = assess([_pairing("claim", _CORRECT_CODE, _REQUIREMENT, path="claim.py")],
                    judge_fn=spy, report={"whole_file_claims": [{"path": "claim.py"}]})
    assert spy.calls == ["claim"]                       # judged despite overlap 0.7 (would be strong)
    assert report.presumed_covered == 0
    assert [f.verdict for f in report.findings] == [sem.SEM_WRONG]


def test_load_gold_non_string_verdict_returns_none_not_raise(tmp_path: Path) -> None:
    # a TOML array/table verdict is unhashable; load_gold must return None, never raise.
    for bad in ('verdict = ["wrong"]', 'verdict = { x = 1 }'):
        p = tmp_path / "g.toml"
        p.write_text(f"[gold]\n{bad}\n", encoding="utf-8")
        assert load_gold(p) is None


def test_calibration_minority_unjudgeable_does_not_deflate_consistency() -> None:
    # one transient crash among good runs must not deflate consistency or flip the exclude
    # decision — UNJUDGEABLE runs are dropped before majority/consistency.
    calls = {"n": 0}

    def flaky(_request: sem.SemanticRequest) -> SemanticReply:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")             # only the first run fails
        return SemanticReply("wrong")

    cal = calibrate([(_pairing("m", _WRONG_CODE, _REQUIREMENT), sem.SemanticGold("wrong"))],
                    flaky, runs=3)
    assert cal.excluded == []                           # a real verdict was produced → scored
    assert cal.accuracy == 1.0
    assert cal.consistency == 1.0                       # over the 2 real runs, both agreed


def test_assess_covered_verdict_lands_in_findings() -> None:
    # a weak link the judge rules COVERED must land in findings with a real verdict, not vanish
    # from every accounting bucket (it is not UNJUDGEABLE and was not presumed_covered).
    report = assess([_pairing("w", _WRONG_CODE, _REQUIREMENT)], judge_fn=_SpyJudge(sem.SEM_COVERED))
    assert [f.verdict for f in report.findings] == [sem.SEM_COVERED]
    assert report.assessed == 1


def test_assess_accounting_identity_holds() -> None:
    # every pairing is accounted for exactly once across the four buckets.
    pairings = [_pairing("strong", _CORRECT_CODE, _REQUIREMENT),
                _pairing("weak", _WRONG_CODE, _REQUIREMENT),
                _pairing("gap", _WRONG_CODE, None),
                _pairing("skip", _WRONG_CODE, _REQUIREMENT, path="x.py")]
    report = assess(pairings, judge_fn=_SpyJudge(sem.SEM_PARTIAL),
                    report={"excluded": [{"path": "x.py"}]})
    assert (report.assessed + report.presumed_covered
            + len(report.unjudgeable) + report.skipped_excluded) == len(pairings)


def test_majority_of_empty_is_unjudgeable() -> None:
    # Defensive: _majority over no verdicts is UNJUDGEABLE with count 0, never an error.
    assert sem._majority([]) == (sem.SEM_UNJUDGEABLE, 0)


# --- deep-review round 3 (M2 comment inflation, m2 effective-n, m3 unicode, m5/i2 gaps) ---

def test_comment_echoing_requirement_does_not_mask_wrong_code() -> None:
    # a comment/docstring that restates the requirement must NOT inflate overlap and wave the
    # block through as presumed_covered — comments/strings are stripped before scoring, so wrong
    # code beneath a requirement-echoing comment is still surfaced as a weak link and judged.
    echoed = ('def compute_tax(amount):\n'
              '    # Validate the user email address format and reject a malformed address'
              ' before saving the record.\n'
              '    """Validate the user email address format and reject a malformed address."""\n'
              '    return amount * lookup_rate(amount)')
    score = overlap_score(echoed, _REQUIREMENT)
    assert score is not None                          # enough executable tokens to compare
    assert score < sem._WEAK_LINK_THRESHOLD           # not inflated by the echoing prose
    spy = _SpyJudge(sem.SEM_WRONG)
    report = assess([_pairing("masked", echoed, _REQUIREMENT)], judge_fn=spy)
    assert spy.calls == ["masked"]                    # judged, not presumed_covered
    assert report.presumed_covered == 0


def test_tokenize_keeps_non_ascii_terms_whole() -> None:
    # non-ASCII terms must stay whole, not fragment to empty — an ASCII-only split deflated the
    # pre-filter and could report a real multilingual block UNJUDGEABLE.
    assert "gebühr" in tokenize("Berechne die Gebühr")   # not {'geb', 'hr'}
    cyrillic = tokenize("проверить адрес электронной почты")
    assert cyrillic                                      # non-empty, not fragmented below the floor
    assert "адрес" in cyrillic


def test_single_surviving_run_is_unmeasurable_for_both_accuracy_and_consistency() -> None:
    # when only one run survives (others crashed), BOTH accuracy and consistency are
    # unmeasurable → None. Scoring the lone survivor for accuracy would let a transient crash flip an
    # excluded tie into a hit/miss, so the case feeds neither denominator (symmetric gate).
    calls = {"n": 0}

    def mostly_down(_request: sem.SemanticRequest) -> SemanticReply:
        calls["n"] += 1
        if calls["n"] == 1:
            return SemanticReply("wrong")               # exactly one real verdict
        raise RuntimeError("down")

    cal = calibrate([(_pairing("s", _WRONG_CODE, _REQUIREMENT), sem.SemanticGold("wrong"))],
                    mostly_down, runs=3)
    assert cal.excluded == []                           # a real verdict was produced → in per_case
    assert cal.accuracy is None                         # one survivor → accuracy unmeasurable
    assert cal.consistency is None                      # one survivor → consistency unmeasurable
    assert cal.per_case[0]["runs_effective"] == 1
    assert cal.per_case[0]["matched"] is None
    assert cal.per_case[0]["consistency"] is None


def test_majority_tie_break_is_canonical_not_first_seen() -> None:
    # ties resolve by sorted verdict name (covered < partial < wrong), independent of run
    # order — a regression to the sibling judge's first-seen tie-break would pass every other test.
    assert sem._majority(["wrong", "covered"]) == ("covered", 1)
    assert sem._majority(["covered", "wrong"]) == ("covered", 1)
    assert sem._majority(["wrong", "partial"]) == ("partial", 1)


def test_overlap_below_code_token_floor_is_none() -> None:
    # the CODE side of the token floor is exercised directly — below-floor code is unjudgeable
    # (None), not a judged weak link. Deleting the code-side guard would otherwise pass every test.
    assert overlap_score("a b", _REQUIREMENT) is None   # 0 domain tokens on the code side
    assert overlap_score("", _REQUIREMENT) is None


# --- deep-review round 4 (F1 escape-aware strip, F2 gold-independent tie) ---

def test_escaped_quote_string_literal_does_not_leak_requirement_text() -> None:
    # A string literal that OPENS with an escaped quote and restates the requirement must be fully
    # stripped from the overlap view, not leak its words into code_tokens. _code_views blanks each
    # STRING token wholesale via the grammar-aware tokenizer, so an escaped internal quote is a
    # non-issue (it is one token) — where the old escape-aware regex could have ended the literal early.
    leaky = ('def compute_tax(amount):\n'
             '    ERR = "\\"validate the user email address format and reject a malformed address\\""\n'
             '    return amount * lookup_rate(amount)')
    score = overlap_score(leaky, _REQUIREMENT)
    assert score is not None
    assert score < sem._WEAK_LINK_THRESHOLD            # requirement words stripped, not leaked
    spy = _SpyJudge(sem.SEM_WRONG)
    report = assess([_pairing("leaky", leaky, _REQUIREMENT)], judge_fn=spy)
    assert spy.calls == ["leaky"]                      # judged, not presumed_covered
    assert report.presumed_covered == 0


def test_strict_tie_is_gold_independent_and_excluded_from_accuracy() -> None:
    # a strict tie (no majority) must not be scored by the gold label's alphabetical rank. It is
    # excluded from accuracy (matched=None) — the SAME result whether gold is 'wrong' or 'covered' —
    # while its low consistency is still reported. Previously a 1-1 tie was a forced miss on 'wrong'.
    calls = {"n": 0}

    def split(_request: sem.SemanticRequest) -> SemanticReply:
        calls["n"] += 1
        return SemanticReply("covered" if calls["n"] % 2 else "wrong")   # covered, wrong → 1-1 tie

    cal_wrong = calibrate([(_pairing("t", _CORRECT_CODE, _REQUIREMENT), sem.SemanticGold("wrong"))],
                          split, runs=2)
    assert cal_wrong.accuracy is None                  # no majority → unmeasurable, not a miss
    assert cal_wrong.consistency == 0.5                # 1 of 2 agreed → reported honestly
    assert cal_wrong.per_case[0]["matched"] is None
    cal_covered = calibrate([(_pairing("t", _CORRECT_CODE, _REQUIREMENT), sem.SemanticGold("covered"))],
                            split, runs=2)
    assert cal_covered.accuracy is None                # identical result — gold label does not decide


# --- property-based invariants (seed-deterministic; generated inputs the examples never picked) ---

# Deliberately mixes ASCII, snake/camelCase, non-ASCII (Gebühr, Cyrillic), and the noise that
# _code_views must survive: comments, plain strings, and escaped-quote string literals.
_VOCAB = ["validate", "email", "address", "reject", "malformed", "save", "record", "compute",
          "tax", "amount", "rate", "lookup", "user", "format", "checkUser", "reject_all",
          "Gebühr", "проверить", "адрес"]


def _rand_words(rng: random.Random, n: int) -> str:
    return " ".join(rng.choice(_VOCAB) for _ in range(n))


def _rand_code(rng: random.Random) -> str:
    """Generate a code-like block: statements, comments, plain + escaped-quote string literals,
    docstrings, and blanks — the shapes _code_views and tokenize must handle without raising."""
    lines = ["def f():"]
    for _ in range(rng.randint(0, 7)):
        kind = rng.randint(0, 4)
        if kind == 0:
            lines.append(f"    {rng.choice(_VOCAB)}_{rng.choice(_VOCAB)} = {rng.randint(0, 9)}")
        elif kind == 1:
            lines.append(f"    # {_rand_words(rng, rng.randint(1, 5))}")
        elif kind == 2:
            quote = rng.choice(['"', "'"])
            esc = rng.choice(["", "\\" + quote])         # sometimes open with an escaped quote
            lines.append(f"    ERR = {quote}{esc}{_rand_words(rng, rng.randint(1, 4))}{esc}{quote}")
        elif kind == 3:
            lines.append(f'    """{_rand_words(rng, rng.randint(1, 4))}"""')
        else:
            lines.append("")
    return "\n".join(lines)


def _raises(_request: sem.SemanticRequest) -> SemanticReply:
    raise ValueError("model down")


class _HostileReply:
    """A reply whose attribute access itself raises — the fail-safe boundary must absorb it."""

    @property
    def verdict(self) -> str:
        raise RuntimeError("lazy parse failed")


def _judges(rng: random.Random) -> List[Optional[Callable[[sem.SemanticRequest], object]]]:
    """The full spread of judge behaviours a host might supply — none may make assess/calibrate raise."""
    verdicts = [sem.SEM_COVERED, sem.SEM_PARTIAL, sem.SEM_WRONG, "maybe", ""]
    return [None, reference_stub_judge, _SpyJudge(), _raises,
            lambda _r: _HostileReply(),
            lambda _r: SemanticReply(rng.choice(verdicts))]


def test_property_overlap_score_is_bounded_or_none() -> None:
    rng = random.Random(1234)
    for _ in range(400):
        score = overlap_score(_rand_code(rng), _rand_words(rng, rng.randint(0, 8)))
        assert score is None or (isinstance(score, float) and 0.0 <= score <= 1.0)


def test_property_tokenize_drops_short_and_stopwords_and_is_deterministic() -> None:
    rng = random.Random(5678)
    for _ in range(400):
        text = _rand_code(rng) if rng.random() < 0.5 else _rand_words(rng, rng.randint(0, 10))
        tokens = tokenize(text)
        assert tokens == tokenize(text)                          # deterministic
        assert all(len(t) > 1 and t not in sem._STOPWORDS for t in tokens)


def test_property_assess_never_raises_and_accounting_identity_holds() -> None:
    rng = random.Random(9012)
    for _ in range(300):
        n = rng.randint(0, 6)
        pairings = [
            Pairing(block_id=f"b{i}", inst=f"inst-{i}", path=f"p{rng.randint(0, 3)}.py",
                    start_line=rng.randint(1, 99), code=_rand_code(rng),
                    requirement=(None if rng.random() < 0.2 else _rand_words(rng, rng.randint(0, 8))))
            for i in range(n)]
        paths = [p.path for p in pairings]
        report = {"excluded": [{"path": p} for p in paths if rng.random() < 0.25],
                  "whole_file_claims": [{"path": p} for p in paths if rng.random() < 0.25]}
        judge = rng.choice(_judges(rng))
        result = assess(pairings, judge_fn=judge, report=report)   # must not raise
        assert (result.assessed + result.presumed_covered
                + len(result.unjudgeable) + result.skipped_excluded) == n
        assert all(f.verdict in sem._MODEL_VERDICTS for f in result.findings)


def test_property_calibrate_never_raises_and_metrics_are_bounded() -> None:
    rng = random.Random(3456)
    for _ in range(300):
        cases = [
            (Pairing(block_id=f"c{i}", inst=f"inst-{i}", path="m.py", start_line=i + 1,
                     code=_rand_code(rng),
                     requirement=(None if rng.random() < 0.2 else _rand_words(rng, rng.randint(0, 8)))),
             sem.SemanticGold(rng.choice([sem.SEM_COVERED, sem.SEM_PARTIAL, sem.SEM_WRONG])))
            for i in range(rng.randint(0, 4))]
        judge = rng.choice([j for j in _judges(rng) if j is not None])
        cal = calibrate(cases, judge, runs=rng.randint(1, 4))       # must not raise
        for metric in (cal.accuracy, cal.consistency):
            assert metric is None or 0.0 <= metric <= 1.0
        assert len(cal.covered) == len(cases)


# --- deep-review round 5 (ainetx: evidence-strip, forced, precedence, gap start_line, path norm) ---

def test_evidence_quote_matching_only_a_comment_is_not_evidence() -> None:
    # the hallucination guard strips comments/strings like overlap_score, so a quote
    # that occurs only in a comment (not executable code) sets evidence_ok=False.
    code = ('def compute_tax(amount):\n'
            '    # validate the user email address and reject malformed input\n'
            '    result = lookup_rate(amount)\n'
            '    return result * amount')
    spy = _SpyJudge(verdict=sem.SEM_WRONG, quote="validate the user email address")
    report = assess([_pairing("masked", code, _REQUIREMENT)], judge_fn=spy)
    assert spy.calls == ["masked"]                       # judged (low overlap on executable tokens)
    assert report.findings[0].evidence_ok is False       # quote lived only in the comment


def test_whole_file_claim_finding_is_marked_forced() -> None:
    # a judgment forced by a whole_file_claim carries forced=True; an ordinary
    # weak-link judgment carries forced=False, so a report consumer can tell them apart.
    spy = _SpyJudge(sem.SEM_WRONG)
    report = assess([_pairing("claim", _CORRECT_CODE, _REQUIREMENT, path="claim.py"),
                     _pairing("weak", _WRONG_CODE, _REQUIREMENT, path="plain.py")],
                    judge_fn=spy, report={"whole_file_claims": [{"path": "claim.py"}]})
    by_id = {f.block_id: f for f in report.findings}
    assert by_id["claim"].forced is True
    assert by_id["weak"].forced is False


def test_excluded_takes_precedence_over_whole_file_claims() -> None:
    # a path in BOTH excluded and whole_file_claims is dropped (exclusion is the
    # human override, applied before ranking).
    spy = _SpyJudge(sem.SEM_WRONG)
    report = assess([_pairing("both", _WRONG_CODE, _REQUIREMENT, path="both.py")],
                    judge_fn=spy,
                    report={"excluded": [{"path": "both.py"}],
                            "whole_file_claims": [{"path": "both.py"}]})
    assert spy.calls == []                    # never judged — excluded wins
    assert report.skipped_excluded == 1


def test_unjudgeable_gap_is_typed_and_carries_start_line() -> None:
    # a coverage gap is a typed SemanticGap with start_line, located like a finding.
    report = assess([_pairing("noreq", _WRONG_CODE, None, start_line=42)], judge_fn=_SpyJudge())
    gap = report.unjudgeable[0]
    assert isinstance(gap, sem.SemanticGap)
    assert (gap.block_id, gap.start_line) == ("noreq", 42)


def test_scope_paths_match_across_separator_style() -> None:
    # a report path in Windows separators matches a pairing path in POSIX separators;
    # scope comparison is separator-normalised.
    spy = _SpyJudge(sem.SEM_WRONG)
    report = assess([_pairing("x", _WRONG_CODE, _REQUIREMENT, path="pkg/mod.py")],
                    judge_fn=spy, report={"excluded": [{"path": "pkg\\mod.py"}]})
    assert report.skipped_excluded == 1       # matched despite backslash vs forward-slash


# --- deep-review round 5b (ainetx: gold-log, schema version, judge id, boundaries, formula/oracle) ---

def test_missing_gold_file_is_logged(tmp_path: Path, caplog) -> None:
    # a missing gold file (the common misconfiguration) is logged, not silently None.
    import logging
    with caplog.at_level(logging.WARNING):
        assert load_gold(tmp_path / "nope.toml") is None
    assert any("gold file not found" in r.message for r in caplog.records)


def test_report_and_calibration_carry_schema_version() -> None:
    # the consumed report shapes carry a schema-version discriminator.
    report = assess([_pairing("w", _WRONG_CODE, _REQUIREMENT)], judge_fn=_SpyJudge())
    assert report.schema_version == sem.SEMANTIC_SCHEMA_VERSION
    cal = calibrate([(_pairing("w", _WRONG_CODE, _REQUIREMENT), sem.SemanticGold("wrong"))],
                    reference_stub_judge, runs=3)
    assert cal.schema_version == sem.SEMANTIC_SCHEMA_VERSION


def test_calibration_records_runs_and_judge_identity() -> None:
    # runs_per_scenario is asserted, and the calibration records
    # which judge produced it.
    cal = calibrate([(_pairing("w", _WRONG_CODE, _REQUIREMENT), sem.SemanticGold("wrong"))],
                    reference_stub_judge, runs=3)
    assert cal.runs_per_scenario == 3
    assert cal.judge == "reference_stub_judge"


def test_weak_link_threshold_boundary_is_strong_not_weak() -> None:
    # a block scoring EXACTLY the threshold (0.30) is strong (score < threshold is
    # strict), so it is presumed-covered, not judged.
    req = "alpha beta gamma delta epsilon zeta eta theta iota kappa"    # 10 domain tokens
    code = "alpha beta gamma lorem ipsum dolor"                          # shares exactly 3 → 0.30
    assert overlap_score(code, req) == 0.30
    spy = _SpyJudge(sem.SEM_WRONG)
    report = assess([_pairing("edge", code, req)], judge_fn=spy)
    assert spy.calls == []                     # not a weak link at the exact boundary
    assert report.presumed_covered == 1


def test_min_tokens_floor_boundary_and_distinct_reasons() -> None:
    # exactly _MIN_TOKENS (4) is sufficient; 3 is below the floor (None). And the
    # "below floor" gap reason stays distinct from the "no requirement" gap reason.
    assert overlap_score("alpha beta gamma delta", "alpha beta gamma delta") is not None  # 4 tokens
    assert overlap_score("alpha beta gamma", "alpha beta gamma") is None                  # 3 tokens
    reason_noreq = assess([_pairing("nr", _WRONG_CODE, None)]).unjudgeable[0].reason
    reason_floor = assess([_pairing("tf", "a b", "c d")]).unjudgeable[0].reason
    assert reason_noreq != reason_floor
    assert "requirement" in reason_noreq
    assert "floor" in reason_floor


# --- deep-review round 5c (review pass: strip-policy split + calibration symmetry) ---

def test_evidence_quote_of_a_real_string_literal_is_accepted() -> None:
    # a quote of an inline string literal the code executes (an error message) IS evidence
    # — evidence_present strips comments/docstrings but keeps string-literal contents.
    code = ('def compute_tax(amount):\n'
            '    if amount < 0:\n'
            '        raise ValueError("amount must be positive")\n'
            '    return amount * lookup_rate(amount)')
    spy = _SpyJudge(verdict=sem.SEM_WRONG, quote='raise ValueError("amount must be positive")')
    report = assess([_pairing("s", code, _REQUIREMENT)], judge_fn=spy)
    assert spy.calls == ["s"]                              # low overlap → judged
    assert report.findings[0].evidence_ok is True         # real string quote survives the strip


def test_reference_stub_grounds_its_quote_on_executable_code() -> None:
    # on a block whose COMMENT echoes the requirement, the stub picks an executable line
    # (not the comment), so its own evidence_ok is True — it keeps its "verifiable quote" promise.
    code = ('def compute_tax(amount):\n'
            '    # validate the user email address and reject malformed input before saving\n'
            '    return compute(amount)')
    req = sem.build_semantic_request(sem.Ranked(_pairing("c", code, _REQUIREMENT), 0.1, True, "x"))
    reply = reference_stub_judge(req)
    assert evidence_present(code, reply.evidence_quote) is True   # quote is real code, guard accepts
    assert "validate" not in reply.evidence_quote                 # not the requirement-echoing comment


def test_transient_crash_does_not_flip_accuracy_via_lone_survivor() -> None:
    # a 1-1 tie is excluded from accuracy (None); if a transient crash drops it to a single
    # survivor, accuracy must STILL be None — not flip to a hit/miss by which run happened to crash.
    tie_calls = {"n": 0}

    def split(_r: sem.SemanticRequest) -> SemanticReply:
        tie_calls["n"] += 1
        return SemanticReply("wrong" if tie_calls["n"] % 2 else "partial")

    tie = calibrate([(_pairing("t", _WRONG_CODE, _REQUIREMENT), sem.SemanticGold("wrong"))],
                    split, runs=2)
    assert tie.accuracy is None                     # 1-1 tie → excluded from accuracy

    crash_calls = {"n": 0}

    def split_crash(_r: sem.SemanticRequest) -> SemanticReply:
        crash_calls["n"] += 1
        if crash_calls["n"] == 1:
            return SemanticReply("partial")
        raise RuntimeError("down")

    lone = calibrate([(_pairing("t", _WRONG_CODE, _REQUIREMENT), sem.SemanticGold("wrong"))],
                     split_crash, runs=2)
    assert lone.accuracy is None                    # lone survivor → still unmeasurable, no flip


# --- deep-review round 6 (grammar-aware lexing: docstring-leak, #-in-string, runs=1 accuracy) ---

def test_triple_quote_inside_comment_does_not_leak_docstring_into_overlap() -> None:
    # a stray triple-quote inside a comment must NOT mis-pair with a real docstring and
    # leak its requirement-echoing body into overlap. The wrong block stays a weak link (judged), not
    # a false presumed_covered; a docstring-only quote is not evidence. (The old regex strip leaked.)
    code = ('def compute_tax(amount):\n'
            '    # prefer """ here\n'
            '    """Validate the user email address format and reject a malformed address before saving."""\n'
            '    return amount * lookup_rate(amount)')
    assert overlap_score(code, _REQUIREMENT) < sem._WEAK_LINK_THRESHOLD   # docstring did NOT leak
    spy = _SpyJudge(sem.SEM_WRONG, quote="Validate the user email address format")
    report = assess([_pairing("leak", code, _REQUIREMENT)], judge_fn=spy)
    assert report.presumed_covered == 0                # judged, not waved through as covered
    assert report.findings[0].evidence_ok is False     # docstring-only quote is not evidence


def test_hash_inside_a_string_literal_does_not_truncate_evidence() -> None:
    # a '#' inside a kept string literal must not be read as a comment and truncate the
    # evidence haystack — a verbatim quote of that string is still valid evidence.
    code = ('def pick_color(kind):\n'
            '    if kind < 0:\n'
            '        raise ValueError("bad #tag for color #FF0000")\n'
            '    return compute(kind)')
    spy = _SpyJudge(sem.SEM_WRONG, quote='raise ValueError("bad #tag for color #FF0000")')
    report = assess([_pairing("c", code, _REQUIREMENT)], judge_fn=spy)
    assert report.findings[0].evidence_ok is True      # the #-bearing string survived the strip


def test_calibrate_runs_one_scores_accuracy() -> None:
    # runs=1 is a supported input; a single clean verdict has a trivial majority and DOES
    # score accuracy (consistency stays None — repeatability is unmeasurable with one run).
    cal = calibrate([(_pairing("w", _WRONG_CODE, _REQUIREMENT), sem.SemanticGold("wrong"))],
                    reference_stub_judge, runs=1)
    assert cal.accuracy == 1.0        # the one clean verdict matched gold
    assert cal.consistency is None    # one run → repeatability unmeasurable


def test_untokenizable_fragment_falls_back_without_raising() -> None:
    # a mid-file fragment that won't tokenize (an unterminated string) must not
    # raise — overlap falls back to a comment strip, evidence to raw code. Advisory and safe.
    fragment = 'x = "unterminated\n    y = compute(the_user_email_address)  # note'
    score = overlap_score(fragment, _REQUIREMENT)         # must not raise
    assert score is None or (isinstance(score, float) and 0.0 <= score <= 1.0)
    assert evidence_present(fragment, "y = compute(the_user_email_address)") is True  # raw fallback


# --- deep-review round 7 (line-offset table must match the tokenizer's \n-only line splitting) ---

def test_line_boundary_char_does_not_desync_evidence_view() -> None:
    # the offset table feeds the evidence view; a docstring after a form-feed page
    # break must still be blanked (str.splitlines() breaks on \x0c but the tokenizer does not, so a
    # mismatched table would leave the docstring un-blanked and accept a docstring-only quote).
    code = ('def compute_tax(amount):\n'
            '\x0c\n'                                    # a form-feed page break (PEP 8 convention)
            '    """validate the user email address and reject malformed input"""\n'
            '    return amount * lookup_rate(amount)')
    spy = _SpyJudge(sem.SEM_WRONG, quote="validate the user email address")
    report = assess([_pairing("d", code, _REQUIREMENT)], judge_fn=spy)
    assert spy.calls == ["d"]                           # judged (docstring blanked → low overlap)
    assert report.findings[0].evidence_ok is False      # docstring-only quote is not evidence


def test_many_line_boundary_chars_do_not_leak_comment_into_overlap() -> None:
    # enough boundary chars before a requirement-echoing comment would, under the old
    # str.splitlines() table, desync spans and leak the comment into the overlap view → false
    # presumed_covered. With the \n-matched table the comment stays blanked and the block is judged.
    breaks = "\x0c\n" * 40
    code = ('def compute_tax(amount):\n'
            + breaks +
            '    # validate the user email address format reject malformed address saving record\n'
            '    return amount * lookup_rate(amount)')
    assert overlap_score(code, _REQUIREMENT) < sem._WEAK_LINK_THRESHOLD   # comment did not leak
    spy = _SpyJudge(sem.SEM_WRONG)
    report = assess([_pairing("ff", code, _REQUIREMENT)], judge_fn=spy)
    assert report.presumed_covered == 0                 # judged, not waved through


def test_dedented_statement_leading_string_is_not_evidence() -> None:
    # a statement-leading string after a DEDENT is a bare string statement (prose),
    # not executable logic — _STATEMENT_START includes DEDENT so it is blanked from the evidence view,
    # and a quote lifted only from it is not accepted as evidence.
    code = ('def compute_tax(amount):\n'
            '    total = amount * 2\n'
            '"""validate the user email address and reject malformed input"""\n'
            'result = total')
    spy = _SpyJudge(sem.SEM_WRONG, quote="validate the user email address")
    report = assess([_pairing("d", code, _REQUIREMENT)], judge_fn=spy)
    assert spy.calls == ["d"]                       # judged (all strings blanked from overlap)
    assert report.findings[0].evidence_ok is False  # dedented bare string is not evidence


def test_fstring_prose_does_not_inflate_overlap() -> None:
    # PEP 701: on Python 3.12+ an f-string tokenizes to FSTRING_START/MIDDLE/END, not one STRING
    # token. The literal text must still be blanked from overlap, so a requirement-echoing f-string
    # cannot mask wrong code as presumed_covered.
    code = ('def compute_tax(amount):\n'
            '    log(f"validate the user email address and reject malformed address before saving")\n'
            '    return amount * 2')
    assert overlap_score(code, _REQUIREMENT) < sem._WEAK_LINK_THRESHOLD   # f-string prose blanked
    spy = _SpyJudge(sem.SEM_WRONG)
    report = assess([_pairing("f", code, _REQUIREMENT)], judge_fn=spy)
    assert report.presumed_covered == 0            # judged, not waved through as covered


def test_present_but_unreadable_gold_file_is_logged(tmp_path: Path, caplog) -> None:
    # A gold file that exists but fails to parse (case B) is logged as unexpected, not silently None.
    import logging
    bad = tmp_path / "g.toml"
    bad.write_text("not = valid = toml [[[", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="studio.utils.eval_semantic"):
        assert load_gold(bad) is None
    assert any("present but unreadable" in r.message for r in caplog.records)


def test_calibrating_against_reference_stub_warns(caplog) -> None:
    # The stub re-uses the pre-filter's own overlap; calibrating against it is warned at runtime so a
    # caller who skipped the docstring still sees the numbers are not judge quality.
    import logging
    with caplog.at_level(logging.WARNING, logger="studio.utils.eval_semantic"):
        calibrate([(_pairing("w", _WRONG_CODE, _REQUIREMENT), sem.SemanticGold("wrong"))],
                  reference_stub_judge, runs=2)
    assert any("reference_stub_judge" in r.message for r in caplog.records)


def test_untokenizable_block_with_requirement_echoing_string_is_not_presumed_covered() -> None:
    # A block that fails to tokenize (unterminated string) must not let a requirement-echoing STRING
    # inflate overlap into a false presumed_covered — the fallback can't strip strings, so an
    # unlexable block is unjudgeable (None), never presumed_covered.
    frag = ('def compute_tax(amount):\n'
            '    msg = "validate the user email address and reject a malformed address before saving\n'
            '    return amount * 2')
    assert overlap_score(frag, _REQUIREMENT) is None       # unlexable → unjudgeable, not inflated
    spy = _SpyJudge(sem.SEM_WRONG)
    report = assess([_pairing("frag", frag, _REQUIREMENT)], judge_fn=spy)
    assert spy.calls == []
    assert report.presumed_covered == 0                    # never presumed covered
    assert any(u.block_id == "frag" for u in report.unjudgeable)   # surfaced as a coverage gap


def test_untokenizable_block_comment_quote_is_not_evidence() -> None:
    # On the fallback path the evidence view is comment-stripped too, so a quote from a comment in an
    # unlexable block is not accepted as evidence.
    frag = 'x = "unterminated\n# validate the user email address\ny = 1'
    assert evidence_present(frag, "validate the user email address") is False


def test_gold_verdict_is_normalized_for_accuracy() -> None:
    # A directly-built SemanticGold with mixed case/whitespace must not deflate accuracy — the gold
    # side is normalized like the judge side.
    cal = calibrate([(_pairing("w", _WRONG_CODE, _REQUIREMENT), sem.SemanticGold("  Wrong "))],
                    reference_stub_judge, runs=2)
    assert cal.accuracy == 1.0     # "  Wrong " matches the judge's normalized "wrong"


def test_prompt_requirement_side_is_bounded() -> None:
    # The requirement-side cap in build_semantic_request is exercised (the code-side test alone let a
    # dropped requirement cap survive). A huge requirement must be truncated in the prompt.
    huge_req = "email " * 5000
    req = sem.build_semantic_request(sem.Ranked(_pairing("r", _WRONG_CODE, huge_req), 0.0, True, "x"))
    assert len(req.prompt) < sem._PROMPT_FIELD_CAP * 3
    assert "[…truncated]" in req.prompt
    assert req.requirement == huge_req            # the structured field stays full


def test_identifier_gaming_blind_spot_is_presumed_covered_not_judged() -> None:
    # Pin the acknowledged blind spot as a visible contract: a block whose executable identifiers echo
    # the requirement pushes overlap ABOVE threshold, so it is presumed_covered and never judged — a
    # semantic model, not this lexical filter, would be needed to catch it.
    gamed = ('def f(x):\n'
             '    validate = user = email = address = format = reject = malformed = record = x\n'
             '    return x')
    assert overlap_score(gamed, _REQUIREMENT) >= sem._WEAK_LINK_THRESHOLD   # identifiers inflate it
    spy = _SpyJudge(sem.SEM_WRONG)
    report = assess([_pairing("gamed", gamed, _REQUIREMENT)], judge_fn=spy)
    assert spy.calls == []                        # never judged — the blind spot
    assert report.presumed_covered == 1
