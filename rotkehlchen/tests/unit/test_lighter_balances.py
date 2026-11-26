"""trodki: Lighter account and public pool balances (LLP, LIT staking)."""
import json
from collections import defaultdict
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from rotkehlchen.accounting.structures.balance import Balance, BalanceSheet
from rotkehlchen.assets.asset import EvmToken
from rotkehlchen.chain.ethereum.manager import LIGHTER_BALANCE_LABEL
from rotkehlchen.chain.evm.types import string_to_evm_address
from rotkehlchen.constants.assets import A_ETH, A_USDC
from rotkehlchen.errors.misc import RemoteError
from rotkehlchen.externalapis.lighter import LighterAPI
from rotkehlchen.fval import FVal
from rotkehlchen.utils.rate_limiter import TokenBucket

if TYPE_CHECKING:
    from rotkehlchen.chain.aggregator import ChainsAggregator
    from rotkehlchen.chain.ethereum.manager import EthereumManager
    from rotkehlchen.db.dbhandler import DBHandler

ADDRESS = string_to_evm_address('0x6575B595806cfF7a6F7F350A66e1D6168826c4C1')
LIT_ADDRESS = '0x232CE3bd40fCd6f80f3d55A522d03f25Df784Ee2'
LLP, LIT_STAKING = 281474976710654, 281474976624800
pytestmark = pytest.mark.parametrize('lighter_balances_enabled', [True], indirect=True)


def _asset(symbol: str, balance: str = '0', margin: str = '0', locked: str = '0') -> dict[str, str]:  # noqa: E501
    return {'symbol': symbol, 'balance': balance, 'locked_balance': locked, 'margin_balance': margin}  # noqa: E501


ASSET_DETAILS = {'code': 200, 'asset_details': [
    {'symbol': 'ETH', 'l1_address': '0x0000000000000000000000000000000000000000', 'l1_decimals': 18, 'index_price': '2000'},  # noqa: E501
    {'symbol': 'USDC', 'l1_address': '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48', 'l1_decimals': 6, 'index_price': '1'},  # noqa: E501
    {'symbol': 'LIT', 'l1_address': LIT_ADDRESS, 'l1_decimals': 18, 'index_price': '3'},
]}
USER = {'code': 200, 'accounts': [
    {'index': 1, 'assets': [_asset('USDC', margin='10')], 'positions': [{'position': '1', 'unrealized_pnl': '-2.5'}], 'shares': []},  # noqa: E501
    {'index': 2, 'assets': [_asset('USDC', margin='0.5')], 'positions': [], 'shares': [
        {'public_pool_index': LLP, 'shares_amount': 100},
        {'public_pool_index': LIT_STAKING, 'shares_amount': 50},
    ]},
]}
POOLS = {
    # a USD vault with open perps: USDC margin 900 + uPnL 100 + 0.05 ETH at 2000 = 1100
    LLP: {'code': 200, 'accounts': [{'pool_info': {'total_shares': 1000}, 'positions': [
        {'position': '-3', 'unrealized_pnl': '100'}, {'position': '0', 'unrealized_pnl': '0'},
    ], 'assets': [_asset('USDC', balance='400', margin='900'), _asset('ETH', margin='0.05')]}]},
    # a token pool without positions: 200 LIT held as spot
    LIT_STAKING: {'code': 200, 'accounts': [{'pool_info': {'total_shares': 100}, 'positions': [], 'assets': [_asset('LIT', balance='150', locked='50')]}]},  # noqa: E501
}


def _get(path: str, params: dict[str, Any]) -> dict[str, Any] | None:
    if path == 'assetDetails':
        return ASSET_DETAILS
    if params['by'] == 'l1_address':
        return USER if params['value'] == ADDRESS else None
    return POOLS[params['value']]


def test_lighter_balances_include_sub_accounts_and_pool_shares(database: DBHandler) -> None:
    api = LighterAPI(database=database)
    with patch.object(api, '_get', side_effect=_get):
        balances = api.query_balances(ADDRESS)

    # 10 - 2.5 collateral + 0.5 sub-account + 100/1000 of the 1100 LLP
    assert balances[A_USDC] == FVal('118')
    lit = EvmToken(f'eip155:1/erc20:{LIT_ADDRESS}')
    assert balances[lit] == FVal(100)  # 50/100 of the 200 staked LIT
    assert lit.symbol == 'LIT' and lit.decimals == 18
    assert A_ETH not in balances  # the LLP's ETH is valued into its USDC share


