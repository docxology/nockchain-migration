# Abstract

The Nockchain migration driver implements an operator-gated runbook for moving
legacy v0 wallet notes to a v1 P2PKH address. It separates transaction
preparation, reconciliation, and broadcast into distinct phases. This report
describes the division of responsibility between the driver, wallet binary, and
operator. The repository's unit suite supplies evidence for parsing, accounting,
and confirmation behavior.
