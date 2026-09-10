"""Tests for utils/cpt_reference_scan — the shared cpt-id def↔ref scan.

The four commands' golden tests already prove behaviour-identity; these pin the
util's own contract: the projections, the def↔ref graph view, and that it adds no
new error-swallowing over scan_cpt_ids.
"""
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from studio.utils import cpt_reference_scan as scan


def _arts(*names):
    return [(Path(n), "REQUIREMENTS") for n in names]


def _hits(*specs):  # spec: (id, type, line, checked)
    return [{"id": i, "type": t, "line": ln, "checked": c} for (i, t, ln, c) in specs]


# ---------------------------------------------------------------- scan_records
def test_scan_records_yields_every_hit_with_artifact_context():
    per = {Path("a.md"): _hits(("cpt-x-req-1", "reference", 3, False)),
           Path("b.md"): _hits(("cpt-x-req-1", "definition", 1, False),
                                ("cpt-x-req-2", "reference", 5, False))}
    with patch.object(scan, "scan_cpt_ids", side_effect=lambda p: per[p]):
        recs = list(scan.scan_records(_arts("a.md", "b.md")))
    assert [(str(p), t, h["id"]) for p, t, h in recs] == [
        ("a.md", "REQUIREMENTS", "cpt-x-req-1"),
        ("b.md", "REQUIREMENTS", "cpt-x-req-1"),
        ("b.md", "REQUIREMENTS", "cpt-x-req-2"),
    ]


# ------------------------------------------------------------------ references
def test_references_filter_target_exclude_definitions_by_default():
    hits = _hits(("cpt-x-req-1", "definition", 1, False),
                 ("cpt-x-req-1", "reference", 4, True),
                 ("cpt-x-req-2", "reference", 7, False))
    with patch.object(scan, "scan_cpt_ids", return_value=hits):
        refs = scan.references("cpt-x-req-1", _arts("a.md"), {}, include_definitions=False)
    assert refs == [{"artifact": "a.md", "artifact_type": "REQUIREMENTS", "line": 4,
                     "kind": None, "type": "reference", "checked": True}]


def test_references_include_definitions_and_attach_source():
    hits = _hits(("cpt-x-req-1", "definition", 1, False), ("cpt-x-req-1", "reference", 4, False))
    with patch.object(scan, "scan_cpt_ids", return_value=hits):
        refs = scan.references("cpt-x-req-1", _arts("a.md"), {"a.md": "SRC"},
                               include_definitions=True)
    assert [r["type"] for r in refs] == ["definition", "reference"]
    assert all(r["source"] == "SRC" for r in refs)


# ----------------------------------------------------------------- definitions
def test_definitions_are_definition_only_and_omit_the_type_key():
    hits = _hits(("cpt-x-req-1", "definition", 1, False),
                 ("cpt-x-req-1", "reference", 4, False),
                 ("cpt-x-req-2", "definition", 9, False))
    with patch.object(scan, "scan_cpt_ids", return_value=hits):
        defs = scan.definitions("cpt-x-req-1", _arts("a.md"), {})
    assert defs == [{"artifact": "a.md", "artifact_type": "REQUIREMENTS", "line": 1,
                     "kind": None, "checked": False}]
    assert "type" not in defs[0]


def test_definitions_attach_source_when_present():
    hits = _hits(("cpt-x-req-1", "definition", 2, False))
    with patch.object(scan, "scan_cpt_ids", return_value=hits):
        defs = scan.definitions("cpt-x-req-1", _arts("a.md"), {"a.md": "SRC"})
    assert defs[0]["source"] == "SRC"


def test_empty_artifacts_yield_empty_everywhere():
    # §3a edge / empty state: no artifacts → empty across every view; scan_cpt_ids never called.
    assert list(scan.scan_records([])) == []
    assert scan.references("cpt-x-req-1", [], {}, include_definitions=True) == []
    assert scan.definitions("cpt-x-req-1", [], {}) == []
    assert scan.graph_for("cpt-x-req-1", []) == {"defined_in": [], "referenced_in": []}


def test_non_ascii_artifact_path_passes_through_unchanged():
    # A4: paths are stringified, not normalised — a non-ASCII path must survive verbatim.
    hits = _hits(("cpt-x-req-1", "reference", 2, False))
    with patch.object(scan, "scan_cpt_ids", return_value=hits):
        refs = scan.references("cpt-x-req-1", [(Path("café/交/x.md"), "REQUIREMENTS")], {},
                               include_definitions=True)
    assert refs[0]["artifact"] == "café/交/x.md"


def test_unknown_id_yields_empty_for_both_views():
    with patch.object(scan, "scan_cpt_ids",
                      return_value=_hits(("cpt-x-req-1", "reference", 1, False))):
        assert scan.references("cpt-x-nope", _arts("a.md"), {}, include_definitions=True) == []
        assert scan.definitions("cpt-x-nope", _arts("a.md"), {}) == []


# ------------------------------------------------------- graph_for (B4 parity)
def test_graph_for_partitions_into_defs_and_refs_matching_the_views():
    hits = _hits(("cpt-x-req-1", "definition", 1, False),
                 ("cpt-x-req-1", "reference", 4, False),
                 ("cpt-x-req-1", "reference", 9, False))
    with patch.object(scan, "scan_cpt_ids", return_value=hits):
        g = scan.graph_for("cpt-x-req-1", _arts("a.md"))
        defs = scan.definitions("cpt-x-req-1", _arts("a.md"), {})
        refs = scan.references("cpt-x-req-1", _arts("a.md"), {}, include_definitions=False)
    assert g["defined_in"] == defs
    assert g["referenced_in"] == refs
    assert len(g["defined_in"]) == 1
    assert len(g["referenced_in"]) == 2


