"""``cfs run-start``: begin a run by writing the shared run-correlation id.

A *run* spans many separate ``cfs`` processes — gates recorded during it, ``verify-completion`` at its
close — and each process otherwise gets its own per-process id, so they could not be scoped together.
This writes one id to the shared run-id file (beside the decision log) so every command of the run
reads the same id and its events scope as one run. Call it **once** at a run's start.

It is setup, not a gate: on success it exits ``0``, whether or not an id could be written (when there
is nowhere to write — outside a project, or logging disabled — it reports that and the run falls back
to per-command ids). A malformed argument is the one exception: like every command it emits the
standard structured error and exits ``2``.
"""
from __future__ import annotations

from typing import List

from ..utils import decision_log, ui

_COMMAND = "run-start"


# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-run-start
def _parser() -> ui.JsonSafeArgumentParser:
    """The command's arguments (none of its own)."""
    return ui.JsonSafeArgumentParser(
        prog="cfs run-start",
        description="Begin a run: write the shared run-correlation id so every cfs command of this "
                    "run (gates during it, verify-completion at its close) scopes to one run.")


def cmd_run_start(argv: List[str]) -> int:
    """Write a fresh run id and report it. Exits 0 on success; 2 on a malformed argument."""
    if ui.parse_args_or_json_error(_parser(), argv) is None:
        return 2  # a bad argument -- the standard structured ERROR was already emitted
    run_id = decision_log.start_run()
    if run_id is None:
        ui.result({"status": "no-log", "run_id": None,
                   "message": "no project decision log here, so per-command ids are used"},
                  human_fn=lambda d: ui.info(f"run-start: {d['message']}"))
        return 0
    ui.result({"status": "started", "run_id": run_id,
               "message": f"run started ({run_id})"},
              human_fn=lambda d: ui.success(f"run-start: {d['message']}"))
    return 0
# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-run-start
