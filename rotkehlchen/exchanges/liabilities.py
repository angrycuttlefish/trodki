"""trodki: liabilities reported by exchange connections (e.g. short positions, margin loans).

Upstream exchange balances are assets only. An exchange that also owes something implements
`ExchangeWithLiabilities`, and the balance snapshot adds its liabilities to the totals.
"""
from collections import defaultdict
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from rotkehlchen.accounting.structures.balance import Balance

if TYPE_CHECKING:
    from collections.abc import Iterable

    from rotkehlchen.assets.asset import Asset
    from rotkehlchen.fval import FVal


@runtime_checkable
class ExchangeWithLiabilities(Protocol):
    def last_liabilities(self) -> dict[Asset, Balance]:
        """Liabilities found by the latest successful `query_balances`, values as positive amounts"""  # noqa: E501
        ...


def collect_exchange_liabilities(
        exchanges: Iterable[object],
        liabilities_value_per_location: defaultdict[str, FVal],
) -> dict[Asset, Balance]:
    """Sum the liabilities of the given exchanges whose balance query succeeded, and add their
    value to the per-location totals under each exchange's data location."""
    liabilities: defaultdict[Asset, Balance] = defaultdict(Balance)
    for exchange in exchanges:
        if not isinstance(exchange, ExchangeWithLiabilities):
            continue
        location = str(exchange.data_location)  # type: ignore[attr-defined]  # an exchange
        for asset, balance in exchange.last_liabilities().items():
            liabilities[asset] += balance
            liabilities_value_per_location[location] += balance.value
    return dict(liabilities)
