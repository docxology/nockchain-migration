# Scope

The driver converts the legacy-wallet handoff into a phase-oriented CLI and a
guided wizard. The handoff defines the migration sequence and its human gates
[@migrationRunbook]. The operator walkthrough documents the concrete commands,
expected output, and remedies for a failed check [@operatorGuide].

The migration prepares a full sweep. The operator selects and verifies the fresh
v1 destination, maintains the key backup, and confirms each transaction before
the wallet can broadcast it.
