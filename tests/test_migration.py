"""Tests for pure migration logic. No wallet binary, no network, no mocks of
the wallet itself — the wrapper is thin and gated by construction."""

from pathlib import Path

import pytest
import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "scripts"))

from nockchain_migration.confirm import address_groups, confirm, confirm_destination
from nockchain_migration.sweep import MigrationTx, parse_sweep_output, reconcile, summary_table
from nockchain_migration.units import NICKS_PER_NOCK, format_amount, nicks_to_nocks
from nockchain_migration.wallet import Wallet, WalletError


# ── units ────────────────────────────────────────────────────────────────
def test_nicks_to_nocks():
    assert nicks_to_nocks(NICKS_PER_NOCK) == 1.0
    assert nicks_to_nocks(0) == 0.0
    with pytest.raises(ValueError):
        nicks_to_nocks(-1)


def test_format_amount_whole_and_remainder():
    assert format_amount(NICKS_PER_NOCK) == "1 nock"
    assert format_amount(2 * NICKS_PER_NOCK) == "2 nocks"
    out = format_amount(NICKS_PER_NOCK + 5)
    assert "1 nocks + 5 nicks" in out


# ── destination discipline ───────────────────────────────────────────────
ADDR = "3uPqrs9wXyZ1abcdefgh"


def test_address_groups():
    assert address_groups(ADDR) == "3uPq...efgh"


def test_confirm_destination_requires_exact_groups():
    inputs = iter(["3uPq efgh"])
    assert confirm_destination(ADDR, prompt=lambda _: next(inputs))
    inputs = iter(["3uPq efgX"])
    assert not confirm_destination(ADDR, prompt=lambda _: next(inputs))
    inputs = iter(["3uPqefgh"])  # missing separator is a fail — be strict
    assert not confirm_destination(ADDR, prompt=lambda _: next(inputs))


def test_confirm_gate_yes_only():
    assert confirm("go?", prompt_fn=lambda _: "yes")
    assert confirm("go?", prompt_fn=lambda _: "y")
    assert not confirm("go?", prompt_fn=lambda _: "y es")
    assert not confirm("go?", prompt_fn=lambda _: "")


# ── sweep parsing / reconciliation ───────────────────────────────────────
SWEEP_OUTPUT = """\
V0 Migration Sweep
- destination: DEMOaKtE18rsN7px6cCxccTG9t81MS3Xf8FXVVnjvYsdp7FWRWJSBjV
- active signing keys examined: 1
- migration txs created: 1

master
- signer address: EXAMPLemasterBase58Address111111111111111111111111111111111111111
- signer version: 0
- selected notes: 2
- selected total: 8000000000
- result: created
- fee: 466944
- migrated amount: 7999533056
- tx path: txs/DEMOtxExample1111111111111111111111111111111111111.tx
- submit with: nockchain-wallet send-tx "txs/DEMOtxExample1111111111111111111111111111111111111.tx"

master
- signer address: EXAMPLechildAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
- signer version: 0
- selected notes: 1
- selected total: 100
- result: created
- fee: 7 nocks 8192 nicks
- migrated amount: 0 nocks 90 nicks
- tx path: txs/childB.tx
"""


def test_parse_sweep_output_extracts_buckets(tmp_path: Path):
    records = parse_sweep_output(SWEEP_OUTPUT, tmp_path / "txs")
    names = [r.tx_path.name for r in records]
    assert names == [
        "DEMOtxExample1111111111111111111111111111111111111.tx",
        "childB.tx",
    ]
    assert records[0].fee_nicks == 466944
    assert records[0].expected_nicks == 7999533056
    assert records[1].fee_nicks == 7 * NICKS_PER_NOCK + 8192
    assert records[1].expected_nicks == 90


def test_reconcile_real_run_numbers():
    records = parse_sweep_output(SWEEP_OUTPUT, Path("/tmp"))
    # 7999533056 + 90 migrated; fees 466944 + 466944 (7 nocks 8192 nicks each)
    total = 7999533056 + 90 + 2 * 466944
    assert reconcile(records, pre_v0_balance_nicks=total)
    assert not reconcile(records, pre_v0_balance_nicks=8000000000)


def test_parse_sweep_output_falls_back_to_txs_dir(tmp_path: Path):
    txs = tmp_path / "txs"
    txs.mkdir()
    (txs / "only.tx").write_text("x")
    records = parse_sweep_output("format drift, nothing parsed", txs)
    assert [r.tx_path.name for r in records] == ["only.tx"]
    assert records[0].fee_nicks == 0 and records[0].expected_nicks == 0


def test_reconcile_balance_minus_fees():
    a = MigrationTx(Path("a.tx"), fee_nicks=500, expected_nicks=1000)
    b = MigrationTx(Path("b.tx"), fee_nicks=250, expected_nicks=250)
    assert reconcile([a, b], pre_v0_balance_nicks=2000)
    assert not reconcile([a, b], pre_v0_balance_nicks=1900)


def test_summary_table_totals():
    r = MigrationTx(Path("a.tx"), fee_nicks=NICKS_PER_NOCK,
                    expected_nicks=10 * NICKS_PER_NOCK)
    table = summary_table([r])
    assert "TOTAL" in table
    assert str(10 * NICKS_PER_NOCK) in table


# ── wallet wrapper guardrails ────────────────────────────────────────────
def test_send_tx_refuses_missing_file(tmp_path):
    w = Wallet(workspace=tmp_path)
    with pytest.raises(WalletError, match="missing tx file"):
        w.send_tx(tmp_path / "nope.tx")


def test_export_keys_requires_nonempty(tmp_path, monkeypatch):
    w = Wallet(workspace=tmp_path)
    # export-keys "succeeds" but writes nothing -> must raise.
    monkeypatch.setattr(Wallet, "run", lambda self, *a, **k: "")
    with pytest.raises(WalletError, match="non-empty"):
        w.export_keys()


def test_run_reports_missing_binary(tmp_path):
    w = Wallet(workspace=tmp_path, binary="definitely-not-on-path-xyz")
    with pytest.raises(WalletError, match="not on PATH"):
        w.list_notes()


# ── wizard address extraction ────────────────────────────────────────────
def test_addresses_extractor_filters_base58():
    from migrate_wizard import addresses

    addr = "3uPqrs9wXyZ1abcdefghijKmnopQRStuv"
    out = f"Master 1: {addr}\nzprvSECRETKEYSTRING00000\nnote: 12nicks"
    got = addresses(out)
    assert addr in got
    assert "12nicks" not in got  # too short
    assert not any("SECRETKEY" in t for t in got)  # I (excluded) splits the zprv run


# ── balance parsing (regression: nocks+nicks components must sum) ───────
def test_parse_balance_nocks_plus_nicks():
    from nockchain_migration.cli import parse_balance_nicks

    real = """Wallet Balance
Wallet balance from block DEMOBLOCK1 at height 142.733
- Wallet Version: %8
- Number of Notes: 2
- Balance: 122070 nocks 30880 nicks
- Balance (raw): 8000010400 nicks"""
    assert parse_balance_nicks(real) == 8000010400
    assert parse_balance_nicks("Balance: 1 nocks 100 nicks") == 65636
    assert parse_balance_nicks("Balance: 1.5 nocks 0 nicks") == 98304
    assert parse_balance_nicks("Balance: 0 nicks") == 0
    assert parse_balance_nicks("Balance (raw): 8000010400 nicks") == 8000010400
