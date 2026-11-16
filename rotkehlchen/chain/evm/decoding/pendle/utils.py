import logging
import time
from collections import defaultdict
from http import HTTPStatus
from threading import Lock
from typing import TYPE_CHECKING, Final

import requests

from rotkehlchen.assets.utils import get_or_create_evm_token
from rotkehlchen.chain.evm.decoding.pendle.constants import CPT_PENDLE
from rotkehlchen.constants.prices import ZERO_PRICE
from rotkehlchen.errors.misc import RemoteError, UnableToDecryptRemoteData
from rotkehlchen.errors.serialization import DeserializationError
from rotkehlchen.globaldb.cache import globaldb_set_general_cache_values
from rotkehlchen.globaldb.handler import GlobalDBHandler
from rotkehlchen.history.deserialization import deserialize_price
from rotkehlchen.logging import RotkehlchenLogsAdapter
from rotkehlchen.serialization.deserialize import deserialize_evm_address
from rotkehlchen.types import CacheType, ChainID, Price
from rotkehlchen.utils.network import create_session, request_get_dict

if TYPE_CHECKING:
    from collections.abc import Sequence

    from rotkehlchen.assets.asset import EvmToken
    from rotkehlchen.db.dbhandler import DBHandler
    from rotkehlchen.types import ChecksumEvmAddress

logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)


def query_pendle_markets(chain: ChainID) -> None:
    """Query Pendle markets for a given chain and cache their addresses."""
    all_markets, all_sy_tokens = [], []
    session = create_session()
    try:
        for market_type in ('active', 'inactive'):  # query active and inactive markets
            response = session.get(url=f'https://api-v2.pendle.finance/core/v1/{chain.serialize()}/markets/{market_type}')
            if response.status_code != HTTPStatus.OK:
                log.error(
                    f'Pendle {market_type} markets query for {chain} failed '
                    f'with status {response.status_code} and message {response.text}',
                )
                return

            for market in response.json()['markets']:
                try:
                    all_markets.append(deserialize_evm_address(market['address']))
                    all_sy_tokens.append(deserialize_evm_address(market['sy'].split('-')[1]))
                except (DeserializationError, KeyError, IndexError, ValueError) as e:
                    msg = f'missing key {e!s}' if isinstance(e, KeyError) else f'{e!s}'
                    log.warning(f'Skipping pendle market entry {market} for {chain} due to {msg}')
                    continue

    except (requests.RequestException, TypeError, KeyError) as e:
        msg = f'missing key {e!s}' if isinstance(e, KeyError) else f'{e!s}'
        log.error(f'Failed to retrieve Pendle markets for {chain} due to {msg}')

    with GlobalDBHandler().conn.write_ctx() as write_cursor:
        globaldb_set_general_cache_values(
            write_cursor=write_cursor,
            key_parts=(CacheType.PENDLE_POOLS, str(chain.serialize())),
            values=all_markets,
        )
        globaldb_set_general_cache_values(
            write_cursor=write_cursor,
            key_parts=(CacheType.PENDLE_SY_TOKENS, str(chain.serialize())),
            values=all_sy_tokens,
        )


def query_pendle_price(token: EvmToken) -> Price:
    """Query USD price for a given Pendle PT/YT/SY/LP token"""
    try:
        result = request_get_dict(f'https://api-v2.pendle.finance/core/v1/{token.chain_id.serialize()}/assets/prices?addresses={token.evm_address}')
        return deserialize_price(result['prices'][token.evm_address.lower()])
    except (RemoteError, UnableToDecryptRemoteData, DeserializationError, TypeError, ValueError, KeyError) as e:  # noqa: E501
        msg = f'missing key {e!s}' if isinstance(e, KeyError) else f'{e!s}'
        log.error(f'Unable to query usd price of pendle wrapped token {token} due to {msg}')
        return ZERO_PRICE


# trodki: Pendle positions found through Pendle's public API, so their LP/PT/YT tokens are
# known to token detection without decoding the user's transactions first.
PENDLE_API_URL: Final = 'https://api-v2.pendle.finance/core/v1'
PENDLE_POSITIONS_CACHE_SECONDS: Final = 300
PENDLE_RATE_LIMIT_BACKOFF_SECONDS: Final = 2
_open_markets_cache: dict[str, tuple[float, dict[int, list[str]]]] = {}
_open_markets_lock = Lock()


def query_pendle_open_markets(address: ChecksumEvmAddress) -> dict[int, list[str]]:
    """Return the markets in which the address has an open Pendle position, by chain id.

    One call covers every chain, and token detection runs per chain, so the answer is cached
    for a few minutes per address.

    May raise RemoteError, UnableToDecryptRemoteData.
    """
    with _open_markets_lock:
        if (cached := _open_markets_cache.get(address)) is not None and time.monotonic() - cached[0] < PENDLE_POSITIONS_CACHE_SECONDS:  # noqa: E501
            return cached[1]

        result = request_get_dict(
            url=f'{PENDLE_API_URL}/dashboard/positions/database/{address}?filterUsd=0',
            handle_429=True,
            backoff_in_seconds=PENDLE_RATE_LIMIT_BACKOFF_SECONDS,
        )
        markets: defaultdict[int, list[str]] = defaultdict(list)
        try:
            for chain_positions in result['positions']:
                for position in chain_positions['openPositions']:
                    # marketId is `{chainId}-{market address}`
                    markets[int(chain_positions['chainId'])].append(position['marketId'].split('-')[1])
        except (KeyError, TypeError, ValueError, IndexError) as e:
            raise RemoteError(f'Unexpected Pendle positions response for {address}: {e!s}') from e

        _open_markets_cache[address] = (time.monotonic(), dict(markets))
        return dict(markets)


def create_pendle_position_tokens(
        database: DBHandler,
        chain_id: ChainID,
        addresses: Sequence[ChecksumEvmAddress],
) -> None:
    """Create the LP, PT and YT tokens of every market where the addresses have an open
    Pendle position on the given chain. Token detection then finds their balances on chain,
    and they are priced through Pendle's API like tokens created by the decoder.

    Failures are logged: detection then just misses the positions, as before.
    """
    for address in addresses:
        try:
            markets = query_pendle_open_markets(address).get(chain_id.value, [])
        except (RemoteError, UnableToDecryptRemoteData) as e:
            log.warning(f'Could not query Pendle positions of {address} due to {e!s}')
            continue

        for market in markets:
            try:
                details = request_get_dict(
                    url=f'{PENDLE_API_URL}/{chain_id.value}/markets/{market}',
                    handle_429=True,
                    backoff_in_seconds=PENDLE_RATE_LIMIT_BACKOFF_SECONDS,
                )
                for key in ('lp', 'pt', 'yt'):
                    token = details[key]
                    get_or_create_evm_token(
                        userdb=database,
                        evm_address=deserialize_evm_address(token['address']),
                        chain_id=chain_id,
                        symbol=token['symbol'],
                        name=token['name'],
                        decimals=int(token['decimals']),
                        protocol=CPT_PENDLE,
                    )
            except (RemoteError, UnableToDecryptRemoteData, DeserializationError, KeyError, TypeError, ValueError) as e:  # noqa: E501
                msg = f'missing key {e!s}' if isinstance(e, KeyError) else f'{e!s}'
                log.warning(f'Could not add the tokens of Pendle market {market} on {chain_id} due to {msg}')  # noqa: E501