def test_graph_for_attaches_source_through_both_partitions():
    hits = _hits(("cpt-x-req-1", "definition", 1, False), ("cpt-x-req-1", "reference", 4, False))
    with patch.object(scan, "scan_cpt_ids", return_value=hits):
        g = scan.graph_for("cpt-x-req-1", _arts("a.md"), {"a.md": "SRC"})
    assert g["defined_in"][0]["source"] == "SRC"
    assert g["referenced_in"][0]["source"] == "SRC"


# ------------------------------------------- A1: adds no new error-swallowing
def test_util_does_not_swallow_scan_errors():
    with patch.object(scan, "scan_cpt_ids", side_effect=OSError("boom")):
        records = scan.scan_records(_arts("a.md"))  # lazy — does not raise until iterated
        with pytest.raises(OSError):
            list(records)


# --------------------------------------------------------- property (§3a)
def test_property_references_typed_and_count_matches_target_hits():
    rng = random.Random(1234)
    ids = ["cpt-x-req-1", "cpt-x-req-2", "cpt-x-flow-a"]
    for _ in range(400):
        hits = [{"id": rng.choice(ids), "type": rng.choice(["definition", "reference"]),
                 "line": rng.randint(1, 50), "checked": rng.choice([True, False])}
                for _ in range(rng.randint(0, 6))]
        target = rng.choice(ids)
        with patch.object(scan, "scan_cpt_ids", return_value=hits):
            refs = scan.references(target, _arts("a.md"), {}, include_definitions=True)
            recs = list(scan.scan_records(_arts("a.md")))
        assert all(r["type"] in ("definition", "reference") for r in refs)
        assert len(refs) == sum(1 for h in hits if h["id"] == target)
        assert len(recs) == len(hits)


def test_property_definitions_and_graph_partition_the_target_scan():
    rng = random.Random(99)
    ids = ["cpt-x-req-1", "cpt-x-req-2", "cpt-x-flow-a"]
    for _ in range(400):
        hits = [{"id": rng.choice(ids), "type": rng.choice(["definition", "reference"]),
                 "line": rng.randint(1, 50), "checked": rng.choice([True, False])}
                for _ in range(rng.randint(0, 6))]
        target = rng.choice(ids)
        with patch.object(scan, "scan_cpt_ids", return_value=hits):
            defs = scan.definitions(target, _arts("a.md"), {})
            g = scan.graph_for(target, _arts("a.md"))
        n_defs = sum(1 for h in hits if h["id"] == target and h["type"] == "definition")
        n_refs = sum(1 for h in hits if h["id"] == target and h["type"] == "reference")
        assert len(defs) == n_defs
        assert all("type" not in d for d in defs)
        assert len(g["defined_in"]) == n_defs
        assert len(g["referenced_in"]) == n_refs


@pytest.mark.parametrize("call", [
    lambda: scan.references("cpt-x-req-1", _arts("a.md"), {}, include_definitions=True),
    lambda: scan.definitions("cpt-x-req-1", _arts("a.md"), {}),
    lambda: scan.graph_for("cpt-x-req-1", _arts("a.md")),
])
def test_no_projection_swallows_scan_errors(call):
    # A1: every projection iterates scan_records eagerly, so a scan_cpt_ids error propagates.
    with patch.object(scan, "scan_cpt_ids", side_effect=OSError("boom")):
        with pytest.raises(OSError):
            call()


def test_source_attached_per_artifact_across_multiple_artifacts():
    per = {Path("a.md"): _hits(("cpt-x-req-1", "reference", 1, False)),
           Path("b.md"): _hits(("cpt-x-req-1", "reference", 2, False))}
    arts = [(Path("a.md"), "REQUIREMENTS"), (Path("b.md"), "REQUIREMENTS")]
    with patch.object(scan, "scan_cpt_ids", side_effect=lambda p: per[p]):
        refs = scan.references("cpt-x-req-1", arts, {"a.md": "SRC_A", "b.md": "SRC_B"},
                               include_definitions=True)
    assert refs[0]["source"] == "SRC_A"
    assert refs[1]["source"] == "SRC_B"


def test_definitions_source_attached_per_artifact_across_multiple_artifacts():
    # #5 mirror: definitions() shares _record with references(), but pin its per-artifact
    # source mapping directly on the where_defined path too — not only via references().
    per = {Path("a.md"): _hits(("cpt-x-req-1", "definition", 1, False)),
           Path("b.md"): _hits(("cpt-x-req-1", "definition", 2, False))}
    arts = [(Path("a.md"), "REQUIREMENTS"), (Path("b.md"), "REQUIREMENTS")]
    with patch.object(scan, "scan_cpt_ids", side_effect=lambda p: per[p]):
        defs = scan.definitions("cpt-x-req-1", arts, {"a.md": "SRC_A", "b.md": "SRC_B"})
    assert defs[0]["source"] == "SRC_A"
    assert defs[1]["source"] == "SRC_B"
