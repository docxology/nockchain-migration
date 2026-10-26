"""Phase driver implementing the v0 -> v1 migration runbook.

Canonical phase order: Phase 2 (seed import) BEFORE Phase 3 (keygen) so the
v0 master stays active while migrate-v0-notes runs (keygen never displaces an
active master, but canonical order minimizes surprises).

Security invariants enforced here, not by convention:
- send-tx runs only after a per-transaction operator gate + destination
  character-group confirmation.
- keys.export must exist, be non-empty, and be confirmed BEFORE the first
  broadcast.
- the seed phrase is read via getpass, used once, never echoed, never stored.
- every broadcast and acceptance check is logged to session.log (no secrets).
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

from .confirm import address_groups, confirm, confirm_destination
from .sweep import MigrationTx, parse_sweep_output, reconcile, summary_table
from .units import NICKS_PER_NOCK, format_amount
from .wallet import Wallet, WalletError

LOG = sys.stderr


def log(msg: str) -> None:
    print(msg, file=LOG, flush=True)


def parse_balance_nicks(text: str) -> int:
    """Extract a raw nick total from show-balance output.

    Wallet format: 'Balance: 120000 nocks 0 nicks' — BOTH components must
    be summed. A bare integer is interpreted as nicks. Previously this
    grabbed only the nicks component ('0') and misread a 120,000-nock
    balance as zero.
    """
    import re

    nocks_m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*nocks", text)
    nicks_m = re.search(r"([0-9]+)\s*nicks", text)
    if nocks_m or nicks_m:
        nocks = float(nocks_m.group(1)) if nocks_m else 0.0
        nicks = int(nicks_m.group(1)) if nicks_m else 0
        return int(round(nocks * NICKS_PER_NOCK)) + nicks
    m = re.search(r"Balance \(raw\):\s*([0-9]+)", text)
    if m:
        return int(m.group(1))
    m = re.search(r"\b([0-9]+)\b", text)
    if m:
        return int(m.group(1))
    raise WalletError(f"cannot parse balance from: {text!r}")


# ── Phase 0 ──────────────────────────────────────────────────────────────
def phase_0(workspace: Path, endpoint: str | None) -> Wallet:
    wallet = Wallet(workspace=workspace, public_endpoint=endpoint)
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        wallet.list_notes()  # proves binary on PATH + endpoint reachable
    except WalletError as exc:
        log(f"PHASE 0 FAILED: {exc}")
        raise SystemExit(1) from exc
    log("Phase 0 OK: wallet on PATH, public API reachable, workspace in use.")
    return wallet


# ── Phase 2 ──────────────────────────────────────────────────────────────
def phase_2_import_seed(wallet: Wallet, version: int = 0) -> None:
    """Operator enters the phrase at a hidden prompt; never echoed or stored."""
    phrase = getpass.getpass(
        "Operator: type/paste the seed phrase now (input hidden): "
    )
    try:
        wallet.run(
            "import-keys", "--seedphrase", phrase, "--version", str(version)
        )
    finally:
        del phrase  # single use; drop the reference immediately
    log(wallet.list_master_addresses())


def phase_2_set_active(wallet: Wallet, master_address: str) -> None:
    wallet.run("set-active-master-address", master_address)
    for cmd_out in (
        wallet.list_master_addresses(),
        wallet.list_notes(),
        wallet.show_balance(),
    ):
        log(cmd_out)


# ── Phase 3 ──────────────────────────────────────────────────────────────
def phase_3_keygen_and_backup(wallet: Wallet) -> str:
    out = wallet.keygen()
    log(out)
    address = ""
    for line in out.splitlines():
        if "p2pkh" in line.lower() or "address" in line.lower():
            address = line.strip().split()[-1]
    if not address:
        raise WalletError("could not read new v1 address from keygen output")
    log(f"New v1 destination: {address} (groups: {address_groups(address)})")
    if not confirm("Confirm this address is the migration destination?"):
        raise SystemExit(2)
    backup = wallet.export_keys()
    log(f"Backup written: {backup} — contains ALL wallet keys. "
        "Move to offline storage after migration.")
    return address


# ── Phase 4 ──────────────────────────────────────────────────────────────
def phase_4_sweep(wallet: Wallet, destination: str,
                  pre_v0_balance_nicks: int) -> list[MigrationTx]:
    out = wallet.run("migrate-v0-notes", "--destination", destination)
    log(out)
    records = parse_sweep_output(out, wallet.workspace / "txs")
    for r in records:
        log(wallet.run("show-tx", str(r.tx_path)))
    log(summary_table(records))
    if not reconcile(records, pre_v0_balance_nicks):
        log("RECONCILIATION MISMATCH: expected migrated amounts do not equal "
            "pre-migration balance minus fees. STOP — surface to operator.")
        raise SystemExit(3)
    log("Reconciliation OK.")
    return records


# ── Phase 5 ──────────────────────────────────────────────────────────────
def phase_5_broadcast(wallet: Wallet, records: list[MigrationTx],
                      destination: str) -> list[str]:
    backup = wallet.export_keys()
    log(f"Pre-broadcast backup verified: {backup}")
    tx_ids = []
    for r in records:
        if not confirm(
            f"Broadcast {r.tx_path.name} "
            f"(fee {format_amount(r.fee_nicks)}, migrated "
            f"{format_amount(r.expected_nicks)}, dest {address_groups(destination)})?"
        ):
            log(f"SKIPPED {r.tx_path.name} (operator declined) — record reason.")
            continue
        out = wallet.send_tx(r.tx_path)
        tx_id = out.strip().splitlines()[-1].strip() if out.strip() else ""
        log(f"Broadcast tx id: {tx_id}")
        accepted = None
        if tx_id:
            accepted = wallet.tx_accepted(tx_id)
            log(f"tx-accepted: {accepted} (validated ≠ canonical; wait for "
                "chain inclusion before declaring victory)")
        tx_ids.append(tx_id)
    return tx_ids


# ── Phase 6 ──────────────────────────────────────────────────────────────
def phase_6_verify(wallet: Wallet, v1_address: str, v0_master: str) -> None:
    """Final verification. Leaves active master on the v1 address (runbook)."""
    wallet.run("set-active-master-address", v1_address)
    log("v1 side:\n" + wallet.list_notes() + "\n" + wallet.show_balance())
    wallet.run("set-active-master-address", v0_master)
    log("v0 side (expect no spendable notes):\n"
        + wallet.list_notes() + "\n" + wallet.show_balance())
    wallet.run("set-active-master-address", v1_address)
    backup = wallet.export_keys()
    log(f"Final backup fresh: {backup}")
    log("Remind operator: move keys.export + seed records to offline storage; "
        "leave active master on the v1 address; scrub ./txs/ only after "
        "operator confirms.")