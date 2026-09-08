"""Nockchain legacy v0 -> v1 wallet migration driver.

Implements the runbook in docs/nockchain-v0-to-v1-migration-handoff.md.
Every network-mutating step (send-tx) is behind an explicit operator gate;
pure logic (units, confirmation, parsing, reconciliation) lives in modules
importable without the wallet binary.
"""

__version__ = "0.1.0"
