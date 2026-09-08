#!/usr/bin/env python3
"""Interactive migration wizard: prompts and stages every runbook phase.

Run it in YOUR OWN terminal (not through an agent) so the seed phrase is
typed at a hidden prompt that no log, transcript, or history records:

    uv run --project <repo> python scripts/migrate_wizard.py \
        --workspace ~/nockchain-migration

Every irreversible step is an explicit yes/no prompt. The wizard can be
re-run safely: completed, non-destructive stages are skipped based on live
wallet state (it asks the wallet, not a state file).
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from nockchain_migration import cli  # noqa: E402
from nockchain_migration.confirm import address_groups, confirm, confirm_destination  # noqa: E402
from nockchain_migration.sweep import (  # noqa: E402
    MigrationTx, parse_sweep_output, reconcile, summary_table)
from nockchain_migration.units import format_amount  # noqa: E402
from nockchain_migration.wallet import Wallet, WalletError  # noqa: E402

RULE = "\n" + "═" * 72 + "\n"


def banner(title: str) -> None:
    print(f"{RULE}{title}{RULE}")


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or default


def choose(prompt: str, options: list[str]) -> str:
    """Numbered single-choice from a list; returns the chosen item."""
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    while True:
        raw = ask(f"{prompt} (1-{len(options)})")
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("  Invalid choice.")


# ── Stage 1: environment ─────────────────────────────────────────────────
def stage_environment(wallet: Wallet) -> None:
    banner("STAGE 1/6 — ENVIRONMENT")
    try:
        wallet.list_notes()
    except WalletError as exc:
        print(f"✗ Wallet not usable: {exc}")
        print("  Build per runbook Phase 0 (make install-hoonc && "
              "make install-nockchain-wallet in the nockchain repo).")
        raise SystemExit(1)
    print(f"✓ {wallet.binary} on PATH, public API reachable, "
          f"workspace {wallet.workspace} in use.")


def addresses(text: str) -> list[str]:
    """Extract base58 address tokens (25+ chars, no I l 0 O) from output."""
    import re

    seen = []
    for tok in re.findall(r"[1-9A-HJ-NP-Za-km-z]{25,}", text):
        if tok not in seen:
            seen.append(tok)
    return seen


def choose(prompt: str, options: list[str]) -> str:
    """Numbered single-choice from a list; returns the chosen item."""
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    while True:
        raw = ask(f"{prompt} (1-{len(options)})")
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("  Invalid choice.")


# ── Stage 2: seed import ─────────────────────────────────────────────────
def stage_seed(wallet: Wallet) -> str:
    """Returns the v0 master address, active in the wallet."""
    banner("STAGE 2/6 — LEGACY v0 SEED IMPORT")
    masters = addresses(wallet.list_master_addresses())
    if masters:
        print("Wallet already holds master addresses:")
        for m in masters:
            print(f"  {m}")
        if confirm("Use these (skip re-import)? If unsure, answer no and "
                   "re-import your phrase."):
            active = choose(
                "Which master owns the funds to migrate?", masters)
        else:
            active = _import_and_pick(wallet, masters)
    else:
        active = _import_and_pick(wallet, masters)
    wallet.run("set-active-master-address", active)
    print(f"\nActive master: {active}")
    print("— Active addresses —")
    print(wallet.run("list-active-addresses"))
    print("— Notes —")
    print(wallet.list_notes())
    balance = wallet.show_balance()
    print(balance)
    nicks = cli.parse_balance_nicks(balance)
    if nicks == 0:
        print("✗ Balance is zero. Wrong seed version or wrong master?")
        if confirm("Re-import the same phrase as --version 1?"):
            wallet.run("import-keys", "--seedphrase",
                       getpass.getpass("seed phrase (hidden): "),
                       "--version", "1")
            return stage_seed(wallet)  # re-run identification with both masters
        raise SystemExit(2)
    if not confirm(f"Pre-migration v0 balance is {format_amount(nicks)}. "
                   "Proceed?"):
        raise SystemExit(2)
    return active


def _import_and_pick(wallet: Wallet, existing: list[str]) -> str:
    phrase = getpass.getpass(
        "Operator: type/paste your seed phrase now (input hidden): ")
    version = ask("Seed version — 0 if generated before Oct 15 2025, "
                  "else 1", default="0")
    try:
        wallet.run("import-keys", "--seedphrase", phrase,
                   "--version", str(version))
    finally:
        del phrase
    masters = [m for m in addresses(wallet.list_master_addresses())
               if m not in existing]
    if not masters:
        print("✗ No new master appeared after import. Wrong phrase?")
        raise SystemExit(2)
    if len(masters) == 1:
        active = masters[0]
    else:
        active = choose("Which master owns the funds to migrate?", masters)
    if not confirm(f"Use {active[:8]}… as the legacy v0 master?"):
        raise SystemExit(2)
    return active


# ── Stage 3: v1 destination + backup ─────────────────────────────────────
def stage_destination(wallet: Wallet, state: dict) -> None:
    banner("STAGE 3/6 — FRESH v1 DESTINATION + BACKUP")
    if state.get("destination") and confirm(
            f"Use recorded destination {address_groups(state['destination'])}?"):
        address = state["destination"]
    else:
        out = wallet.keygen()
        print(out)
        candidates = [a for a in addresses(out)
                      if a not in state.get("known_masters", [])]
        address = candidates[0] if len(candidates) == 1 else ""
        if not address:
            print("Could not unambiguously read the new v1 address from "
                  "keygen output. Copy the 'Address' value printed above.")
            address = ask("New v1 P2PKH address")
    if len(address) < 25 or set(address) - set(
            "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"):
        print(f"✗ '{address}' is not a valid base58 P2PKH address. Aborting "
              "rather than confirming garbage.")
        raise SystemExit(2)
    print(f"\nDestination: {address}")
    print(f"Groups:      {address_groups(address)}")
    if not confirm_destination(address):
        print("✗ Character-group confirmation failed. Do not proceed with "
              "a mistyped destination.")
        raise SystemExit(2)
    if not confirm("This address is the migration destination?"):
        raise SystemExit(2)
    state["destination"] = address
    backup = wallet.export_keys()
    print(f"✓ Backup verified: {backup} — contains ALL wallet keys. "
          "Move it to offline storage after the migration.")


# ── Stage 4: sweep ───────────────────────────────────────────────────────
def stage_sweep(wallet: Wallet, state: dict) -> None:
    banner("STAGE 4/6 — SWEEP (DRY RUN — NOTHING IS BROADCAST)")
    balance = cli.parse_balance_nicks(wallet.show_balance())
    out = wallet.run("migrate-v0-notes", "--destination", state["destination"])
    print(out)
    records = parse_sweep_output(out, wallet.workspace / "txs")
    if not records:
        print("✗ No migration transactions were produced.")
        raise SystemExit(3)
    for r in records:
        print(wallet.run("show-tx", str(r.tx_path)))
    print(summary_table(records))
    if not reconcile(records, balance):
        print("\n✗ RECONCILIATION MISMATCH — expected migrated amounts do "
              "not equal pre-migration balance minus fees. STOP. Inspect "
              "the txs above; do not broadcast.")
        raise SystemExit(3)
    print("✓ Reconciliation OK.")
    state["records"] = records


# ── Stage 5: broadcast ───────────────────────────────────────────────────
def stage_broadcast(wallet: Wallet, state: dict) -> None:
    banner("STAGE 5/6 — BROADCAST (HUMAN GATE PER TRANSACTION)")
    records: list[MigrationTx] = state["records"]
    backup = wallet.export_keys()
    print(f"✓ Pre-broadcast backup verified: {backup}\n")
    tx_ids: list[tuple[str, str]] = []
    for r in records:
        print(f"Tx file:   {r.tx_path}")
        print(wallet.run("show-tx", str(r.tx_path)))
        print(f"Fee: {format_amount(r.fee_nicks)} · Migrated: "
              f"{format_amount(r.expected_nicks)} · Dest: "
              f"{address_groups(state['destination'])}")
        if not confirm(f"Broadcast {r.tx_path.name}?"):
            print(f"— SKIPPED {r.tx_path.name} (record your reason) —")
            continue
        out = wallet.send_tx(r.tx_path)
        print(out)
        import re

        ids = re.findall(r"[1-9A-HJ-NP-Za-km-z]{40,}", out)
        tx_id = ids[-1] if ids else ""
        if tx_id:
            print(f"Broadcast tx id: {tx_id}")
        else:
            print("Broadcast submitted (wallet acknowledged but printed no "
                  "tx id). Record the acknowledgement line above.")
        try:
            accepted = wallet.tx_accepted(tx_id)
            print(f"tx-accepted: {accepted}  (validated ≠ final; wait for "
                  "canonical-chain inclusion)")
        except WalletError as exc:
            print(f"tx-accepted check unavailable: {exc}\n"
                  "This does NOT mean the broadcast failed. Verify the v1 "
                  "balance in Stage 6 / later with list-notes.")
        tx_ids.append((r.tx_path.name, tx_id))
    state["tx_ids"] = tx_ids


# ── Stage 6: verify ──────────────────────────────────────────────────────
def stage_verify(wallet: Wallet, state: dict) -> None:
    banner("STAGE 6/6 — VERIFY AND CLOSE OUT")
    v1 = state["destination"]
    wallet.run("set-active-master-address", v1)
    print("— v1 side —")
    print(wallet.list_notes())
    print(wallet.show_balance())
    v0 = state["v0_master"]
    wallet.run("set-active-master-address", v0)
    print("— v0 side (expect no spendable notes) —")
    print(wallet.list_notes())
    print(wallet.show_balance())
    wallet.run("set-active-master-address", v1)  # leave on v1 (runbook)
    backup = wallet.export_keys()
    print(f"✓ Final backup fresh: {backup}")
    print("\nOperator reminders:")
    for tx_name, tx_id in state.get("tx_ids", []):
        print(f"  broadcast receipt: {tx_name} → {tx_id}")
    print("  • Move keys.export and seed-phrase records to offline storage.")
    print("  • Keep the new v1 seed phrase written down.")
    print("  • Scrub ./txs/ only after you confirm everything settled.")
    print("  • Active master left on the v1 address.")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", type=Path, required=True,
                    help="dedicated migration dir (wallet writes txs/, keys.export here)")
    ap.add_argument("--endpoint", default=None,
                    help="public gRPC override (default: wallet default)")
    ap.add_argument("--destination", default=None,
                    help="resume with a previously recorded v1 destination")
    args = ap.parse_args(argv)

    state: dict = {}
    if args.destination:
        state["destination"] = args.destination

    wallet = Wallet(workspace=args.workspace, public_endpoint=args.endpoint)
    args.workspace.mkdir(parents=True, exist_ok=True)

    print(__doc__)
    if not confirm("Start/continue the v0 → v1 migration now?"):
        return 0

    import subprocess
    try:
        rev = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        rev = "unknown"
    print(f"wizard code commit: {rev or 'unknown'} "
          "(if a fix you expect is missing, git pull in the repo)")
    stage_environment(wallet)
    state["v0_master"] = stage_seed(wallet)
    state["known_masters"] = addresses(wallet.list_master_addresses())
    stage_destination(wallet, state)
    stage_sweep(wallet, state)
    stage_broadcast(wallet, state)
    stage_verify(wallet, state)
    banner("MIGRATION COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
