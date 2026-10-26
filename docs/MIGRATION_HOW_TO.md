# Migration How-To — operator walkthrough

Step-by-step instructions for migrating Nockchain funds from the legacy v0
note format to the v1 P2PKH address format. This guide drives the tooling in
this repo, which implements the canonical runbook
([nockchain-v0-to-v1-migration-handoff.md](nockchain-v0-to-v1-migration-handoff.md) —
read it at least once before starting; it explains *why* each step exists).

**This is a real-value asset migration. Correctness and secrecy outrank speed.
When in doubt, stop and ask.**

---

## Recommended: run the wizard

The wizard stages everything and prompts you at every gate in one
interactive session — including the hidden seed-phrase prompt:

```bash
uv run --project /path/to/nockchain-migration \
    python /path/to/nockchain-migration/scripts/migrate_wizard.py \
    --workspace ~/nockchain-migration
```

It walks Stages 1–6 in order (environment → seed import → destination +
backup → sweep + reconciliation → gated broadcast → verify) and skips
already-completed stages based on live wallet state, so it is safe to re-run.
The manual phase-by-phase commands below remain valid and are documented for
operators who prefer one phase at a time.

---

## Before you start

| Requirement | Check |
|---|---|
| `git`, `make`, C toolchain, Rust (rustup) | `rustup --version && which git make cc` |
| This repo cloned | `git clone https://github.com/docxology/nockchain-migration.git` |
| A dedicated workspace dir | `mkdir -p ~/nockchain-migration` — the wallet writes `./txs/*.tx` and `keys.export` into cwd |
| ~30–60 min of uninterrupted time | the runbook has human gates; do not rush them |
| Your seed phrase written down offline | if the phrase was generated **before October 2025** it is probably version 0 |

All commands below run from the repo root; `WORKSPACE` is your dedicated
directory (e.g. `~/nockchain-migration`).

---

## Phase 0 — build the wallet and verify connectivity

Do this inside the workspace, following the official quickstart:

```bash
cd ~/nockchain-migration
git clone https://github.com/nockchain/nockchain.git
cd nockchain
make install-nockchain-wallet
export PATH="$HOME/.cargo/bin:$PATH"
```

Then prove the binary and the public endpoint work:

```bash
cd ~/nockchain-migration
uv run --project /path/to/nockchain-migration \
    python /path/to/nockchain-migration/scripts/migrate.py phase0 \
    --workspace ~/nockchain-migration
```

Expected: `Phase 0 OK: wallet on PATH, public API reachable, workspace in use.`
If it fails, **stop** — do not improvise an alternative build. The default
public endpoint is `216.158.95.10:5556`; override only if needed with
`--endpoint host:port`.

## Phase 2 — import the legacy v0 seed phrase (HUMAN GATE)

The operator types the phrase at a hidden prompt. It is never echoed, logged,
or stored.

```bash
uv run --project ... python scripts/migrate.py import \
    --workspace ~/nockchain-migration --version 0
# → prompt: "Operator: type/paste the seed phrase now (input hidden)"
```

The driver collects the phrase itself at that hidden prompt and invokes
`nockchain-wallet import-keys` once; nothing is written to disk or to shell
history. The wizard does the same in its Stage 2.

Then set the legacy v0 master active (it must be the active master while the
sweep runs — that is why import happens **before** keygen):

```bash
nockchain-wallet list-master-addresses          # identify the v0 master
uv run ... python scripts/migrate.py import \
    --workspace ~/nockchain-migration --master <legacy-v0-master-b58>
```

Check the output of `list-notes` / `show-balance` that the phase prints.
**If the balance is zero or clearly wrong, STOP.**

- Notes appear but nothing spendable later? Re-run `import` with
  `--version 1` (seed-version fallback) and re-activate.

## Phase 3 — generate the fresh v1 key (HUMAN GATE: record destination)

```bash
nockchain-wallet keygen
```

The active master stays the v0 master (required for the sweep). Record the
new v1 P2PKH address from the output — this is the **migration destination**.
`keygen` does not displace the active master, which is exactly why the seed
import (Phase 2) happened first. Confirm the address aloud / on paper before
continuing; you will type its first-4/last-4 groups back at the Phase 5
broadcast gates.

