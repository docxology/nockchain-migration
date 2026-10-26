"""Wallet CLI wrapper.

Thin subprocess adapter around `nockchain-wallet`. All commands run inside a
dedicated workspace directory (the wallet writes ./txs/*.tx and keys.export to
cwd). Broadcast is deliberately NOT exposed as a convenience one-liner: the
phase driver gates it per transaction.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


class WalletError(RuntimeError):
    pass


_ANSI = re.compile(
    r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))"
)


def _strip_ansi(text: str) -> str:
    """The wallet colorizes even captured (non-TTY) output; parse clean."""
    return _ANSI.sub("", text)


@dataclass(frozen=True)
class Wallet:
    """Location-bound wrapper. workspace must exist before commands run."""

    workspace: Path
    binary: str = "nockchain-wallet"
    public_endpoint: str | None = None  # default public endpoint if unset

    def run(self, *args: str, timeout: float = 300.0) -> str:
        cmd = [self.binary, *args]
        if self.public_endpoint:
            cmd = [self.binary, "--client", "public",
                   "--public-grpc-server-addr", self.public_endpoint, *args]
        try:
            proc = subprocess.run(
                cmd, cwd=self.workspace, capture_output=True, text=True,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise WalletError(
                f"{self.binary} not on PATH — see runbook Phase 0"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise WalletError(f"timed out: {' '.join(cmd)}") from exc
        if proc.returncode != 0:
            raise WalletError(
                f"{' '.join(cmd)} failed ({proc.returncode}):\n{proc.stderr.strip()}"
            )
        return _strip_ansi(proc.stdout)

    # ── read-only queries ────────────────────────────────────────────────
    def list_master_addresses(self) -> str:
        return self.run("list-master-addresses")

    def list_notes(self) -> str:
        return self.run("list-notes")

    def show_balance(self) -> str:
        return self.run("show-balance")

    def tx_accepted(self, tx_id: str) -> bool:
        out = self.run("--client", "public", "tx-accepted", tx_id).strip().lower()
        return out.endswith("true")

    # ── gated mutations ──────────────────────────────────────────────────
    def keygen(self) -> str:
        """Safe before or after seed import: does not displace an active master."""
        return self.run("keygen")

    def export_keys(self) -> Path:
        """Pre-mutation backup (security rule 5). Returns keys.export path."""
        self.run("export-keys")
        path = self.workspace / "keys.export"
        if not path.exists() or path.stat().st_size == 0:
            raise WalletError("export-keys produced no non-empty keys.export")
        return path

    def send_tx(self, tx_path: Path) -> str:
        """Broadcast. Caller MUST have a per-tx operator gate before this."""
        if not tx_path.exists():
            raise WalletError(f"missing tx file: {tx_path}")
        return self.run("send-tx", str(tx_path))
