# Pylint Rule Rollout Brainstorm

Session ID: `pylint-rule-rollout-20260613T125348Z`

## Topic

Choose a pragmatic next batch of `pylint` rules for Constructor Studio: enable
critical clean-pass rules now, fix obvious small warning sets next, and defer
noisy or policy-heavy rules.

## Decisions

- Enable now: `E1120,E1121,E1123,E1124,E1125,E1126,E1130,E1131,E1133,E1136`
- Enable now: `W0102,W0106,W0120,W0123,W0125,W0133,W0150,W0201,W0231,W0237`
- Fix first, then enable: `W1514,W1309,W0107`
- Defer: `W0108,W0621`
- Review separately: `W0640`, because it may be a real closure-capture correctness issue in `commands/map/links.py`
- Rollout shape: first zero-noise config expansion, then a small cleanup tranche

## Open Questions

- Should `W0640` be patched immediately as a one-off correctness fix?
- Should the fix-first tranche be one combined patch or split into cleanup/config steps?

## Evidence Summary

- `make pylint` is the canonical command and is enforced in CI.
- Current `pyproject.toml` disables all messages and enables a small staged set.
- Current enabled set passes.
- `--enable=E` and `--enable=F` pass clean.
- Targeted runtime/control-flow warning probes pass clean.
- Known obvious fix-first warnings:
  - `W1514`: 2 missing encodings
  - `W1309`: 5 static f-strings
  - `W0107`: 3 unnecessary `pass` statements