Then produce the pre-migration backup:

```bash
cd ~/nockchain-migration && nockchain-wallet export-keys && ls -la keys.export
```

`keys.export` contains **ALL** wallet keys. Move it to secure offline storage
after the migration.

## Phase 4 — sweep (dry run; nothing is broadcast yet)

```bash
uv run ... python scripts/migrate.py sweep \
    --workspace ~/nockchain-migration --destination <v1-p2pkh-b58>
```

What happens:

1. `migrate-v0-notes` finds all spendable v0 notes and builds **one tx per
   spend-capable signer bucket** — expect possibly multiple `./txs/*.tx`.
   It ignores v1 notes and uses the destination as refund target.
2. Each saved tx is shown via `show-tx`, then a summary table prints fees and
   expected migrated amounts per bucket.
3. The driver **reconciles**: sum(expected migrated) must equal
   pre-migration balance minus fees. On mismatch it exits non-zero and
   nothing can be broadcast. Do not bypass this check.

## Phase 5 — broadcast (HUMAN GATE per transaction)

```bash
uv run ... python scripts/migrate.py broadcast \
    --workspace ~/nockchain-migration --destination <v1-p2pkh-b58>
```

For **each** tx file, one at a time:

1. The driver re-verifies `keys.export` (must exist and be non-empty).
2. It asks you to confirm that exact file, its fee, its migrated amount, and
   the destination's first-4/last-4 groups. **Only an explicit `yes`
   broadcasts.** Anything else skips the file with a logged reason.
3. After each broadcast, `tx-accepted` is checked. `true` = the node
   validated the tx — necessary but **not final**; wait for canonical-chain
   inclusion. `false`/error → do NOT re-broadcast; report, wait, re-check.

There is no batch/auto-confirm mode and none will be added. Saved tx files
must never be edited — editing invalidates the signature and risks sending
funds to a wrong destination.

## Phase 6 — verify and close out

```bash
uv run ... python scripts/migrate.py verify \
    --workspace ~/nockchain-migration \
    --destination <v1-p2pkh-b58> --master <legacy-v0-master-b58>
```

The driver checks: v1 side shows the migrated balance; v0 side shows no
spendable notes; a fresh `keys.export` is written; the active master is left
on the **v1** address.

Final human tasks (the driver prints these reminders):

- Move `keys.export` and any seed-phrase records to secure offline storage.
- Keep the new v1 seed phrase written down per your key-management practice.
- Optionally scrub `./txs/` once you confirm everything settled (ask first —
  you may want the receipts).

---

## Failure playbook

| Symptom | Likely cause | Action |
|---|---|---|
| Import OK but `list-notes` empty | wrong seed version | re-run `import` with `--version 1` |
| Sweep finds no spendable notes | watch-only key, wrong active master, or notes already v1 | verify active master is the v0 master; wallet must hold the signing key |
| Reconciliation mismatch at Phase 4 | fee/amount parse drift or genuine accounting error | STOP; inspect `show-tx` output manually; do not broadcast |
| `tx-accepted` false after broadcast | not yet validated or rejected | wait and re-check; never re-broadcast without a decision |
| Build fails | toolchain mismatch | follow the repo's `rust-toolchain` pin; report exact error |
| Any command conflicts with the wallet README | README is Tier-1 canonical | surface the discrepancy before proceeding |

## Command cheat sheet

```bash
# driver phases (each gates what the runbook gates)
scripts/migrate.py phase0    --workspace WS [--endpoint HOST:PORT]
scripts/migrate.py import    --workspace WS [--version 0|1] [--master V0ADDR]
scripts/migrate.py sweep     --workspace WS --destination V1ADDR
scripts/migrate.py broadcast --workspace WS --destination V1ADDR
scripts/migrate.py verify    --workspace WS --destination V1ADDR --master V0ADDR

# raw wallet, when the runbook calls for it directly
nockchain-wallet list-master-addresses | list-notes | show-balance
nockchain-wallet keygen | export-keys
nockchain-wallet --client public tx-accepted <base58-tx-id>
```

Units: 65,536 nicks = 1 nock. The driver prints amounts as
`N nocks + M nicks (X.NNNNNN nocks)`.