# Agent Handoff Prompt: Nockchain Legacy v0 → v1 Wallet Migration

> **How to use this document:** Paste everything below the divider into your agent
> (Claude Code, Codex CLI, an operator agent, etc.). It is written to be
> self-contained: the agent needs no prior Nockchain context. Human interaction
> points are explicitly marked as **[HUMAN GATE]** — the agent must stop and wait
> at every one of them.

---

## MISSION

You are an operations agent assisting the operator (Daniel) in migrating
Nockchain wallet funds from the **legacy v0 note format** to the current
**v1 pay-to-pubkey-hash (P2PKH)** address format, using the official
`nockchain-wallet` tooling from the `nockchain/nockchain` monorepo.

This is a real-value asset migration. Correctness and secrecy of key material
outrank speed. When in doubt, stop and ask.

### What "success" means

1. The official repository is cloned and the wallet binary is built and
   verified on PATH.
2. The operator's legacy v0 seed phrase is imported (interactively, by the
   operator — never handled by you beyond passing it into the wallet command).
3. A fresh v1 key pair is generated and its P2PKH address is recorded and
   verified.
4. All spendable v0 notes are swept into the v1 address via
   `migrate-v0-notes`, with the operator explicitly confirming the destination
   and every transaction before broadcast.
5. Broadcast transactions are checked for acceptance and the final v1 balance
   is verified.
6. A clean backup (`keys.export`) is produced and the operator is told exactly
   where it lives and how to restore from it.

---

## CRITICAL SECURITY RULES (NON-NEGOTIABLE)

1. **Never broadcast anything without an explicit human confirmation.** The
   commands `send-tx` (and anything else that submits to the network) may only
   run after the operator reads the transaction summary and says, in effect,
   "yes, send it." Each transaction gets its own confirmation.
