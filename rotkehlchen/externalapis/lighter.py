"""trodki: Lighter (zk perps exchange on Ethereum) account and pool balances.

Everything here uses Lighter's public, unauthenticated REST API, keyed by the user's L1
(Ethereum) address. Trades and history need a read-only token and are not covered.
https://apidocs.lighter.xyz
"""
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Final

import requests

from rotkehlchen.assets.asset import Asset
from rotkehlchen.assets.utils import get_or_create_evm_token
from rotkehlchen.concurrency import cancellable_sleep
from rotkehlchen.constants import ZERO
from rotkehlchen.constants.assets import A_ETH
from rotkehlchen.constants.resolver import evm_address_to_identifier
from rotkehlchen.db.settings import CachedSettings
from rotkehlchen.errors.misc import InputError, RemoteError
from rotkehlchen.errors.serialization import DeserializationError
from rotkehlchen.fval import FVal
from rotkehlchen.logging import RotkehlchenLogsAdapter
from rotkehlchen.serialization.deserialize import deserialize_evm_address, deserialize_fval
from rotkehlchen.types import ChainID, ChecksumEvmAddress
from rotkehlchen.utils.network import create_session
from rotkehlchen.utils.rate_limiter import TokenBucket

if TYPE_CHECKING:
    from rotkehlchen.db.dbhandler import DBHandler

logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)

LIGHTER_API_URL: Final = 'https://mainnet.zklighter.elliot.ai/api/v1'
LIGHTER_ACCOUNT_NOT_FOUND: Final = 21100
# Standard accounts get 60 requests per rolling minute, per IP and per L1 address. A rate
# limited request gets 429 (or 405 from the firewall, which cools down for 60 seconds).
# https://docs.lighter.xyz/developers/reference/rate-limits
LIGHTER_REQUESTS_PER_SECOND: Final = 1
LIGHTER_REQUEST_BURST: Final = 10
LIGHTER_RATE_LIMITED_STATUSES: Final = (
    HTTPStatus.TOO_MANY_REQUESTS,
    HTTPStatus.METHOD_NOT_ALLOWED,
)
LIGHTER_MAX_BACKOFF_SECONDS: Final = 60
LIGHTER_ASSETS_CACHE_SECONDS: Final = 300
LIGHTER_USDC_SYMBOL: Final = 'USDC'
ZERO_ADDRESS: Final = '0x0000000000000000000000000000000000000000'


@dataclass(frozen=True)
class LighterAsset:
    """A Lighter asset as listed by `assetDetails`. All of them are Ethereum L1 assets."""
    symbol: str
    l1_address: str
    l1_decimals: int
    index_price: FVal


