"""trodki: Interactive Brokers balances, liabilities (shorts, margin) and marks."""
from collections import defaultdict
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
import requests

from rotkehlchen.accounting.structures.balance import Balance
from rotkehlchen.assets.asset import Asset
from rotkehlchen.constants.assets import A_USD
from rotkehlchen.db.settings import CachedSettings
from rotkehlchen.errors.misc import RemoteError
from rotkehlchen.exchanges.ibkr.gateway import IbkrLoggedOutError
from rotkehlchen.exchanges.ibkr.types import IbkrPosition
from rotkehlchen.exchanges.liabilities import collect_exchange_liabilities
from rotkehlchen.fval import FVal
from rotkehlchen.globaldb.handler import GlobalDBHandler
from rotkehlchen.locations.constants import LOCATION_IBKR
from rotkehlchen.tests.utils.api import api_url_for, assert_proper_sync_response_with_result
from rotkehlchen.tests.utils.exchanges import create_test_ibkr
from rotkehlchen.types import ApiKey, ApiSecret

if TYPE_CHECKING:
    from rotkehlchen.api.server import APIServer
    from rotkehlchen.db.dbhandler import DBHandler
    from rotkehlchen.exchanges.exchange import ExchangeQueryBalances
    from rotkehlchen.exchanges.ibkr.ibkr import Ibkr
    from rotkehlchen.user_messages import MessagesAggregator

ACCOUNT = 'U0000001'
FX = {'USD': FVal(1), 'GBP': FVal('1.25'), 'CHF': FVal(0)}


def _position(conid: int, position: str, mkt_value: str, asset_class: str = 'OPT', currency: str = 'USD') -> IbkrPosition:  # noqa: E501
    return IbkrPosition(
        conid=conid, contract_desc=f'C{conid}', asset_class=asset_class, position=FVal(position),
        mkt_price=FVal(0), mkt_value=FVal(mkt_value), avg_cost=FVal(0), unrealized_pnl=FVal(0),
        currency=currency, ticker='X', und_conid=None, put_or_call=None, strike=None, expiry=None,
        multiplier=FVal(100 if asset_class == 'OPT' else 1),
    )


def _ibkr(database: DBHandler, msg_aggregator: MessagesAggregator) -> Ibkr:
    ibkr = create_test_ibkr(database, msg_aggregator, ApiKey('token'), ApiSecret(b'1'))
    ibkr.account_id_override = ACCOUNT
    return ibkr


def _fx(from_asset: Asset, to_asset: Asset, **_kwargs: object) -> FVal:
    """Rates into the main currency, whatever it is in the test DB"""
    assert to_asset == CachedSettings().main_currency
    return FX[from_asset.identifier]


def _query(
        ibkr: Ibkr,
        positions: list[IbkrPosition],
        ledger: dict[str, FVal],
        net: str = '0',
) -> ExchangeQueryBalances:
    with (
        patch.object(ibkr.gateway, 'positions', return_value=positions),
        patch.object(ibkr.gateway, 'ledger', return_value=ledger),
        patch.object(ibkr.gateway, 'net_liquidation', return_value=(FVal(net), 'USD')),
        patch('rotkehlchen.exchanges.ibkr.ibkr.Inquirer.find_price', side_effect=_fx),
    ):
        return ibkr.query_balances()


def test_long_short_and_cash(database: DBHandler, function_scope_messages_aggregator: MessagesAggregator) -> None:  # noqa: E501
    ibkr = _ibkr(database, function_scope_messages_aggregator)
    balances, msg = _query(
        ibkr,
        positions=[_position(1, '10', '2000', asset_class='STK'), _position(2, '-2', '-300')],
        ledger={'USD': FVal(5000), 'GBP': FVal(-100)},
    )
    assert msg == '' and balances is not None
    assert balances[Asset('ibkr-1')] == Balance(amount=FVal(10), value=FVal(2000))
    assert balances[A_USD] == Balance(amount=FVal(5000), value=FVal(5000))
    assert Asset('ibkr-2') not in balances
    liabilities = ibkr.last_liabilities()
    assert liabilities[Asset('ibkr-2')] == Balance(amount=FVal(2), value=FVal(300))
    assert liabilities[Asset('GBP')] == Balance(amount=FVal(100), value=FVal(125))
    # the marks are stored as current prices per unit
    assert GlobalDBHandler.get_manual_current_price(Asset('ibkr-2')) == (CachedSettings().main_currency, FVal(150))  # noqa: E501


def test_net_matches_net_liquidation(database: DBHandler, function_scope_messages_aggregator: MessagesAggregator) -> None:  # noqa: E501
    ibkr = _ibkr(database, function_scope_messages_aggregator)
    balances, _ = _query(
        ibkr,
        positions=[_position(1, '10', '2000', asset_class='STK'), _position(2, '-2', '-300')],
        ledger={'USD': FVal(5000), 'GBP': FVal(-100)},
        net='6575',
    )
    assert balances is not None
    net = sum(b.value for b in balances.values()) - sum(b.value for b in ibkr.last_liabilities().values())  # noqa: E501
    assert abs(net - FVal(6575)) < FVal('0.01')


def test_missing_fx_rate_is_an_error(database: DBHandler, function_scope_messages_aggregator: MessagesAggregator) -> None:  # noqa: E501
    balances, msg = _query(
        _ibkr(database, function_scope_messages_aggregator),
        positions=[_position(3, '5', '500', asset_class='STK', currency='CHF')],
        ledger={},
    )
    assert balances is None
    assert 'CHF' in msg


