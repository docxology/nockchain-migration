# TODO

## Workflowz review — 2026-11-10

- [ ] **WF-1 (P1)** Pin `.python-version` to a concrete patch release.
  - Outcome: `uv run python --version` resolves without uv fetching/interpreting a bare minor.
  - Evidence: `.python-version:1` contains `3.15`; `pyproject.toml:5` allows `>=3.11`.
  - Probe: `uv run python -c "import sys; assert sys.version_info[:3] == (3, 15, 2)"` from repo root.
  - Constraints: project targets 3.15.2 per lane policy; no dependency in `pyproject.toml` forbids it.

- [ ] **WF-2 (P1)** Replace float arithmetic in `parse_balance_nicks` with integer/Decimal math.
  - Outcome: balances with nock components whose product with 65,536 exceeds 2^53 no longer risk rounding error; reconciliation gate cannot be silently fooled.
  - Evidence: `src/nockchain_migration/cli.py:47-49` uses `float(...) * NICKS_PER_NOCK` then `int(round(...))`.
  - Probe: `uv run python -c "from nockchain_migration.cli import parse_balance_nicks; assert parse_balance_nicks('Balance: 200000000 nocks 0 nicks') == 200000000 * 65536"` (currently passes but only by luck of rounding; regression test should pin behavior at a value where float would slip, e.g. `137438953473 nocks 1 nicks`).
  - Dependencies: none.

- [ ] **WF-3 (P1)** Replace float arithmetic in `sweep._field_nicks` for nock-suffixed values.
  - Outcome: per-signer `fee: N nocks M nicks` lines convert exactly; reconciliation sum is precise.
  - Evidence: `src/nockchain_migration/sweep.py:62-63` `int(round(float(value) * NICKS_PER_NOCK))`.
  - Probe: `uv run python -c "from pathlib import Path; from nockchain_migration.sweep import parse_sweep_output; out='- signer address: X\n- fee: 137438953473 nocks 0 nicks\n- migrated amount: 0\n- tx path: txs/a.tx\n'; r=parse_sweep_output(out, Path('/tmp'))[0]; assert r.fee_nicks == 137438953473 * 65536"`.
  - Dependencies: none.

- [ ] **WF-4 (P0)** `scripts/migrate.py broadcast` must not call `phase_5_broadcast` with zero-amount fallback records.
  - Outcome: operator's per-tx confirm prompt shows the real fee and migrated amount; the informed-consent gate is meaningful.
  - Evidence: `scripts/migrate.py:62-66` calls `parse_sweep_output("", out)` which always takes the zero-fee fallback at `src/nockchain_migration/sweep.py:90-93`; `cli.py:142-143` then renders `fee 0 nicks, migrated 0 nicks` in the confirm prompt.
  - Probe: from repo root with a fake wallet shim on PATH, run `uv run python scripts/migrate.py broadcast --workspace /tmp/wf4 --destination <b58>` and confirm the per-tx prompt either aborts with "re-run sweep" or shows non-zero amounts sourced from a re-parsed sweep log; never the literal string `migrated 0 nocks` for a non-empty tx.
  - Dependencies: choose one of (a) persist parsed sweep records to a JSON sidecar during `sweep` and reload in `broadcast`, or (b) require operator to re-run `sweep` immediately before `broadcast` in the same process. Does not violate the "no batch/auto-confirm" invariant.

- [ ] **WF-5 (P2)** Reconcile README Python prerequisite with `.python-version`.
  - Outcome: docs and pin agree; new contributors are not told 3.11 is sufficient when the pin requests 3.15.
  - Evidence: `README.md:41` says "Python 3.11+"; `.python-version:1` says `3.15`.
  - Probe: `uv run python scripts/migrate.py --help` succeeds and README prerequisites section names the same minor as `.python-version`.
  - Dependencies: land WF-1 first so the README can cite a concrete version.

- [ ] **WF-6 (P3)** Drop the redundant `sys.path` insertion and dynamic `__import__("pathlib")` in `tests/test_migration.py`.
  - Outcome: single source of path bootstrap in `tests/conftest.py`; test file imports `migrate_wizard` without re-prepending `scripts/`.
  - Evidence: `tests/conftest.py:4` already inserts `src/`; `tests/test_migration.py:7-8` re-imports sys/pathlib and inserts `scripts/` using `__import__("pathlib")` despite `from pathlib import Path` on line 4.
  - Probe: `uv run pytest -q` from repo root passes with the same count as before the cleanup.
  - Dependencies: none; pure maintainability, no behavior change.