2. **Never modify a saved transaction before broadcast.** The wallet signs the
   exact canonical transaction noun it displays and saves; changing
   recipients, fees, or note data invalidates the signature and any edit risks
   sending funds to a wrong destination [ref: wallet README, "Maintained
   invariants"].
3. **Seed phrase handling:**
   - The seed phrase is entered **interactively by the operator**. Do not ask
     the operator to paste it into chat if a terminal prompt is available;
     prefer having the operator type/paste it directly into the terminal at
     the wallet's prompt, or into a `read -s` shell variable you then use
     once.
   - Never echo the seed phrase back, never write it to a file, never include
     it in logs, transcripts, commit messages, or environment files that
     persist.
   - After the import command runs, ensure the phrase does not remain in
     shell history (e.g., `history -d <n>` for the offending entries, or run
     the import from a shell with history temporarily disabled).
4. **Destination-address discipline:** before any `send-tx`, display the
   destination P2PKH and require the operator to confirm it character-group by
   character-group (e.g., first 4 / last 4 chars). Base58 strings look alike;
   the wallet decodes addresses as explicit versions and visually similar
   strings must not be trusted casually.
5. **Backups before mutations:** produce `nockchain-wallet export-keys` output
   and confirm the file exists and is non-empty **before** the first
   `send-tx`. The export file is sensitive — treat it like the seed phrase.
6. **No scope creep:** do not run a local node, miner, or anything else not in
   this runbook unless the operator asks. The wallet talks to a public gRPC
   endpoint by default and that is sufficient for this migration.
7. **Work in a dedicated directory:** the wallet writes `./txs/*.tx`,
   `keys.export`, and `message.sig`-style artifacts to the **current working
   directory**. Create and operate from a dedicated workspace such as
   `~/nockchain-migration/` so nothing is scattered.

---

## BACKGROUND FACTS YOU NEED (verified against official docs)

- The wallet is a client, not a consensus implementation: it plans, encodes,
  and signs transactions locally, then submits them to a node for admission.
- `migrate-v0-notes --destination <v1-p2pkh-b58>`:
  - Finds spendable v0 notes for the **active v0 master** and any active v0
    child signers under that master.
  - **Ignores v1 notes.**
  - Builds **one transaction per spend-capable signer bucket** — expect
    possibly multiple `./txs/*.tx` files, not one.
  - Uses the destination as the refund target, so leftover value also returns
    as v1.
  - Prints a signer-by-signer summary: saved tx path, selected inputs, fee,
    expected migrated amount, and the exact `send-tx` command for each.
  - Is **full-sweep only** in the current release.
- Watch-only imports are **not sufficient**; the wallet must hold the matching
  v0 **signing key**.
- Seed-phrase versioning: if the seed phrase was generated **before October
  2025**, it is probably version 0. If notes import but cannot be spent with
  version 0, re-import the same phrase with `--version 1`.
- `keygen` behavior: if no active master key is set, the new key becomes
  active; otherwise the active key remains unchanged. **This is why the seed
  import must happen BEFORE `keygen`** — the v0 master must remain the active
  master while `migrate-v0-notes` runs.
- Units: 65,536 nicks = 1 nock. `--amount`/`--fee` are whole nocks;
  `--amount-nicks`/`--fee-nicks` are raw nicks.
- `tx-accepted` returning `true` means the node **validated** the transaction;
  it is necessary but not sufficient — wait for canonical-chain inclusion
  before declaring victory.
- Default public endpoint: `23.252.122.18:5556` (no local node required).
- Mixed v0/v1 note sets are rejected in manual `create-tx`; auto-selection is
  v1-only. That is why the dedicated `migrate-v0-notes` command exists.

---

## PHASE 0 — ENVIRONMENT SETUP (autonomous; no human gate)

**Objective:** a working `nockchain-wallet` binary on PATH.

1. Check prerequisites and install anything missing per the repo's own
   README/quickstart:
   - `git`, `make`, a C toolchain, and Rust via `rustup` (let the repo's
     `rust-toolchain` file pin the toolchain version).
2. Clone the official monorepo:

   ```bash
   mkdir -p ~/nockchain-migration && cd ~/nockchain-migration
   git clone https://github.com/nockchain/nockchain.git
   cd nockchain
   ```

3. Build and install the wallet (follow the repo's quickstart; the canonical
   target is):

   ```bash
   make install-nockchain-wallet
   export PATH="$HOME/.cargo/bin:$PATH"
   ```

   If the quickstart also requires `make install-hoonc`, run it, but it is not
   needed for this migration.

4. Verify:

   ```bash
   which nockchain-wallet
   nockchain-wallet --help
   ```

   If the binary is missing or `--help` fails, stop and report — do not
   improvise an alternative build.

5. Confirm connectivity to the public API (a sync-heavy command proves both
   binary and network):

   ```bash
   cd ~/nockchain-migration
   nockchain-wallet list-notes
   ```

   An empty result or "no pubkeys" message is fine at this point — the point
   is that the command runs and reaches the endpoint.

**Exit criteria for Phase 0:** wallet binary on PATH, `--help` works, public
API reachable, dedicated workspace directory in use.

---

## PHASE 1 — FRESH v1 KEY GENERATION (human gate for recording)

**Objective:** a brand-new v1 key pair whose P2PKH address will be the
migration destination.

> Ordering note: this intentionally happens AFTER the v0 seed import in the
> canonical flow, but since `keygen` does not displace an existing active
> master, it is safe to run after Phase 2 as well. To keep the canonical
> order and minimize surprises, run Phase 2 (import) first, then this phase.

1. **[HUMAN GATE]** Tell the operator: "I will now import your legacy seed
   phrase. When I run the import command, please type/paste the phrase
   directly into the terminal prompt yourself." (Proceed to Phase 2 first if
   following the canonical order.)

---

## PHASE 2 — LEGACY v0 SEED IMPORT (human gate — seed phrase)

**Objective:** the v0 master key present in the wallet and set active.

1. **[HUMAN GATE]** Confirm with the operator that their seed phrase predates
   October 2025 (→ likely `--version 0`). If they are unsure, start with
   version 0; the fallback is documented below.
