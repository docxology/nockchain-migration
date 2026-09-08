# AGENTS.md — nockchain migration project

Runbook being implemented:
[docs/nockchain-v0-to-v1-migration-handoff.md](docs/nockchain-v0-to-v1-migration-handoff.md).
Operator walkthrough (step-by-step, gates, failure playbook):
[docs/MIGRATION_HOW_TO.md](docs/MIGRATION_HOW_TO.md).
Read both before touching `src/nockchain_migration/`.

## Invariants (non-negotiable, enforced in code)

- `Wallet.send_tx` is the ONLY broadcast path and every caller gates it on an
  explicit operator `confirm()` for that exact tx file. Never add a batch or
  auto-confirm mode.
- `export-keys` output must exist, be non-empty, and be verified before the
  first broadcast in a session (`phase_5_broadcast` re-runs it).
- Seed phrases: hidden prompt (`getpass`), single use, never logged or
  persisted. `LOG` goes to stderr and must never receive key material.
- Canonical phase order: seed import (Phase 2) BEFORE `keygen` (Phase 3) so
  the v0 master stays active for `migrate-v0-notes`. `keygen` does not
  displace an active master, but keep the order anyway.
- Reconciliation gate: if `sweep.reconcile` fails (migrated total ≠
  pre-v0 balance − fees), the driver exits non-zero before any broadcast.
- `parse_balance_nicks` accepts "N nicks", "N.N nocks", or a bare integer
  (nicks). If `show-balance` output format drifts, fix the parser, don't
  special-case.

## Known limits

- `sweep.parse_sweep_output` parses the current summary format; on drift it
  falls back to listing `./txs/*.tx` with zero fees, and reconciliation then
  fails loudly — that is intentional, do not loosen it.
- `migrate-v0-notes` is full-sweep only; partial sweeps are out of scope.

## Verification

```bash
uv run pytest          # unit tests, no binary/network needed
python scripts/migrate.py phase0 --workspace /tmp/nock-test   # needs nockchain-wallet on PATH
```

Self-versioned repo published at `github.com/docxology/nockchain-migration` (MIT).
Sensitive artifacts (`keys.export`, `txs/`, `*.zprv`) are gitignored — keep it
that way. Repo-wide policy: [../../AGENTS.md](../../AGENTS.md).