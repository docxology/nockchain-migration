"""Operator confirmation helpers.

Destination-address discipline (security rule 4 of the runbook): base58
strings look alike, so the operator confirms character-group by
character-group, not by glancing at the whole string.
"""

FIRST_GROUP = 4
LAST_GROUP = 4


def address_groups(address: str) -> str:
    """Render the first-4 / last-4 confirmation groups of a base58 address."""
    if len(address) <= FIRST_GROUP + LAST_GROUP:
        # Degenerate for real addresses; keep exact but flagged.
        return f"<SHORT ADDRESS, verify in full> {address}"
    return f"{address[:FIRST_GROUP]}...{address[-LAST_GROUP:]}"


def confirm_destination(address: str, prompt=input) -> bool:
    """Require the operator to type the first-4/last-4 groups back exactly."""
    first, last = address[:FIRST_GROUP], address[-LAST_GROUP:]
    answer = prompt(
        f"Type the destination groups '{first}' then '{last}' "
        f"(space-separated) to confirm: "
    )
    parts = answer.strip().split()
    return parts == [first, last]


def confirm(prompt: str, prompt_fn=input) -> bool:
    """Explicit yes/no gate. Only an unambiguous yes proceeds."""
    answer = prompt_fn(f"{prompt} [yes/no]: ")
    return answer.strip().lower() in {"yes", "y"}
