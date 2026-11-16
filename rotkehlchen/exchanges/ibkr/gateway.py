"""trodki: read-only client for the Interactive Brokers Client Portal Gateway.

The gateway runs on the user's machine and the user logs in to it in their own browser.
Only read-only endpoints are used (`/portfolio/*` and `/tickle`): the brokerage endpoints
(`/iserver/*`) would take over the username's single trading session and log the user out
of TWS / IBKR Mobile, so `_url` refuses to build them.
https://www.interactivebrokers.com/docs/web-api/authentication/sessions
"""
import datetime
import logging
import time
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Final, Literal
from urllib.parse import urlparse

import requests

from rotkehlchen.db.settings import CachedSettings
from rotkehlchen.errors.misc import RemoteError
from rotkehlchen.errors.serialization import DeserializationError
from rotkehlchen.exchanges.ibkr.types import GatewayStatus, IbkrPosition
from rotkehlchen.logging import RotkehlchenLogsAdapter
from rotkehlchen.serialization.deserialize import deserialize_fval
from rotkehlchen.utils.network import create_session
from rotkehlchen.utils.rate_limiter import TokenBucket

if TYPE_CHECKING:
    from rotkehlchen.fval import FVal

logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)

# IBKR allows 10 req/s globally and sends a violating IP to a 15 minute penalty box.
# https://www.interactivebrokers.com/docs/web-api/v1/pacing-limitations
GATEWAY_REQUESTS_PER_SECOND: Final = 5
GATEWAY_REQUEST_BURST: Final = 5
PENALTY_BOX_SECONDS: Final = 900
ACCOUNTS_MIN_INTERVAL_SECONDS: Final = 5
POSITIONS_PAGE_SIZE: Final = 100
LOCAL_HOSTS: Final = ('localhost', '127.0.0.1')
FORBIDDEN_PREFIX: Final = '/' + 'iserver'
LEDGER_BASE_KEY: Final = 'BASE'


class IbkrRateLimitedError(RemoteError):
    """The gateway answered 429; IBKR keeps the IP in a penalty box for a while"""


class IbkrLoggedOutError(RemoteError):
    """The gateway is running but no user is logged in to it"""


class IbkrUnreachableError(RemoteError):
    """Nothing answered at the gateway URL"""


