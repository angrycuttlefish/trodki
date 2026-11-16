"""trodki: Interactive Brokers exchange connection.

Positions come from the locally running Client Portal Gateway (read-only `/portfolio`
endpoints only) and history from Flex Web Service. One connection per IBKR account.
"""
import logging
from typing import TYPE_CHECKING, Any

from rotkehlchen.exchanges.exchange import ExchangeInterface, ExchangeQueryBalances
from rotkehlchen.exchanges.ibkr.constants import DEFAULT_GATEWAY_URL
from rotkehlchen.locations.constants import LOCATION_IBKR
from rotkehlchen.logging import RotkehlchenLogsAdapter

if TYPE_CHECKING:
    from rotkehlchen.db.dbhandler import DBHandler
    from rotkehlchen.exchanges.data_structures import MarginPosition
    from rotkehlchen.types import ApiKey, ApiSecret, Timestamp
    from rotkehlchen.user_messages import MessagesAggregator

logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)


class Ibkr(ExchangeInterface):

    def __init__(
            self,
            name: str,
            api_key: ApiKey,
            secret: ApiSecret,
            database: DBHandler,
            msg_aggregator: MessagesAggregator,
            ibkr_gateway_url: str = DEFAULT_GATEWAY_URL,
            ibkr_account_id: str | None = None,
    ) -> None:
        super().__init__(
            name=name,
            location=LOCATION_IBKR,
            api_key=api_key,
            secret=secret,
            database=database,
            msg_aggregator=msg_aggregator,
        )
        self.gateway_url = ibkr_gateway_url
        self.account_id_override = ibkr_account_id

    def first_connection(self) -> None:
        self.first_connection_made = True

    def validate_api_key(self) -> tuple[bool, str]:
        raise NotImplementedError

    def query_balances(self, **kwargs: Any) -> ExchangeQueryBalances:
        raise NotImplementedError

    def query_online_margin_history(
            self,
            start_ts: Timestamp,
            end_ts: Timestamp,
    ) -> list[MarginPosition]:
        return []