def test_zero_position_rows_skipped(database: DBHandler, function_scope_messages_aggregator: MessagesAggregator) -> None:  # noqa: E501
    ibkr = _ibkr(database, function_scope_messages_aggregator)
    balances, _ = _query(ibkr, positions=[_position(4, '0', '0')], ledger={'USD': FVal(0)})
    assert balances == {}
    assert ibkr.last_liabilities() == {}


def test_logged_out_returns_error(database: DBHandler, function_scope_messages_aggregator: MessagesAggregator) -> None:  # noqa: E501
    ibkr = _ibkr(database, function_scope_messages_aggregator)
    with patch.object(ibkr.gateway, 'positions', side_effect=IbkrLoggedOutError('IBKR gateway https://localhost:5000 is not logged in')):  # noqa: E501
        balances, msg = ibkr.query_balances()
    assert balances is None
    assert 'https://localhost:5000' in msg
    assert ibkr.last_liabilities() == {}


def test_ambiguous_account_without_override(database: DBHandler, function_scope_messages_aggregator: MessagesAggregator) -> None:  # noqa: E501
    ibkr = create_test_ibkr(database, function_scope_messages_aggregator, ApiKey('t'), ApiSecret(b'1'))  # noqa: E501
    with (
        patch.object(ibkr.gateway, 'accounts', return_value=['U0000001', 'U0000002']),
        pytest.raises(RemoteError, match='set the account id'),
    ):
        ibkr.account_id()
    with patch.object(ibkr.gateway, 'accounts', return_value=['U0000001']):
        assert ibkr.account_id() == 'U0000001'


def test_one_gateway_down_other_still_reported(database: DBHandler, function_scope_messages_aggregator: MessagesAggregator) -> None:  # noqa: E501
    up = _ibkr(database, function_scope_messages_aggregator)
    down = _ibkr(database, function_scope_messages_aggregator)
    balances_up, _ = _query(up, positions=[_position(2, '-1', '-50')], ledger={})
    with patch.object(down.gateway, 'positions', side_effect=IbkrLoggedOutError('logged out')):
        balances_down, msg = down.query_balances()
    assert balances_up == {} and balances_down is None and msg
    per_location: defaultdict[str, FVal] = defaultdict(FVal)
    liabilities = collect_exchange_liabilities([up], per_location)
    assert liabilities == {Asset('ibkr-2'): Balance(amount=FVal(1), value=FVal(50))}
    assert per_location['ibkr'] == FVal(50)


def test_aggregation_includes_exchange_liabilities(database: DBHandler, function_scope_messages_aggregator: MessagesAggregator) -> None:  # noqa: E501
    first = _ibkr(database, function_scope_messages_aggregator)
    second = _ibkr(database, function_scope_messages_aggregator)
    _query(first, positions=[_position(2, '-2', '-300')], ledger={})
    _query(second, positions=[_position(2, '-1', '-150')], ledger={})
    per_location: defaultdict[str, FVal] = defaultdict(FVal)
    liabilities = collect_exchange_liabilities([first, second, object()], per_location)
    assert liabilities == {Asset('ibkr-2'): Balance(amount=FVal(3), value=FVal(450))}
    assert per_location['ibkr'] == FVal(450)


@pytest.mark.parametrize('added_exchanges', [(LOCATION_IBKR,)])
@pytest.mark.parametrize('ethereum_accounts', [[]])
@pytest.mark.parametrize('btc_accounts', [[]])
def test_all_balances_include_ibkr_liabilities(rotkehlchen_api_server_with_exchanges: APIServer) -> None:  # noqa: E501
    """The balance snapshot adds what an IBKR connection owes (shorts) to the liabilities."""
    rotki = rotkehlchen_api_server_with_exchanges.rest_api.rotkehlchen
    ibkr = rotki.exchange_manager.connected_exchanges[LOCATION_IBKR][0]
    with (
        patch.object(ibkr, 'query_balances', return_value=({A_USD: Balance(FVal(1000), FVal(1000))}, '')),  # noqa: E501
        patch.object(ibkr, 'last_liabilities', return_value={A_USD: Balance(FVal(300), FVal(300))}),  # noqa: E501
        # the cassettes have no main currency to USD rate for today's snapshot
        patch('rotkehlchen.rotkehlchen.PriceHistorian.query_historical_price', return_value=FVal(1)),  # noqa: E501
    ):
        response = requests.get(
            api_url_for(rotkehlchen_api_server_with_exchanges, 'allbalancesresource'),
            json={'async_query': False, 'ignore_cache': True},
        )
    result = assert_proper_sync_response_with_result(response)
    assert FVal(result['liabilities'][A_USD.identifier]['amount']) == FVal(300)
    assert FVal(result['net_value']) == FVal(700) * FVal(result['assets'][A_USD.identifier]['value']) / FVal(1000)  # noqa: E501


@pytest.mark.parametrize('added_exchanges', [(LOCATION_IBKR,)])
def test_exchange_liabilities_endpoint(rotkehlchen_api_server_with_exchanges: APIServer) -> None:
    """The frontend reads what each exchange owes after refreshing its balances"""
    rotki = rotkehlchen_api_server_with_exchanges.rest_api.rotkehlchen
    ibkr = rotki.exchange_manager.connected_exchanges[LOCATION_IBKR][0]
    with patch.object(ibkr, 'last_liabilities', return_value={A_USD: Balance(FVal(300), FVal(270))}):  # noqa: E501
        result = assert_proper_sync_response_with_result(requests.get(
            api_url_for(rotkehlchen_api_server_with_exchanges, 'exchangeliabilitiesresource'),
        ))
    assert result == {'ibkr': {A_USD.identifier: {'amount': '300', 'value': '270'}}}
