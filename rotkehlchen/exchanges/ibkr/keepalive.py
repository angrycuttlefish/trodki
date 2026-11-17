"""trodki: keep the IBKR gateways' read-only sessions alive.

The Client Portal Gateway drops an idle session, after which the user has to log in again
in their browser. A `/tickle` about once a minute per gateway keeps it alive.
"""
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable

    from rotkehlchen.exchanges.ibkr.ibkr import Ibkr

TICKLE_INTERVAL_SECONDS: Final = 60


def gateways_due_for_tickle[T](
        exchanges: Iterable[T],
        last_tickle: dict[str, float],
        now: float,
) -> list[T]:
    """Return the connections whose gateway was last tickled at least a minute ago, and mark
    them as tickled at `now`. Connections are told apart by their gateway URL."""
    due = []
    for exchange in exchanges:
        key = str(getattr(exchange, 'gateway_url', id(exchange)))
        if now - last_tickle.get(key, float('-inf')) >= TICKLE_INTERVAL_SECONDS:
            last_tickle[key] = now
            due.append(exchange)
    return due


def tickle_gateways(exchanges: Iterable[Ibkr]) -> None:
    for exchange in exchanges:
        exchange.gateway.tickle()
