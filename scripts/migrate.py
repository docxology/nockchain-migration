#!/usr/bin/env python3
"""Thin CLI for the nockchain v0 -> v1 migration driver.

All logic lives in src/nockchain_migration; this entry point only parses
arguments and calls phase functions. Run from a dedicated workspace dir:

    python scripts/migrate.py phase0 --workspace ~/nockchain-migration
    python scripts/migrate.py import --workspace ... [--version 0|1]
    python scripts/migrate.py sweep --destination <v1-p2pkh> --workspace ...
    python scripts/migrate.py broadcast --destination <v1-p2pkh> --workspace ...

Broadcast always asks per-transaction; there is no --yes flag by design.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nockchain_migration import cli  # noqa: E402
from nockchain_migration.sweep import parse_sweep_output  # noqa: E402
from nockchain_migration.wallet import Wallet  # noqa: E402


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=[
        "phase0", "import", "sweep", "broadcast", "verify"])
    ap.add_argument("--workspace", type=Path, required=True)
    ap.add_argument("--endpoint", default=None,
                    help="public gRPC override (default: wallet's own default)")
    ap.add_argument("--version", type=int, default=0, choices=[0, 1],
                    help="seed-phrase version for import (fallback: re-import 1)")
    ap.add_argument("--destination", default=None,
                    help="v1 P2PKH base58 destination (sweep/broadcast)")
    ap.add_argument("--master", default=None,
                    help="v0 master address (import activation / verify)")
    args = ap.parse_args(argv)

    if args.command == "phase0":
        cli.phase_0(args.workspace, args.endpoint)
        return 0

    wallet = Wallet(workspace=args.workspace, public_endpoint=args.endpoint)

    if args.command == "import":
        cli.phase_2_import_seed(wallet, version=args.version)
        if args.master:
            cli.phase_2_set_active(wallet, args.master)
        return 0

    if args.command in {"sweep", "broadcast"} and not args.destination:
        ap.error("--destination is required for sweep/broadcast")

    if args.command == "sweep":
        balance = cli.parse_balance_nicks(wallet.show_balance())
        cli.phase_4_sweep(wallet, args.destination, balance)
        return 0

    if args.command == "broadcast":
        out = wallet.workspace / "txs"
        records = parse_sweep_output("", out)
        cli.phase_5_broadcast(wallet, records, args.destination)
        return 0

    if not args.master:
        ap.error("--master (v0 master address) is required for verify")
    cli.phase_6_verify(wallet, args.destination or "", args.master)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
