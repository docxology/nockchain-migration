# Nockchain migration documentation

This project packages the legacy v0 to v1 P2PKH wallet migration runbook into a
phase driver and an interactive wizard.

- [Operator walkthrough](MIGRATION_HOW_TO.md) covers setup, the wizard, transaction
  confirmation, and the failure playbook.
- [Migration handoff](nockchain-v0-to-v1-migration-handoff.md) is the canonical
  runbook implemented by the driver.
- [Manuscript and build instructions](manuscript/README.md) explain the design,
  verification evidence, and how to render the manuscript.
- [Maintenance backlog](TODO.md) records open review findings.

## Code map

- [Migrate](../scripts/migrate.py) exposes the individual phases.
  [Migrate wizard](../scripts/migrate_wizard.py) guides the operator through them
  and checks the live wallet state.
- [Phase functions](../src/nockchain_migration/cli.py) coordinate setup, key
  generation and backup, sweep, gated broadcast, and verification.
- [Wallet wrapper](../src/nockchain_migration/wallet.py) calls the
  `nockchain-wallet` binary. [Sweep parsing and reconciliation](../src/nockchain_migration/sweep.py)
  compare the expected migrated value with the prior balance minus fees.
- [Confirmation](../src/nockchain_migration/confirm.py) checks the destination
  character groups. [Units](../src/nockchain_migration/units.py) handles display
  conversion between nicks and nocks.
- [Unit tests](../tests/test_migration.py) cover these components without a live
  wallet.

## Development verification

The package declares Python 3.11 or later. The checkout's
[`.python-version`](../.python-version) selects Python 3.15 for the default
`uv` workflow. Run the same locked test command as [CI](../.github/workflows/ci.yml)
from the repository root.

```sh
uv run --frozen --no-progress pytest -q
```

For a real migration, use the official `nockchain-wallet` binary and follow the
operator walkthrough from a dedicated workspace.