def test_lighter_balances_unknown_address_and_failing_pool(database: DBHandler) -> None:
    api = LighterAPI(database=database)
    with patch.object(api, '_get', side_effect=_get):
        assert api.query_balances(string_to_evm_address('0x000000000000000000000000000000000000dEaD')) == {}  # noqa: E501

    def failing_llp(path: str, params: dict[str, Any]) -> dict[str, Any] | None:
        if params.get('value') == LLP:
            raise RemoteError('pool down')
        return _get(path, params)

    api = LighterAPI(database=database)
    with patch.object(api, '_get', side_effect=failing_llp):
        balances = api.query_balances(ADDRESS)
    assert balances[A_USDC] == FVal('8')  # the LLP is skipped, the rest is kept


def test_ethereum_balances_add_lighter_under_its_label(ethereum_manager: EthereumManager) -> None:
    onchain: defaultdict = defaultdict(BalanceSheet)
    onchain[ADDRESS].assets[A_USDC]['address'] = Balance(amount=FVal(5), value=FVal(5))
    with (
        patch('rotkehlchen.chain.evm.manager.EvmManager.query_balances', return_value=onchain),
        patch.object(LighterAPI, 'query_balances', side_effect=lambda address: {A_USDC: FVal(7)} if address == ADDRESS else {}),  # noqa: E501
        patch('rotkehlchen.chain.ethereum.manager.Inquirer.find_price', return_value=FVal(2)),
    ):
        balances = ethereum_manager.query_balances([ADDRESS])

    assert balances[ADDRESS].assets[A_USDC]['address'].amount == FVal(5)
    assert balances[ADDRESS].assets[A_USDC][LIGHTER_BALANCE_LABEL] == Balance(amount=FVal(7), value=FVal(14))  # noqa: E501

    with (
        patch('rotkehlchen.chain.evm.manager.EvmManager.query_balances', return_value=defaultdict(BalanceSheet)),  # noqa: E501
        patch.object(LighterAPI, 'query_balances', side_effect=RemoteError('lighter down')),
    ):
        assert ethereum_manager.query_balances([ADDRESS]) == {}


def test_aggregator_ethereum_balances_include_lighter(blockchain: ChainsAggregator) -> None:
    """The aggregator queries Ethereum through `query_eth_balances`, not the manager's
    `query_balances`, so Lighter must be added on that path too."""
    onchain: defaultdict = defaultdict(BalanceSheet)
    with (
        patch.object(blockchain.ethereum, 'query_evm_chain_balances', return_value=onchain),
        patch.object(blockchain.ethereum, 'query_protocols_with_balance', side_effect=lambda balances, addresses: balances),  # noqa: E501
        patch.object(LighterAPI, 'query_balances', return_value={A_USDC: FVal(3)}),
        patch('rotkehlchen.chain.ethereum.manager.Inquirer.find_price', return_value=FVal(1)),
    ):
        balances = blockchain.query_eth_balances([ADDRESS])

    assert balances[ADDRESS].assets[A_USDC][LIGHTER_BALANCE_LABEL].amount == FVal(3)


def _response(status: int, body: dict[str, Any]) -> requests.Response:
    (response := requests.Response()).status_code = status
    response._content = json.dumps(body).encode()
    return response


def test_lighter_rate_limited_requests_back_off_and_retry(database: DBHandler) -> None:
    session = MagicMock(spec=requests.Session)
    session.get.side_effect = [
        _response(429, {'code': 429}),
        _response(405, {}),
        _response(200, ASSET_DETAILS),
    ]
    api = LighterAPI(database=database, session=session, rate_limiter=TokenBucket(rps=100, capacity=100))  # noqa: E501
    with patch('rotkehlchen.externalapis.lighter.cancellable_sleep') as sleep:
        assert api._get('assetDetails', {}) == ASSET_DETAILS

    assert [call.args[0] for call in sleep.call_args_list] == [2, 60]

    session.get.side_effect = None
    session.get.return_value = _response(429, {'code': 429})
    with (
        patch('rotkehlchen.externalapis.lighter.cancellable_sleep'),
        pytest.raises(RemoteError, match='still rate limited'),
    ):
        api._get('assetDetails', {})
