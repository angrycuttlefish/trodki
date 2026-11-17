"""trodki: Interactive Brokers data types."""
import datetime
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from rotkehlchen.fval import FVal


class GatewayStatus(StrEnum):
    OK = 'ok'
    LOGGED_OUT = 'logged_out'
    UNREACHABLE = 'unreachable'
    RATE_LIMITED = 'rate_limited'


@dataclass(frozen=True)
class IbkrPosition:
    """One open position as reported by the gateway's `/portfolio/{account}/positions`.

    `position` is signed (negative = short) and in contracts for options. `mkt_value` and
    `unrealized_pnl` are in `currency` and already include the contract multiplier.
    """
    conid: int
    contract_desc: str
    asset_class: str
    position: FVal
    mkt_price: FVal
    mkt_value: FVal
    avg_cost: FVal
    unrealized_pnl: FVal
    currency: str
    ticker: str | None
    und_conid: int | None
    put_or_call: Literal['C', 'P'] | None
    strike: FVal | None
    expiry: datetime.date | None
    multiplier: FVal

    def days_to_expiry(self) -> int | None:
        if self.expiry is None:
            return None
        return (self.expiry - datetime.datetime.now(tz=datetime.UTC).date()).days

    def serialize(self) -> dict[str, Any]:
        return {
            'conid': self.conid,
            'contract_desc': self.contract_desc,
            'asset_class': self.asset_class,
            'position': str(self.position),
            'mkt_price': str(self.mkt_price),
            'mkt_value': str(self.mkt_value),
            'avg_cost': str(self.avg_cost),
            'unrealized_pnl': str(self.unrealized_pnl),
            'currency': self.currency,
            'ticker': self.ticker,
            'und_conid': self.und_conid,
            'put_or_call': self.put_or_call,
            'strike': None if self.strike is None else str(self.strike),
            'expiry': None if self.expiry is None else self.expiry.isoformat(),
            'days_to_expiry': self.days_to_expiry(),
            'multiplier': str(self.multiplier),
        }
