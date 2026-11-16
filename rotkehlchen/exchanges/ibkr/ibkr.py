"""trodki: Interactive Brokers exchange connection.

Positions come from the locally running Client Portal Gateway (read-only `/portfolio`
endpoints only) and history from Flex Web Service. One connection per IBKR account.
"""
import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any, cast

from rotkehlchen.accounting.structures.balance import Balance
from rotkehlchen.assets.asset import Asset
from rotkehlchen.constants import ZERO
from rotkehlchen.db.settings import CachedSettings
from rotkehlchen.errors.asset import UnknownAsset
from rotkehlchen.errors.misc import RemoteError
from rotkehlchen.exchanges.exchange import ExchangeInterface, ExchangeQueryBalances
from rotkehlchen.exchanges.ibkr.assets import get_or_create_contract_asset
from rotkehlchen.exchanges.ibkr.constants import DEFAULT_GATEWAY_URL
from rotkehlchen.exchanges.ibkr.flex import FlexWebService
from rotkehlchen.exchanges.ibkr.gateway import IbkrGateway
from rotkehlchen.exchanges.ibkr.types import GatewayStatus
from rotkehlchen.globaldb.handler import GlobalDBHandler
from rotkehlchen.inquirer import Inquirer
from rotkehlchen.locations.constants import LOCATION_IBKR
from rotkehlchen.logging import RotkehlchenLogsAdapter
from rotkehlchen.types import Price

if TYPE_CHECKING:
    from rotkehlchen.assets.asset import AssetWithOracles
    from rotkehlchen.db.dbhandler import DBHandler
    from rotkehlchen.exchanges.data_structures import MarginPosition
    from rotkehlchen.exchanges.ibkr.types import IbkrPosition
    from rotkehlchen.fval import FVal
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
        self.account_id_override = ibkr_account_id or None
        self.gateway = IbkrGateway(base_url=ibkr_gateway_url)
        self.flex_account_id: str | None = None  # set once a Flex statement was read
        self._liabilities: dict[Asset, Balance] = {}

    def first_connection(self) -> None:
        self.first_connection_made = True

    def flex(self) -> FlexWebService:
        """Flex Web Service client from the connection's credentials: the api key is the
        Flex token and the secret the Flex query id."""
        return FlexWebService(token=self.api_key, query_id=self.secret.decode())

    def validate_api_key(self) -> tuple[bool, str]:
        """Only the Flex credentials decide. A gateway that isn't logged in yet is reported,
        since positions stay unavailable until the user logs in to it."""
        if not (result := self.flex().validate())[0]:
            return result
        if (status := self.gateway.status()) != GatewayStatus.OK:
            return True, f'Flex credentials are valid. The IBKR gateway at {self.gateway_url} is {status}: log in at {self.gateway_url} to see positions'  # noqa: E501
        return True, ''

    def account_id(self) -> str:
        """The IBKR account of this connection.

        May raise RemoteError if the gateway can't be read or sees several accounts that
        nothing disambiguates.
        """
        if self.account_id_override is not None:
            return self.account_id_override

        accounts = self.gateway.accounts()
        if len(accounts) == 1:
            return accounts[0]
        if self.flex_account_id is not None and self.flex_account_id in accounts:
            return self.flex_account_id
        raise RemoteError(
            f'IBKR gateway {self.gateway_url} exposes accounts {", ".join(accounts) or "none"}; '
            f'set the account id of the {self.name} connection',
        )

    def last_liabilities(self) -> dict[Asset, Balance]:
        return self._liabilities

    def query_balances(self, **kwargs: Any) -> ExchangeQueryBalances:
        """Long positions and cash are assets, short positions and negative cash liabilities.
        Values come from IBKR's own marks, converted to the main currency."""
        self._liabilities = {}
        try:
            account = self.account_id()
            positions = self.gateway.positions(account)
            cash = self.gateway.ledger(account)
        except RemoteError as e:
            return None, f'{self.name}: {e!s}'

        main_currency = CachedSettings().main_currency
        rates: dict[str, FVal] = {}
        for currency in {p.currency for p in positions} | set(cash):
            try:
                rate = Inquirer.find_price(Asset(currency), main_currency)
            except UnknownAsset:
                rate = Price(ZERO)
            if rate == ZERO:
                return None, f'{self.name}: no {currency} to {main_currency.identifier} price to value IBKR holdings'  # noqa: E501
            rates[currency] = rate

        assets: defaultdict[Asset, Balance] = defaultdict(Balance)
        liabilities: defaultdict[Asset, Balance] = defaultdict(Balance)
        for position in positions:
            if position.position == ZERO:  # closed or expired today, still listed
                continue
            asset = self._contract_asset(position)
            balance = Balance(
                amount=abs(position.position),
                value=abs(position.mkt_value) * rates[position.currency],
            )
            GlobalDBHandler.add_manual_latest_price(
                from_asset=asset,
                to_asset=main_currency,
                price=Price(balance.value / balance.amount),
            )
            (assets if position.position > ZERO else liabilities)[asset] += balance

        for currency, amount in cash.items():
            if amount == ZERO:
                continue
            balance = Balance(amount=abs(amount), value=abs(amount) * rates[currency])
            (assets if amount > ZERO else liabilities)[Asset(currency)] += balance

        self._liabilities = dict(liabilities)
        # contract assets are custom assets, which have no price oracles
        return cast('dict[AssetWithOracles, Balance]', dict(assets)), ''

    def query_positions(self) -> tuple[str | None, GatewayStatus, list[IbkrPosition]]:
        """Account id, gateway status and the open positions, for the IBKR positions page.

        A gateway that isn't usable yields its status and no positions instead of raising.
        May raise RemoteError if a usable gateway fails mid-query.
        """
        if (status := self.gateway.status()) != GatewayStatus.OK:
            return self.account_id_override, status, []
        account = self.account_id()
        return account, status, self.gateway.positions(account)

    def query_positions_summary(self) -> dict[str, Any]:
        """Serialized positions with totals converted to the main currency"""
        account, status, positions = self.query_positions()
        main_currency = CachedSettings().main_currency
        rates = {
            currency: Inquirer.find_price(Asset(currency), main_currency)
            for currency in {p.currency for p in positions}
        }
        return {
            'account_id': account,
            'gateway_url': self.gateway_url,
            'status': str(status),
            'positions': [position.serialize() for position in positions],
            'totals': {
                'market_value': str(sum((p.mkt_value * rates[p.currency] for p in positions), start=ZERO)),  # noqa: E501
                'unrealized_pnl': str(sum((p.unrealized_pnl * rates[p.currency] for p in positions), start=ZERO)),  # noqa: E501
                'currency': main_currency.identifier,
            },
        }

    def _contract_asset(self, position: IbkrPosition) -> Asset:
        return get_or_create_contract_asset(
            self.db,
            conid=position.conid,
            description=position.contract_desc,
            asset_class=position.asset_class,
            underlying=position.ticker,
            put_or_call=position.put_or_call,
            strike=position.strike,
            expiry=position.expiry,
            multiplier=position.multiplier,
        )

    def query_online_margin_history(
            self,
            start_ts: Timestamp,
            end_ts: Timestamp,
    ) -> list[MarginPosition]:
        return []
