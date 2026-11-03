# P0 local test evidence

- Date: 2026-11-03
- Environment: isolated Linux workspace, Python 3.13.5, local Git fixture repository.
- Commands: `python -m unittest discover -s tests -v` and `python -m compileall -q blindreview`
- Result: **14/14 tests passed**; syntax compilation passed.

Covered: contract validation, malformed identity rejection, report parsing, SQLite idempotence/restart handling, real local Git clone and pinned commit validation, mock Codex-style report, mock OpenCode JSONL event parsing, authenticated HTTP endpoints, subprocess cancellation, 2-of-3 gate, 600-second third-seat grace (simulated clock), cancellation, coordinator resume and config-fingerprint protection.

**Not verified**: actual Hermes A2A plugin behavior, production Git remote access, Codex/OpenCode binary versions and model calls, actual node 5bao/9bao/rusty reachability, Windows 10 subprocess handling, actual 420-second remote review, network outage and server-kill fault injection, release approval gates P1/P2.

The mock reviewer is a test fixture and must **never** be counted as a real blind-review report in production.
