"""Nock/nick unit handling. 65,536 nicks = 1 nock."""

NICKS_PER_NOCK = 65_536


def nicks_to_nocks(nicks: int) -> float:
    """Convert raw nicks to whole-nock float (nicks are canonical)."""
    if nicks < 0:
        raise ValueError("nicks must be non-negative")
    return nicks / NICKS_PER_NOCK


def format_amount(nicks: int) -> str:
    """Human-readable amount: whole nocks plus exact remainder in nicks."""
    nocks, rem = divmod(nicks, NICKS_PER_NOCK)
    if rem == 0:
        return f"{nocks} nock" + ("" if nocks == 1 else "s")
    return f"{nocks} nocks + {rem} nicks ({nicks_to_nocks(nicks):.6f} nocks)"