class IbkrGateway:

    def __init__(
            self,
            base_url: str,
            session: requests.Session | None = None,
            rate_limiter: TokenBucket | None = None,
    ) -> None:
        self.base_url = base_url.rstrip('/')
        self.session = session if session is not None else create_session()
        self.rate_limiter = rate_limiter if rate_limiter is not None else TokenBucket(
            rps=GATEWAY_REQUESTS_PER_SECOND,
            capacity=GATEWAY_REQUEST_BURST,
        )
        # the gateway serves a self-signed certificate on the user's own machine
        self.verify_tls = urlparse(self.base_url).hostname not in LOCAL_HOSTS
        self._penalty_until = 0.0
        self._accounts: tuple[float, list[str]] | None = None

    def _url(self, path: str) -> str:
        if path.startswith(FORBIDDEN_PREFIX):
            raise ValueError(f'trodki never calls brokerage session endpoints such as {path}')
        return f'{self.base_url}/v1/api{path}'

    def _get(self, path: str) -> Any:
        """May raise:
        - IbkrRateLimitedError, IbkrLoggedOutError, IbkrUnreachableError, RemoteError
        """
        if time.monotonic() < self._penalty_until:
            raise IbkrRateLimitedError(f'IBKR gateway {self.base_url} is rate limited, waiting')

        url = self._url(path)
        self.rate_limiter.acquire()
        try:
            response = self.session.get(
                url=url,
                verify=self.verify_tls,
                timeout=CachedSettings().get_timeout_tuple(),
            )
        except requests.RequestException as e:
            raise IbkrUnreachableError(f'IBKR gateway at {self.base_url} is not reachable: {e}') from e  # noqa: E501

        if response.status_code == HTTPStatus.TOO_MANY_REQUESTS:
            self._penalty_until = time.monotonic() + PENALTY_BOX_SECONDS
            log.warning(f'IBKR gateway {self.base_url} rate limited us. Pausing {PENALTY_BOX_SECONDS}s')  # noqa: E501
            raise IbkrRateLimitedError(f'IBKR gateway {self.base_url} is rate limited, waiting')
        if response.status_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
            raise IbkrLoggedOutError(f'IBKR gateway {self.base_url} is not logged in. Log in at {self.base_url}')  # noqa: E501
        if response.status_code != HTTPStatus.OK:
            raise RemoteError(f'IBKR gateway {path} returned {response.status_code}: {response.text[:200]}')  # noqa: E501

        try:
            return response.json()
        except requests.JSONDecodeError as e:
            raise RemoteError(f'IBKR gateway {path} returned non-JSON {response.text[:200]}') from e  # noqa: E501

    def tickle(self) -> GatewayStatus:
        """Keep the read-only session alive and report its state"""
        try:
            self._get('/tickle')
        except IbkrRateLimitedError:
            return GatewayStatus.RATE_LIMITED
        except IbkrLoggedOutError:
            return GatewayStatus.LOGGED_OUT
        except IbkrUnreachableError:
            return GatewayStatus.UNREACHABLE
        except RemoteError as e:
            log.error(f'Unexpected IBKR gateway tickle failure: {e!s}')
            return GatewayStatus.UNREACHABLE
        return GatewayStatus.OK

    def status(self) -> GatewayStatus:
        return self.tickle()

    def accounts(self) -> list[str]:
        """The account ids the logged-in username sees. Also a prerequisite of the other
        portfolio calls, rate limited by IBKR to once per 5 seconds.

        May raise RemoteError
        """
        if self._accounts is not None and time.monotonic() - self._accounts[0] < ACCOUNTS_MIN_INTERVAL_SECONDS:  # noqa: E501
            return self._accounts[1]

        data = self._get('/portfolio/accounts')
        try:
            accounts = [str(entry.get('accountId') or entry['id']) for entry in data]
        except (KeyError, TypeError, AttributeError) as e:
            raise RemoteError(f'Unexpected IBKR portfolio accounts response {data!r}') from e

        self._accounts = (time.monotonic(), accounts)
        return accounts

    def positions(self, account_id: str) -> list[IbkrPosition]:
        """All open positions of the account. Rows with zero size are dropped.

        May raise RemoteError
        """
        self.accounts()
        positions: list[IbkrPosition] = []
        page = 0
        while True:
            rows = self._get(f'/portfolio/{account_id}/positions/{page}')
            if not isinstance(rows, list):
                raise RemoteError(f'Unexpected IBKR positions response {rows!r}')
            for row in rows:
                try:
                    position = _deserialize_position(row)
                except (DeserializationError, KeyError, TypeError, ValueError) as e:
                    raise RemoteError(f'Could not read IBKR position {row!r}: {e!s}') from e
                if position.position != 0:
                    positions.append(position)
            if len(rows) < POSITIONS_PAGE_SIZE:
                return positions
            page += 1

    def ledger(self, account_id: str) -> dict[str, FVal]:
        """Cash per currency. The aggregated `BASE` entry is left out.

        May raise RemoteError
        """
        data = self._get(f'/portfolio/{account_id}/ledger')
        try:
            return {
                currency: deserialize_fval(entry['cashbalance'], 'cashbalance', 'ibkr')
                for currency, entry in data.items()
                if currency != LEDGER_BASE_KEY
            }
        except (AttributeError, KeyError, TypeError, DeserializationError) as e:
            raise RemoteError(f'Unexpected IBKR ledger response {data!r}') from e

    def net_liquidation(self, account_id: str) -> tuple[FVal, str]:
        """May raise RemoteError"""
        data = self._get(f'/portfolio/{account_id}/summary')
        try:
            entry = data['netliquidation']
            return deserialize_fval(entry['amount'], 'netliquidation', 'ibkr'), entry['currency']
        except (KeyError, TypeError, DeserializationError) as e:
            raise RemoteError(f'Unexpected IBKR account summary response {data!r}') from e


def _deserialize_position(row: dict[str, Any]) -> IbkrPosition:
    """May raise DeserializationError, KeyError, TypeError, ValueError"""
    put_or_call: Literal['C', 'P'] | None = row['putOrCall'] if row.get('putOrCall') in ('C', 'P') else None  # noqa: E501
    expiry = None
    if (raw_expiry := row.get('expiry')) not in (None, ''):
        expiry = datetime.datetime.strptime(str(raw_expiry), '%Y%m%d').replace(tzinfo=datetime.UTC).date()  # noqa: E501
    return IbkrPosition(
        conid=int(row['conid']),
        contract_desc=str(row.get('contractDesc') or row.get('ticker') or row['conid']),
        asset_class=str(row.get('assetClass') or ''),
        position=deserialize_fval(row['position'], 'position', 'ibkr'),
        mkt_price=deserialize_fval(row.get('mktPrice', 0), 'mktPrice', 'ibkr'),
        mkt_value=deserialize_fval(row.get('mktValue', 0), 'mktValue', 'ibkr'),
        avg_cost=deserialize_fval(row.get('avgCost', 0), 'avgCost', 'ibkr'),
        unrealized_pnl=deserialize_fval(row.get('unrealizedPnl', 0), 'unrealizedPnl', 'ibkr'),
        currency=str(row['currency']),
        ticker=row.get('ticker'),
        und_conid=None if row.get('undConid') in (None, 0) else int(row['undConid']),
        put_or_call=put_or_call,
        strike=None if row.get('strike') in (None, '', 0, '0') else deserialize_fval(row['strike'], 'strike', 'ibkr'),  # noqa: E501
        expiry=expiry,
        multiplier=deserialize_fval(row.get('multiplier') or 1, 'multiplier', 'ibkr'),
    )