2. Prepare the import so the operator enters the phrase at a hidden prompt,
   not in plain command line:

   ```bash
   cd ~/nockchain-migration
   read -rs SEEDPHRASE && echo
   nockchain-wallet import-keys --seedphrase "$SEEDPHRASE" --version 0
   unset SEEDPHRASE
   history -d $((HISTCMD-1)) 2>/dev/null
   ```

   (Adapt to your shell; the requirements are: hidden input, single use,
   immediate unset, no history persistence.)
3. Verify the legacy master is present:

   ```bash
   nockchain-wallet list-master-addresses
   ```

4. **[HUMAN GATE]** Show the operator the list of master addresses. Ask them
   to identify which one is the legacy v0 master that owns their funds (it is
   a base58 master pubkey for v0 wallets). If only one master exists, still
   show it and get explicit acknowledgment.
5. Set the legacy v0 master active:

   ```bash
   nockchain-wallet set-active-master-address <legacy-v0-master-address>
   ```

6. Confirm active state and see the note tree:

   ```bash
   nockchain-wallet list-master-addresses
   nockchain-wallet list-active-addresses
   nockchain-wallet list-notes
   nockchain-wallet show-balance
   ```

**Fallback:** if notes appear but the sweep later fails to find spendable
notes (or spending fails), re-import the same phrase with
`--version 1` and repeat steps 3–6.

**Exit criteria:** legacy v0 master present and active; `list-notes` /
`show-balance` show the expected v0 notes. If the balance is zero or clearly
wrong, STOP and report before proceeding.

---

## PHASE 3 — FRESH v1 KEY GENERATION (continued)

1. Generate the new key pair:

   ```bash
   nockchain-wallet keygen
   ```

   The active master stays the v0 master (required for the sweep). Record the
   new v1 P2PKH address from the output.
2. Verify it is tracked:

   ```bash
   nockchain-wallet list-master-addresses
   ```

3. **[HUMAN GATE]** Display the new v1 P2PKH destination address to the
   operator and have them confirm it will be the migration destination.
   Write it down in the session log (the address is public information; the
   seed/keys are not).
4. Immediately produce the pre-migration backup:

   ```bash
   nockchain-wallet export-keys   # writes keys.export in cwd
   ls -la keys.export
   ```

   Tell the operator where `keys.export` is, that it contains ALL wallet
   keys, and that it must be moved to secure offline storage after the
   migration.

---

## PHASE 4 — SWEEP (dry run only; broadcast is a separate gate)

1. Run the migration sweep:

   ```bash
   nockchain-wallet migrate-v0-notes --destination <v1-p2pkh-b58>
   ```

2. This writes one `./txs/<name>.tx` file per spend-capable signer bucket and
   prints a per-signer summary. **Do NOT run any `send-tx` yet.**
3. For each saved transaction, display its contents:

   ```bash
   nockchain-wallet show-tx ./txs/<migration-transaction>.tx
   ```

4. Prepare a summary table for the operator: for each tx file — signer, note
   count, fee (in nocks and nicks), expected migrated amount, destination,
   and the exact `send-tx` command the wallet printed.

**Exit criteria:** all tx files exist under `./txs/`, all have been shown via
`show-tx`, and the summary table reconciles (sum of expected migrated amounts
≈ pre-migration v0 balance minus total fees).

---

## PHASE 5 — BROADCAST (human gate per transaction)

For **each** tx file, one at a time:

1. **[HUMAN GATE]** Present the tx's summary line and destination address
   (first-4/last-4 characters). Ask: "Confirm broadcast of
   `./txs/<name>.tx` (signer X, amount Y nocks, fee Z) to destination
   <v1-p2pkh>?" Only proceed on an explicit yes.
2. Broadcast:

   ```bash
   nockchain-wallet send-tx ./txs/<migration-transaction>.tx
   ```

3. Record the returned transaction ID (base58) in the session log.
4. Check acceptance (public API):

   ```bash
   nockchain-wallet --client public tx-accepted <base58-tx-id>
   ```

   Interpretation: `true` = validated by the node (good, not final).
   `false` or an error = do not panic; report to the operator, wait, and
   re-check. Never re-broadcast or rebuild a tx without the operator's
   instruction.

**Exit criteria:** every tx file from Phase 4 either broadcast and accepted,
or explicitly skipped by the operator with a recorded reason.

---

