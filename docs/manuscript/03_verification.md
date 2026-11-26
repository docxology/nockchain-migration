# Verification

The unit suite covers amount formatting, confirmation input, per-signer sweep
parsing, the pre-broadcast reconciliation equation, and error cases for absent
transaction files, missing wallet binaries, or empty key exports [@unitSuite].
The repository CI runs the locked suite with uv.

The local test evidence applies to the driver and its parsing and gating logic.
A deployment check uses the official wallet binary in the operator's
environment. Settlement and actual migration balances are observations of a
live run, which the operator validates through the closeout phase.
