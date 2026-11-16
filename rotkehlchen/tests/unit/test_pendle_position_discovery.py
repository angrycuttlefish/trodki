"""trodki: tokens of open Pendle positions are created from Pendle's API before detection."""
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from rotkehlchen.assets.asset import EvmToken
from rotkehlchen.chain.evm.decoding.pendle import utils as pendle_utils
from rotkehlchen.chain.evm.decoding.pendle.constants import CPT_PENDLE
from rotkehlchen.chain.evm.decoding.pendle.utils import create_pendle_position_tokens
from rotkehlchen.chain.evm.types import string_to_evm_address
from rotkehlchen.errors.asset import UnknownAsset
from rotkehlchen.errors.misc import RemoteError
from rotkehlchen.types import ChainID

if TYPE_CHECKING:
    from rotkehlchen.db.dbhandler import DBHandler

pytestmark = pytest.mark.parametrize('pendle_position_discovery_enabled', [True], indirect=True)
ADDRESS = string_to_evm_address('0x6575B595806cfF7a6F7F350A66e1D6168826c4C1')
MARKET = '0x4ccf6deb3d1895373f604b418ff55d8adae8b846'
LP, PT, YT = MARKET, '0xba96292ee7673e3b546cc90db6d97111cd9a314f', '0x480c3c9470fa4bbda030f6396fa4b17adefc1ce0'  # noqa: E501
POSITIONS = {'positions': [
    {'chainId': 1, 'openPositions': [{'marketId': f'1-{MARKET}'}], 'closedPositions': []},
    {'chainId': 8453, 'openPositions': [], 'closedPositions': [{'marketId': '8453-0xdead'}]},
]}
MARKET_DETAILS = {
    'lp': {'address': LP, 'symbol': 'PLP-USDat-14JAN2027', 'name': 'PLP-USDat-14JAN2027', 'decimals': 18},  # noqa: E501
    'pt': {'address': PT, 'symbol': 'PT-USDat-14JAN2027', 'name': 'PT-USDat-14JAN2027', 'decimals': 6},  # noqa: E501
    'yt': {'address': YT, 'symbol': 'YT-USDat-14JAN2027', 'name': 'YT-USDat-14JAN2027', 'decimals': 6},  # noqa: E501
}


@pytest.fixture(autouse=True)
def _clear_positions_cache() -> None:
    pendle_utils._open_markets_cache.clear()


def _api(url: str, **kwargs: Any) -> dict[str, Any]:
    assert kwargs['handle_429'] is True
    if '/dashboard/positions/database/' in url:
        return POSITIONS
    if url.endswith(f'/1/markets/{MARKET}'):
        return MARKET_DETAILS
    raise AssertionError(f'unexpected url {url}')


def test_open_position_tokens_are_created_as_pendle_tokens(database: DBHandler) -> None:
    with patch.object(pendle_utils, 'request_get_dict', side_effect=_api) as api:
        create_pendle_position_tokens(database=database, chain_id=ChainID.ETHEREUM, addresses=[ADDRESS])  # noqa: E501
        # another chain reuses the cached positions and has no open market
        create_pendle_position_tokens(database=database, chain_id=ChainID.BASE, addresses=[ADDRESS])  # noqa: E501

    assert api.call_count == 2  # positions once, market details once
    for address, symbol, decimals in ((LP, 'PLP-USDat-14JAN2027', 18), (PT, 'PT-USDat-14JAN2027', 6), (YT, 'YT-USDat-14JAN2027', 6)):  # noqa: E501
        token = EvmToken(f'eip155:1/erc20:{string_to_evm_address(address)}')
        assert (token.symbol, token.decimals, token.protocol) == (symbol, decimals, CPT_PENDLE)


def test_position_discovery_failure_creates_nothing(database: DBHandler) -> None:
    with patch.object(pendle_utils, 'request_get_dict', side_effect=RemoteError('pendle down')):
        create_pendle_position_tokens(database=database, chain_id=ChainID.ETHEREUM, addresses=[ADDRESS])  # noqa: E501

    with pytest.raises(UnknownAsset):
        EvmToken(f'eip155:1/erc20:{string_to_evm_address(LP)}')


def test_token_detection_runs_pendle_discovery_first(ethereum_inquirer: Any, database: DBHandler) -> None:  # noqa: E501
    from rotkehlchen.chain.ethereum.tokens import EthereumTokens
    tokens = EthereumTokens(database=database, evm_inquirer=ethereum_inquirer)
    calls: list[str] = []

    def discover(**kwargs: Any) -> None:
        calls.append('pendle')

    def detection_data(**kwargs: Any) -> tuple[list, list]:
        calls.append('detect')
        return [], []

    with (
        patch('rotkehlchen.chain.evm.tokens.create_pendle_position_tokens', side_effect=discover),
        patch('rotkehlchen.globaldb.handler.GlobalDBHandler.get_token_detection_data', side_effect=detection_data),  # noqa: E501
        patch.object(tokens, '_detect_tokens', return_value=({}, set(), {})),
        patch.object(tokens, '_detect_erc721_tokens', return_value={}),
    ):
        tokens._query_new_tokens([ADDRESS])

    assert calls[:2] == ['pendle', 'detect']
