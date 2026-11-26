"""trodki: Interactive Brokers positions endpoint and gateway keep-alive."""
import datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
import requests

from rotkehlchen.db.settings import CachedSettings
from rotkehlchen.exchanges.ibkr.keepalive import TICKLE_INTERVAL_SECONDS, gateways_due_for_tickle
from rotkehlchen.exchanges.ibkr.types import GatewayStatus, IbkrPosition
from rotkehlchen.fval import FVal
from rotkehlchen.locations.constants import LOCATION_IBKR
from rotkehlchen.tests.utils.api import api_url_for, assert_proper_sync_response_with_result
from rotkehlchen.tests.utils.exchanges import create_test_ibkr

if TYPE_CHECKING:
    from rotkehlchen.api.server import APIServer

OPTION = IbkrPosition(
    conid=762299516, contract_desc='ARKG 15JAN27 46 C', asset_class='OPT', position=FVal(-2),
    mkt_price=FVal('1.5'), mkt_value=FVal(-300), avg_cost=FVal(250), unrealized_pnl=FVal(200),
    currency='USD', ticker='ARKG', und_conid=1, put_or_call='C', strike=FVal(46),
    expiry=datetime.date(2027, 1, 15), multiplier=FVal(100),
)


@pytest.mark.parametrize('added_exchanges', [(LOCATION_IBKR,)])
def test_positions_endpoint_shape(rotkehlchen_api_server_with_exchanges: APIServer) -> None:
    rotki = rotkehlchen_api_server_with_exchanges.rest_api.rotkehlchen
    up = rotki.exchange_manager.connected_exchanges[LOCATION_IBKR][0]
    up.account_id_override = 'U0000001'
    down = create_test_ibkr(rotki.data.db, rotki.msg_aggregator)
    down.name, down.gateway_url = 'IBKR Business', 'https://localhost:5001'
    rotki.exchange_manager.connected_exchanges[LOCATION_IBKR].append(down)
    with (
        patch.object(up.gateway, 'status', return_value=GatewayStatus.OK),
        patch.object(up.gateway, 'positions', return_value=[OPTION]),
        patch.object(down.gateway, 'status', return_value=GatewayStatus.LOGGED_OUT),
        patch('rotkehlchen.exchanges.ibkr.ibkr.Inquirer.find_price', return_value=FVal(2)),
    ):
        result = assert_proper_sync_response_with_result(requests.get(
            api_url_for(rotkehlchen_api_server_with_exchanges, 'ibkrpositionsresource'),
        ))

    main = CachedSettings().main_currency.identifier
    assert result['accounts']['IBKR Business'] == {
        'name': 'IBKR Business',
        'account_id': None, 'gateway_url': 'https://localhost:5001', 'status': 'logged_out',
        'error': None,
        'positions': [], 'totals': {'market_value': '0', 'unrealized_pnl': '0', 'currency': main},
    }
    account = result['accounts'][up.name]
    assert (account['account_id'], account['status']) == ('U0000001', 'ok')
    assert account['positions'] == [OPTION.serialize()]
    assert account['totals'] == {'market_value': '-600', 'unrealized_pnl': '400', 'currency': main}


def test_tickle_interval() -> None:
    gateway = MagicMock(name='ibkr')
    last: dict[str, float] = {}
    assert gateways_due_for_tickle([gateway], last, now=1000.0) == [gateway]
    assert gateways_due_for_tickle([gateway], last, now=1000.0 + TICKLE_INTERVAL_SECONDS - 1) == []
    assert gateways_due_for_tickle([gateway], last, now=1000.0 + TICKLE_INTERVAL_SECONDS) == [gateway]  # noqa: E501
