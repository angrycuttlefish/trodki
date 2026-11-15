"""trodki: open Hyperliquid perp positions, across the main DEX and HIP-3 DEXs."""
from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
import requests

from rotkehlchen.chain.evm.types import string_to_evm_address
from rotkehlchen.errors.misc import RemoteError
from rotkehlchen.externalapis.hyperliquid import HyperliquidAPI
from rotkehlchen.fval import FVal
from rotkehlchen.tests.utils.api import (
    api_url_for,
    assert_error_response,
    assert_proper_sync_response_with_result,
)

if TYPE_CHECKING:
    from rotkehlchen.api.server import APIServer
    from rotkehlchen.types import ChecksumEvmAddress

TRADER = string_to_evm_address('0x6575B595806cfF7a6F7F350A66e1D6168826c4C1')
FAILED_TRADER = string_to_evm_address('0x5A0b54D5dc17e0AadC383d2db43B0a0D3E029c4c')
FLAT_TRADER = string_to_evm_address('0x33046dC9Bc0872686662A2EAfeA1861725beB19F')
NVDA = {  # a live xyz position
    'coin': 'xyz:NVDA', 'szi': '0.068', 'leverage': {'type': 'cross', 'value': 3},
    'entryPx': '182.46', 'positionValue': '10.87592', 'unrealizedPnl': '-1.53136',
    'returnOnEquity': '-0.3702729365', 'liquidationPx': None, 'marginUsed': '3.625306',
    'maxLeverage': 20, 'cumFunding': {'allTime': '0.031673', 'sinceOpen': '0.025508', 'sinceChange': '0.025508'},  # noqa: E501
}
BTC_SHORT = {
    'coin': 'BTC', 'szi': '-0.5', 'leverage': {'type': 'isolated', 'value': 10, 'rawUsd': '1'},
    'entryPx': '70000', 'positionValue': '32500', 'unrealizedPnl': '2500',
    'returnOnEquity': '0.71', 'liquidationPx': '76000.5', 'marginUsed': '3500',
    'cumFunding': {'allTime': '-3', 'sinceOpen': '-2', 'sinceChange': '-2'},
}


def _states(address: str, account_type: str, dex_name: str | None = None) -> dict[str, Any]:
    assert account_type == 'clearinghouseState'
    if dex_name == 'broken':
        raise RemoteError('dex down')
    if address == FLAT_TRADER:
        return {'assetPositions': []}
    return {'assetPositions': [{'type': 'oneWay', 'position': {None: BTC_SHORT, 'xyz': NVDA}[dex_name]}] + ([{'type': 'oneWay', 'position': {'coin': 'ETH'}}] if dex_name is None else [])}  # noqa: E501


def test_query_perp_positions_covers_every_dex() -> None:
    """Positions of the main and HIP-3 DEXs are returned; a failing HIP-3 DEX and a
    malformed position are skipped."""
    api = HyperliquidAPI()
    with (
        patch.object(api, '_discover_available_dex_names', return_value=['broken', 'xyz']),
        patch.object(api, '_query', side_effect=_states),
    ):
        positions = api.query_perp_positions(TRADER)

    assert [(p.dex, p.market, p.side) for p in positions] == [(None, 'BTC', 'short'), ('xyz', 'xyz:NVDA', 'long')]  # noqa: E501
    btc, nvda = positions
    assert (btc.size, btc.mark_price, btc.leverage, btc.leverage_type) == (FVal('0.5'), FVal('65000'), FVal(10), 'isolated')  # noqa: E501
    assert (btc.liquidation_price, btc.funding_since_open) == (FVal('76000.5'), FVal(-2))
    assert nvda.liquidation_price is None
    assert nvda.serialize()['unrealized_pnl'] == '-1.53136'


def test_query_perp_positions_main_dex_failure_raises() -> None:
    api = HyperliquidAPI()
    with (
        patch.object(api, '_discover_available_dex_names', return_value=[]),
        patch.object(api, '_query', side_effect=RemoteError('api down')),
        pytest.raises(RemoteError),
    ):
        api.query_perp_positions(TRADER)


@pytest.mark.parametrize('hyperliquid_accounts', [[TRADER, FAILED_TRADER, FLAT_TRADER]])
def test_hyperliquid_perp_positions_endpoint(
        rotkehlchen_api_server: APIServer,
        hyperliquid_accounts: list[ChecksumEvmAddress],  # pylint: disable=unused-argument
) -> None:
    """Positions are keyed by address, a flat address is left out and a failed one listed."""
    def query(self: HyperliquidAPI, address: str, account_type: str, dex_name: str | None = None) -> dict[str, Any]:  # noqa: E501
        if address == FAILED_TRADER:
            raise RemoteError('rate limited')
        return _states(address, account_type, dex_name)

    with (
        patch.object(HyperliquidAPI, '_discover_available_dex_names', return_value=[]),
        patch.object(HyperliquidAPI, '_query', autospec=True, side_effect=query),
    ):
        result = assert_proper_sync_response_with_result(requests.get(
            api_url_for(rotkehlchen_api_server, 'hyperliquidperppositionsresource'),
        ))

    assert result == {'accounts': {TRADER: [{
        'dex': None, 'market': 'BTC', 'side': 'short', 'size': '0.5', 'entry_price': '70000',
        'mark_price': '65000', 'position_value': '32500', 'unrealized_pnl': '2500',
        'return_on_equity': '0.71', 'margin_used': '3500', 'leverage': '10',
        'leverage_type': 'isolated', 'liquidation_price': '76000.5', 'funding_since_open': '-2',
    }]}, 'failed': [FAILED_TRADER]}


@pytest.mark.parametrize('hyperliquid_accounts', [[TRADER]])
def test_hyperliquid_perp_positions_endpoint_remote_error(rotkehlchen_api_server: APIServer) -> None:  # noqa: E501
    with patch.object(HyperliquidAPI, 'query_perp_positions', side_effect=RemoteError('api down')):
        response = requests.get(api_url_for(rotkehlchen_api_server, 'hyperliquidperppositionsresource'))  # noqa: E501

    assert_error_response(response=response, contained_in_msg='api down', status_code=HTTPStatus.BAD_GATEWAY)  # noqa: E501
