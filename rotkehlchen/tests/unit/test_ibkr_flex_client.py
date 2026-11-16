"""trodki: Interactive Brokers Flex Web Service client and connection validation."""
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
import requests

from rotkehlchen.errors.misc import RemoteError
from rotkehlchen.exchanges.ibkr.flex import FLEX_SEND_REQUEST_URL, FlexWebService
from rotkehlchen.exchanges.ibkr.types import GatewayStatus
from rotkehlchen.tests.utils.exchanges import create_test_ibkr

if TYPE_CHECKING:
    from rotkehlchen.db.dbhandler import DBHandler
    from rotkehlchen.user_messages import MessagesAggregator

pytestmark = pytest.mark.parametrize('ibkr_flex_enabled', [True], indirect=True)
GET_URL = 'https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement'
SEND_OK = f"""<FlexStatementResponse timestamp="16 November, 2026 01:00 PM EST">
<Status>Success</Status><ReferenceCode>4242</ReferenceCode><Url>{GET_URL}</Url>
</FlexStatementResponse>"""
IN_PROGRESS = """<FlexStatementResponse><Status>Warn</Status><ErrorCode>1019</ErrorCode>
<ErrorMessage>Statement generation in progress. Please try again shortly.</ErrorMessage>
</FlexStatementResponse>"""
TOKEN_EXPIRED = """<FlexStatementResponse><Status>Fail</Status><ErrorCode>1012</ErrorCode>
<ErrorMessage>Token has expired.</ErrorMessage></FlexStatementResponse>"""
STATEMENT = '<FlexQueryResponse queryName="trodki" type="AF"><FlexStatements count="1"/></FlexQueryResponse>'  # noqa: E501


def _response(text: str, status: int = 200) -> MagicMock:
    response = MagicMock(spec=requests.Response)
    response.status_code, response.text, response.content = status, text, text.encode()
    return response


def _flex(*texts: str) -> tuple[FlexWebService, MagicMock]:
    session = MagicMock(spec=requests.Session)
    session.get.side_effect = [_response(text) for text in texts]
    return FlexWebService(token='tok', query_id='987', session=session), session


def test_fetch_statement_two_step() -> None:
    flex, session = _flex(SEND_OK, STATEMENT)
    assert flex.fetch_statement() == STATEMENT.encode()
    send, get = session.get.call_args_list
    assert send.kwargs['url'] == FLEX_SEND_REQUEST_URL
    assert send.kwargs['params'] == {'t': 'tok', 'q': '987', 'v': '3'}
    assert get.kwargs['url'] == GET_URL  # the URL IBKR returns, not a hard-coded one
    assert get.kwargs['params'] == {'t': 'tok', 'q': '4242', 'v': '3'}


def test_in_progress_retries_then_succeeds() -> None:
    flex, _ = _flex(SEND_OK, IN_PROGRESS, IN_PROGRESS, STATEMENT)
    with patch('rotkehlchen.exchanges.ibkr.flex.cancellable_sleep') as sleep:
        assert flex.fetch_statement() == STATEMENT.encode()
    assert [call.args[0] for call in sleep.call_args_list] == [5, 10]


def test_in_progress_gives_up_after_backoff() -> None:
    flex, _ = _flex(SEND_OK, IN_PROGRESS, IN_PROGRESS, IN_PROGRESS, IN_PROGRESS)
    with (
        patch('rotkehlchen.exchanges.ibkr.flex.cancellable_sleep'),
        pytest.raises(RemoteError, match='still being generated'),
    ):
        flex.fetch_statement()


def test_error_code_raises_with_message() -> None:
    flex, _ = _flex(TOKEN_EXPIRED)
    with pytest.raises(RemoteError, match=r'1012.*Token has expired'):
        flex.fetch_statement()
    flex, _ = _flex(TOKEN_EXPIRED)
    assert flex.validate() == (False, 'IBKR Flex error 1012: Token has expired.')
    flex, session = _flex()
    session.get.side_effect = requests.ConnectionError('dns')
    ok, msg = flex.validate()
    assert ok is False and 'dns' in msg


def test_validate_ok_with_gateway_logged_out(database: DBHandler, function_scope_messages_aggregator: MessagesAggregator) -> None:  # noqa: E501
    ibkr = create_test_ibkr(database, function_scope_messages_aggregator)
    with (
        patch.object(FlexWebService, 'validate', return_value=(True, '')),
        patch.object(ibkr.gateway, 'status', return_value=GatewayStatus.LOGGED_OUT),
    ):
        ok, msg = ibkr.validate_api_key()
    assert ok is True
    assert 'https://localhost:5000' in msg
    with patch.object(FlexWebService, 'validate', return_value=(False, 'IBKR Flex error 1012: Token has expired.')):  # noqa: E501
        assert ibkr.validate_api_key() == (False, 'IBKR Flex error 1012: Token has expired.')
