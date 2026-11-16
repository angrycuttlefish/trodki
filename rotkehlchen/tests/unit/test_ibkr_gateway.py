"""trodki: read-only Interactive Brokers Client Portal Gateway client."""
import ast
import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from rotkehlchen.errors.misc import RemoteError
from rotkehlchen.exchanges.ibkr.gateway import IbkrGateway, IbkrRateLimitedError
from rotkehlchen.exchanges.ibkr.types import GatewayStatus
from rotkehlchen.fval import FVal
from rotkehlchen.utils.rate_limiter import TokenBucket

ACCOUNT = 'U0000001'


def _response(status: int, body: Any) -> MagicMock:
    response = MagicMock(spec=requests.Response)
    response.status_code = status
    response.json.return_value = body
    response.text = str(body)
    return response


def _option_row(conid: int, position: float = 10) -> dict[str, Any]:
    return {
        'acctId': ACCOUNT, 'conid': conid, 'contractDesc': 'ARKG 15JAN27 46 C',
        'position': position,
        'mktPrice': 3.1, 'mktValue': 3100.0, 'avgCost': 292.0, 'avgPrice': 2.92,
        'unrealizedPnl': 180.0, 'realizedPnl': 0.0, 'currency': 'USD', 'assetClass': 'OPT',
        'expiry': '20270115', 'putOrCall': 'C', 'strike': '46', 'ticker': 'ARKG',
        'undConid': 214284287, 'multiplier': 100.0,
    }


def _gateway(*responses: MagicMock) -> tuple[IbkrGateway, MagicMock]:
    session = MagicMock(spec=requests.Session)
    session.get.side_effect = list(responses)
    session.post.side_effect = list(responses)
    gateway = IbkrGateway(
        base_url='https://localhost:5000',
        session=session,
        rate_limiter=TokenBucket(rps=1000, capacity=1000),
    )
    return gateway, session


def test_positions_parse_options_and_paging() -> None:
    first_page = [_option_row(1000 + i) for i in range(99)] + [_option_row(9999, position=0)]
    gateway, session = _gateway(
        _response(200, [{'id': ACCOUNT, 'accountId': ACCOUNT}]),
        _response(200, first_page),
        _response(200, [_option_row(762299516)]),
    )
    positions = gateway.positions(ACCOUNT)

    assert len(positions) == 100  # 99 + 1 from the second page, the zero row dropped
    assert all(p.conid != 9999 for p in positions)
    option = positions[-1]
    assert (option.conid, option.put_or_call, option.strike) == (762299516, 'C', FVal(46))
    assert option.expiry == datetime.date(2027, 1, 15)
    assert option.multiplier == FVal(100)
    assert option.serialize()['days_to_expiry'] == (datetime.date(2027, 1, 15) - datetime.datetime.now(tz=datetime.UTC).date()).days  # noqa: E501
    urls = [call.kwargs.get('url', call.args[0] if call.args else None) for call in session.get.call_args_list]  # noqa: E501
    assert urls[0].endswith('/v1/api/portfolio/accounts')
    assert urls[1].endswith(f'/v1/api/portfolio/{ACCOUNT}/positions/0')
    assert urls[2].endswith(f'/v1/api/portfolio/{ACCOUNT}/positions/1')


def test_ledger_multi_currency() -> None:
    gateway, _ = _gateway(_response(200, {
        currency: {'cashbalance': value, 'currency': currency}
        for currency, value in (('USD', 5000), ('GBP', -100), ('EUR', 10), ('CAD', 1), ('CHF', 2), ('BASE', 4900))  # noqa: E501
    }))
    assert gateway.ledger(ACCOUNT) == {
        'USD': FVal(5000), 'GBP': FVal(-100), 'EUR': FVal(10), 'CAD': FVal(1), 'CHF': FVal(2),
    }


def test_net_liquidation() -> None:
    gateway, _ = _gateway(_response(200, {'netliquidation': {'amount': 7012.5, 'currency': 'USD'}}))  # noqa: E501
    assert gateway.net_liquidation(ACCOUNT) == (FVal('7012.5'), 'USD')


def test_status_logged_out_and_unreachable() -> None:
    gateway, _ = _gateway(_response(401, {'error': 'not authenticated'}))
    assert gateway.status() == GatewayStatus.LOGGED_OUT
    gateway, _ = _gateway(_response(200, {'session': 'abc', 'iserver': {'authStatus': {'authenticated': False}}}))  # noqa: E501
    assert gateway.status() == GatewayStatus.OK  # the read-only session is alive
    gateway, session = _gateway()
    session.get.side_effect = session.post.side_effect = requests.ConnectionError('refused')
    assert gateway.status() == GatewayStatus.UNREACHABLE


def test_429_sets_penalty_box() -> None:
    gateway, session = _gateway(
        _response(429, {}),
        _response(200, [{'id': ACCOUNT}]),
    )
    with patch('rotkehlchen.exchanges.ibkr.gateway.time.monotonic', return_value=1000.0):
        with pytest.raises(IbkrRateLimitedError):
            gateway.accounts()
        calls = session.get.call_count
        with pytest.raises(IbkrRateLimitedError):
            gateway.accounts()
        assert session.get.call_count == calls
        assert gateway.status() == GatewayStatus.RATE_LIMITED
    with patch('rotkehlchen.exchanges.ibkr.gateway.time.monotonic', return_value=1901.0):
        assert gateway.accounts() == [ACCOUNT]


def test_failure_raises_remote_error() -> None:
    gateway, _ = _gateway(_response(500, {'error': 'boom'}))
    with pytest.raises(RemoteError):
        gateway.accounts()


def test_no_iserver_urls() -> None:
    gateway, _ = _gateway()
    with pytest.raises(ValueError, match='iserver'):
        gateway._url('/iserver/accounts')
    package = Path(__file__).parents[2] / 'exchanges' / 'ibkr'
    for source in package.glob('*.py'):
        for node in ast.walk(ast.parse(source.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert not node.value.startswith('/iserver'), f'{source.name} builds an /iserver URL'  # noqa: E501


@pytest.mark.parametrize(('base_url', 'verify'), [
    ('https://localhost:5000', False),
    ('https://127.0.0.1:5001', False),
    ('https://gateway.example.com', True),
])
def test_tls_verify_only_off_for_localhost(base_url: str, verify: bool) -> None:
    assert IbkrGateway(base_url=base_url).verify_tls is verify
