# Design

The wallet wrapper delegates wallet operations to the official
`nockchain-wallet` command. The phase driver retains responsibility for the
sequence of checks and the handling of errors.

1. Establish the wallet workspace and confirm connectivity.
2. Import and select the legacy master with the operator's input. Generate a
   fresh key and verify the key export.
3. Prepare sweep files and parse the amounts and fees. Reconcile the sum of the
   migrated amounts with the prior balance less fees.
4. Recheck the export and confirm each exact transaction before broadcast.
5. Compare the destination and legacy wallet balances as part of closeout.

The code keeps the broadcast path in the wallet wrapper. The controls for
destination confirmation and transaction approval stay in the driver, where
the operator can see each decision.
