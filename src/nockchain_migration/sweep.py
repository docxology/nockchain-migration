"""Sweep output parsing and reconciliation (runbook Phase 4 exit criteria).

`migrate-v0-notes` prints a signer-by-signer summary with the saved tx path,
fee, and expected migrated amount, and saves one ./txs/<name>.tx per
spend-capable signer bucket. This module parses that output and reconciles
the expected migration total against the pre-migration v0 balance minus fees.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .units import NICKS_PER_NOCK

# Real v0.1.15 per-signer block format (fields are bare nicks, no unit):
#   master
#   - signer address: <b58>
#   - selected notes: 2
#   - selected total: 8000000000
#   - fee: 466944
#   - migrated amount: 7999533056
#   - tx path: txs/<name>.tx
# Also accept unit-suffixed variants ('fee: 7 nocks 8192 nicks').
_BLOCK = re.compile(r"(?m)^(?=\s*-\s*signer address:)")
_TX_PATH = re.compile(r"^\s*-\s*tx path:\s*(\S+\.tx)\s*$", re.M)
_FEE_COMBINED = re.compile(
    r"^\s*-\s*fee:\s*([0-9]+)\s*nocks?\s+([0-9]+)\s*nicks\s*$", re.M
)
_FEE = re.compile(
    r"^\s*-\s*fee:\s*([0-9]+(?:\.[0-9]+)?)\s*(nocks?|nicks)?\s*$", re.M
)
_AMOUNT_COMBINED = re.compile(
    r"^\s*-\s*(?:migrated amount|expected migrated amount):\s*"
    r"([0-9]+)\s*nocks?\s+([0-9]+)\s*nicks\s*$",
    re.M,
)
_AMOUNT = re.compile(
    r"^\s*-\s*(?:migrated amount|expected migrated amount):\s*"
    r"([0-9]+(?:\.[0-9]+)?)\s*(nocks?|nicks)?\s*$",
    re.M,
)


@dataclass(frozen=True)
class MigrationTx:
    tx_path: Path
    fee_nicks: int
    expected_nicks: int


def _field_nicks(combined: re.Pattern[str], plain: re.Pattern[str],
                 block: str) -> int:
    m = combined.search(block)
    if m:  # 'N nocks M nicks'
        return int(m.group(1)) * NICKS_PER_NOCK + int(m.group(2))
    m = plain.search(block)
    if not m:
        return 0
    value, unit = m.group(1), m.group(2)
    if unit and unit.startswith("nock"):
        return int(round(float(value) * NICKS_PER_NOCK))
    return int(value)  # bare nicks (real v0.1.15 format) or explicit nicks


def _parse_block(block: str, txs_dir: Path) -> MigrationTx | None:
    tx_m = _TX_PATH.search(block)
    if not tx_m:
        return None
    name = Path(tx_m.group(1)).name
    return MigrationTx(
        txs_dir / name,
        _field_nicks(_FEE_COMBINED, _FEE, block),
        _field_nicks(_AMOUNT_COMBINED, _AMOUNT, block),
    )


def parse_sweep_output(text: str, txs_dir: Path) -> list[MigrationTx]:
    """Extract per-signer tx records from migrate-v0-notes output.

    On summary-format drift (no .tx paths found), falls back to files present
    in txs_dir with zero fees; reconciliation then fails loudly — intentional.
    """
    records = []
    for block in _BLOCK.split(text):
        rec = _parse_block(block, txs_dir)
        if rec:
            records.append(rec)
    if not records:
        records = [
            MigrationTx(p, 0, 0) for p in sorted(txs_dir.glob("*.tx"))
        ]
    return records




def reconcile(
    records: list[MigrationTx], pre_v0_balance_nicks: int, tolerance_nicks: int = 1
) -> bool:
    """Sum of expected migrated amounts ≈ pre-migration balance minus fees."""
    total_fees = sum(r.fee_nicks for r in records)
    total_migrated = sum(r.expected_nicks for r in records)
    expected = pre_v0_balance_nicks - total_fees
    return abs(total_migrated - expected) <= tolerance_nicks


def summary_table(records: list[MigrationTx]) -> str:
    """Operator-facing per-tx summary (nicks; use units.format_amount to render)."""
    lines = [f"{'tx':<40} {'fee (nicks)':>12} {'expected (nicks)':>18}"]
    for r in records:
        lines.append(f"{r.tx_path.name:<40} {r.fee_nicks:>12} {r.expected_nicks:>18}")
    total_fees = sum(r.fee_nicks for r in records)
    total = sum(r.expected_nicks for r in records)
    lines.append(f"{'TOTAL':<40} {total_fees:>12} {total:>18}")
    return "\n".join(lines)
