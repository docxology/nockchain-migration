# nockchain — legacy v0 → v1 wallet migration

Open-source, operator-gated tooling that implements the Nockchain legacy v0 → v1
P2PKH wallet migration runbook (`docs/nockchain-v0-to-v1-migration-handoff.md`)
as executable phases instead of pasted shell commands.

This is a **real-value asset migration** tool. Every network-mutating step
(`send-tx`) requires an explicit per-transaction operator confirmation; there
is no `--yes` flag by design.

## Documentation

- [docs/MIGRATION_HOW_TO.md](docs/MIGRATION_HOW_TO.md) — **start here**: the
  operator walkthrough, phase by phase, with human gates and the failure
  playbook.
- [docs/nockchain-v0-to-v1-migration-handoff.md](docs/nockchain-v0-to-v1-migration-handoff.md)
  — the canonical runbook this project implements.

## Layout

- `docs/MIGRATION_HOW_TO.md` — the step-by-step operator walkthrough (start
  here when running the migration).
- `docs/nockchain-v0-to-v1-migration-handoff.md` — the canonical runbook this
  project implements. When it and the code disagree, surface the discrepancy;
  the runbook and the wallet README win.
- `src/nockchain_migration/` — the driver:
  - `wallet.py` — thin subprocess wrapper around `nockchain-wallet`;
    refuses to broadcast a missing tx file; requires a non-empty
    `keys.export` after `export-keys`.
  - `sweep.py` — parses `migrate-v0-notes` per-signer output, reconciles
    expected migrated amounts against pre-migration balance minus fees.
  - `confirm.py` — destination character-group confirmation (first-4/last-4).
  - `units.py` — 65,536 nicks = 1 nock formatting.
  - `cli.py` — phase functions (Phase 0 setup, Phase 2 import, Phase 3 keygen
    + backup, Phase 4 sweep, Phase 5 broadcast gates, Phase 6 verify).
- `scripts/migrate.py` — CLI entry point.
- `tests/` — no-mocks tests of the pure logic.

## Usage

From a dedicated workspace directory (the wallet writes `./txs/*.tx` and
`keys.export` to cwd):

```bash
uv run python scripts/migrate.py phase0 --workspace ~/nockchain-migration
uv run python scripts/migrate.py import --workspace ~/nockchain-migration --version 0
uv run python scripts/migrate.py sweep --workspace ~/nockchain-migration \
    --destination <v1-p2pkh-b58>
uv run python scripts/migrate.py broadcast --workspace ~/nockchain-migration \
    --destination <v1-p2pkh-b58>
uv run python scripts/migrate.py verify --workspace ~/nockchain-migration \
    --destination <v1-p2pkh-b58> --master <legacy-v0-master-address>
```

## Interactive wizard

The recommended way to run the migration. It prompts stage by stage
(environment → seed → destination → sweep → gated broadcast → verify),
skips already-completed stages based on live wallet state, and every
irreversible step is an explicit yes/no:

```bash
uv run --project /path/to/nockchain-migration \
    python /path/to/nockchain-migration/scripts/migrate_wizard.py \
    --workspace ~/nockchain-migration
```

Run it in your own terminal so the seed-phrase prompt is truly hidden.

Seed phrases are entered at a hidden `getpass` prompt by the operator and are
never echoed, logged, or stored. `keys.export` and `txs/` are gitignored.

## Tests

```bash
uv run pytest
```

## Status

Phase logic implemented and unit-tested; end-to-end execution requires the
official `nockchain-wallet` binary (Phase 0) and the operator's live key
material, and is deliberately not automatable past the gates.