class LighterAPI:

    def __init__(
            self,
            database: DBHandler,
            session: requests.Session | None = None,
            rate_limiter: TokenBucket | None = None,
    ) -> None:
        self.database = database
        self.session = session if session is not None else create_session()
        self.rate_limiter = rate_limiter if rate_limiter is not None else TokenBucket(
            rps=LIGHTER_REQUESTS_PER_SECOND,
            capacity=LIGHTER_REQUEST_BURST,
        )
        self._assets_lock = threading.Lock()
        self._assets_fetched_at = 0.0
        self._assets: dict[str, LighterAsset] | None = None

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Query a public endpoint. Returns None if the account does not exist.

        Requests are paced to Lighter's public limit. A rate limited response is retried
        with exponential backoff up to the user's query retry limit.

        May raise:
        - RemoteError
        """
        url = f'{LIGHTER_API_URL}/{path}'
        cached_settings = CachedSettings()
        retries_left, backoff = cached_settings.get_query_retry_limit(), 1
        while True:
            self.rate_limiter.acquire()
            try:
                response = self.session.get(url, params=params, timeout=cached_settings.get_timeout_tuple())  # noqa: E501
            except requests.RequestException as e:
                raise RemoteError(f'Lighter request to {url} failed due to {e}') from e

            if response.status_code not in LIGHTER_RATE_LIMITED_STATUSES:
                break
            self.rate_limiter.shrink_after_429()
            if retries_left <= 0:
                raise RemoteError(f'Lighter {path} is still rate limited after retrying')

            backoff = min(backoff * 2, LIGHTER_MAX_BACKOFF_SECONDS)
            wait_seconds = backoff
            if (retry_after := response.headers.get('Retry-After')) is not None:
                try:
                    wait_seconds = min(max(int(retry_after), 1), LIGHTER_MAX_BACKOFF_SECONDS)
                except ValueError:
                    pass
            elif response.status_code == HTTPStatus.METHOD_NOT_ALLOWED:
                wait_seconds = LIGHTER_MAX_BACKOFF_SECONDS
            log.debug(f'Lighter {path} returned {response.status_code}. Backing off for {wait_seconds} seconds')  # noqa: E501
            cancellable_sleep(wait_seconds)
            retries_left -= 1

        try:
            data = response.json()
        except requests.JSONDecodeError as e:
            raise RemoteError(f'Lighter {path} returned non-JSON response {response.text[:200]}') from e  # noqa: E501

        if not isinstance(data, dict):
            raise RemoteError(f'Lighter {path} returned unexpected response {data!r}')
        if data.get('code') == LIGHTER_ACCOUNT_NOT_FOUND:
            return None
        if response.status_code != 200 or data.get('code') != 200:
            raise RemoteError(f'Lighter {path} returned {response.status_code}: {data}')

        return data

    def _lighter_assets(self) -> dict[str, LighterAsset]:
        """May raise RemoteError, DeserializationError, KeyError, TypeError, ValueError"""
        with self._assets_lock:
            now = time.monotonic()
            if self._assets is not None and now - self._assets_fetched_at < LIGHTER_ASSETS_CACHE_SECONDS:  # noqa: E501
                return self._assets

            data = self._get('assetDetails', {})
            if data is None:
                raise RemoteError('Lighter assetDetails returned account-not-found')
            self._assets = {
                entry['symbol']: LighterAsset(
                    symbol=entry['symbol'],
                    l1_address=entry['l1_address'],
                    l1_decimals=int(entry['l1_decimals']),
                    index_price=deserialize_fval(entry['index_price'], 'index_price', 'lighter'),
                ) for entry in (data.get('asset_details') or [])
            }
            self._assets_fetched_at = time.monotonic()
            return self._assets

    def _to_asset(self, lighter_asset: LighterAsset) -> Asset:
        """Map a Lighter asset to its Ethereum asset, adding the token if it is not known.

        May raise DeserializationError, InputError.
        """
        if lighter_asset.l1_address == ZERO_ADDRESS:
            return A_ETH
        evm_address = deserialize_evm_address(lighter_asset.l1_address)
        existing = Asset(evm_address_to_identifier(evm_address, ChainID.ETHEREUM))
        if existing.exists():
            return existing
        return get_or_create_evm_token(
            userdb=self.database,
            evm_address=evm_address,
            chain_id=ChainID.ETHEREUM,
            symbol=lighter_asset.symbol,
            decimals=lighter_asset.l1_decimals,
        )

    @staticmethod
    def _holdings(account: dict[str, Any]) -> dict[str, FVal]:
        """The holdings of a Lighter account by asset symbol.

        An asset is held either as spot (`balance` + `locked_balance`) or as margin collateral
        (`margin_balance`); the two overlap rather than add up (the LLP reports its ETH only as
        margin, LIT staking its LIT only as spot, and USDC margin includes the USDC balance),
        so the larger counts. The unrealized PnL of the open perp positions is added to USDC,
        giving the account's USDC equity. May raise DeserializationError, KeyError, TypeError.
        """
        holdings: defaultdict[str, FVal] = defaultdict(FVal)
        for entry in account.get('assets') or []:
            spot = deserialize_fval(entry['balance'], 'balance', 'lighter') + deserialize_fval(entry['locked_balance'], 'locked_balance', 'lighter')  # noqa: E501
            margin = deserialize_fval(entry['margin_balance'], 'margin_balance', 'lighter')
            holdings[entry['symbol']] += max(spot, margin)

        for position in account.get('positions') or []:
            holdings[LIGHTER_USDC_SYMBOL] += deserialize_fval(position['unrealized_pnl'], 'unrealized_pnl', 'lighter')  # noqa: E501

        return holdings

    def _pool_share_holdings(self, pool_index: int, shares: int) -> dict[str, FVal]:
        """The holdings that `shares` of a public pool represent, by asset symbol.

        A pool with open perp positions (such as the LLP) is a USD vault: its share is valued
        in USDC, pricing the pool's non USDC assets at Lighter's index price. A pool without
        positions (such as LIT staking) is a share of the tokens it holds.

        May raise RemoteError, DeserializationError, KeyError, TypeError, ValueError, ZeroDivisionError.
        """
        data = self._get('account', {'by': 'index', 'value': pool_index})
        if data is None:
            raise RemoteError(f'Lighter pool {pool_index} not found')

        accounts = data.get('accounts') or []
        if len(accounts) == 0:
            raise RemoteError(f'Lighter pool {pool_index} returned no accounts')
        pool = accounts[0]
        total_shares = deserialize_fval(pool['pool_info']['total_shares'], 'total_shares', 'lighter')  # noqa: E501
        fraction = FVal(shares) / total_shares
        holdings = self._holdings(pool)
        if not any(
            deserialize_fval(p['position'], 'position', 'lighter') != ZERO
            for p in (pool.get('positions') or [])
        ):
            return {symbol: amount * fraction for symbol, amount in holdings.items()}

        lighter_assets = self._lighter_assets()
        value = sum(
            (amount if symbol == LIGHTER_USDC_SYMBOL else amount * lighter_assets[symbol].index_price)  # noqa: E501
            for symbol, amount in holdings.items()
        )
        return {LIGHTER_USDC_SYMBOL: FVal(value) * fraction}

    def query_balances(self, address: ChecksumEvmAddress) -> dict[Asset, FVal]:
        """Query the Lighter balances of an L1 address: the collateral and assets of every
        sub-account and the shares it holds in public pools (LLP, LIT staking, ...).

        A pool or asset that cannot be read is logged and skipped.

        May raise:
        - RemoteError if the account query fails
        """
        data = self._get('account', {'by': 'l1_address', 'value': address})
        if data is None:
            return {}

        holdings: defaultdict[str, FVal] = defaultdict(FVal)
        for account in data.get('accounts') or []:
            try:
                for symbol, amount in self._holdings(account).items():
                    holdings[symbol] += amount
            except (DeserializationError, KeyError, TypeError, ValueError) as e:
                log.error(f'Failed to read Lighter account {account.get("index")} of {address}: {e}')  # noqa: E501

            for share in account.get('shares') or []:
                try:
                    shares_amount = int(share['shares_amount'])
                    if shares_amount == 0:
                        continue
                    pool_holdings = self._pool_share_holdings(
                        pool_index=int(share['public_pool_index']),
                        shares=shares_amount,
                    )
                except (
                    RemoteError,
                    DeserializationError,
                    KeyError,
                    TypeError,
                    ValueError,
                    IndexError,
                    ZeroDivisionError,
                ) as e:
                    log.error(f'Failed to read Lighter pool share {share} of {address}: {e}')
                    continue

                for symbol, amount in pool_holdings.items():
                    holdings[symbol] += amount

        balances: dict[Asset, FVal] = {}
        for symbol, amount in holdings.items():
            if amount == ZERO:
                continue
            try:
                asset = self._to_asset(self._lighter_assets()[symbol])
            except (RemoteError, DeserializationError, InputError, KeyError, TypeError, ValueError) as e:  # noqa: E501
                log.error(f'Skipping Lighter balance of {amount} {symbol} for {address}: {e}')
                continue
            balances[asset] = balances.get(asset, ZERO) + amount

        return balances