## PHASE 6 — VERIFICATION AND CLOSEOUT

1. Wait for canonical-chain inclusion (ask the operator how long they want to
   wait / whether they have a block explorer they trust; re-run
   `tx-accepted` and balance checks at intervals they choose).
2. Verify funds landed on the new v1 address:

   ```bash
   nockchain-wallet set-active-master-address <new-v1-p2pkh-address>
   nockchain-wallet list-notes
   nockchain-wallet show-balance
   nockchain-wallet list-notes-by-address <v1-p2pkh-b58>
   ```

3. Confirm the v0 side is empty (re-activate the v0 master and check):

   ```bash
   nockchain-wallet set-active-master-address <legacy-v0-master-address>
   nockchain-wallet list-notes
   nockchain-wallet show-balance
   ```

   Expected: no spendable v0 notes remain.
4. Final backup and hygiene:
   - Re-run `nockchain-wallet export-keys` and confirm `keys.export` is fresh
     and non-empty.
   - **[HUMAN GATE]** Remind the operator to move `keys.export` and any seed
     phrase records to secure offline storage, and to keep the new seed
     phrase (for the v1 key) written down per their usual key-management
     practice.
   - Leave the active master set to the new v1 address.
   - Optionally scrub `./txs/` after the operator confirms everything settled
     (ask first — they may want the receipts).
5. Final report to the operator: pre-migration balance, per-tx fees and
   amounts, tx IDs, post-migration v1 balance, backup locations, and any
   anomalies.

---

## FAILURE PLAYBOOK

| Symptom | Likely cause | Action |
|---|---|---|
| Import succeeds but `list-notes` shows nothing | Wrong seed-phrase version | Re-import with `--version 1` |
| `migrate-v0-notes` finds no spendable notes | Watch-only key, or wrong active master, or notes already v1 | Verify active master is the v0 master; verify the wallet holds the signing key (watch-only is insufficient) |
| `send-tx` rejected by node | Stale chain view / fee issues | Do not rebuild blindly; report, re-sync, consult the operator; protocol disputes defer to `PROTOCOL.md` |
| `tx-accepted` returns `false` after broadcast | Not yet validated, or rejected | Wait and re-check; report to operator; never re-broadcast without instruction |
| Build fails | Toolchain mismatch | Follow the repo's `rust-toolchain` pin and README; report exact error |
| Mixed-version error in any manual tx | v0 and v1 notes cannot be mixed | Do not attempt manual `create-tx` mixes; use `migrate-v0-notes` only |

---

## COMMAND QUICK REFERENCE

```bash
# Build / install (from repo root)
make install-nockchain-wallet
export PATH="$HOME/.cargo/bin:$PATH"

# Keys
nockchain-wallet keygen
nockchain-wallet import-keys --seedphrase "$SEEDPHRASE" --version 0   # or 1
nockchain-wallet import-keys --file keys.export
nockchain-wallet export-keys
nockchain-wallet show-master-zprv        # sensitive — operator eyes only
nockchain-wallet list-master-addresses
nockchain-wallet list-active-addresses
nockchain-wallet set-active-master-address <address-b58>

# Balances / notes
nockchain-wallet list-notes
nockchain-wallet list-notes-by-address <base58-address>
nockchain-wallet show-balance

# Migration
nockchain-wallet migrate-v0-notes --destination <v1-p2pkh-b58>
nockchain-wallet show-tx ./txs/<name>.tx
nockchain-wallet send-tx ./txs/<name>.tx
nockchain-wallet --client public tx-accepted <base58-tx-id>

# Endpoint overrides (only if needed)
nockchain-wallet --client public --public-grpc-server-addr <host:port> list-notes
nockchain-wallet --client private --private-grpc-server-port <port> list-notes
```

**Canonical sources:** `github.com/nockchain/nockchain` (monorepo quickstart,
`START_HERE.md`, `PROTOCOL.md`, `changelog/protocol/`) and
`crates/nockchain-wallet/README.md` (Tier 1 canonical for wallet CLI
behavior). If any command here conflicts with the current README, the README
wins — surface the discrepancy to the operator before proceeding.
