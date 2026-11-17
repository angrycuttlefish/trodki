"""trodki: importing exported IBKR Flex statements (backfill of older years)."""
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import requests

from rotkehlchen.errors.misc import InputError
from rotkehlchen.exchanges.ibkr.flex_import import import_flex_file
from rotkehlchen.locations.constants import LOCATION_IBKR
from rotkehlchen.tests.utils.api import (
    api_url_for,
    assert_error_response,
    assert_proper_sync_response_with_result,
)
from rotkehlchen.tests.utils.exchanges import create_test_ibkr

if TYPE_CHECKING:
    from rotkehlchen.api.server import APIServer
    from rotkehlchen.db.dbhandler import DBHandler
    from rotkehlchen.user_messages import MessagesAggregator

FIXTURE = Path(__file__).parents[1] / 'data' / 'ibkr' / 'flex_statement.xml'


def _later_statement() -> bytes:
    """An overlapping statement: the fixture plus one more fill"""
    extra = FIXTURE.read_text(encoding='utf-8').replace('tradeID="1001"', 'tradeID="1999"').split('<Trades>\n')[1].split('\n')[0]  # noqa: E501
    return FIXTURE.read_text(encoding='utf-8').replace('<Trades>\n', f'<Trades>\n{extra}\n', 1).encode()  # noqa: E501


def test_import_overlapping_statements_dedupes(database: DBHandler, function_scope_messages_aggregator: MessagesAggregator) -> None:  # noqa: E501
    ibkr = create_test_ibkr(database, function_scope_messages_aggregator)
    added, skipped = import_flex_file(ibkr, FIXTURE.read_bytes())
    assert added > 0 and skipped == 0
    assert import_flex_file(ibkr, FIXTURE.read_bytes()) == (0, added)
    added_later, skipped_later = import_flex_file(ibkr, _later_statement())
    assert (added_later, skipped_later) == (3, added)  # the new fill's spend, receive and fee
    assert ibkr.flex_account_id == 'U0000001'


def test_import_rejects_other_account(database: DBHandler, function_scope_messages_aggregator: MessagesAggregator) -> None:  # noqa: E501
    ibkr = create_test_ibkr(database, function_scope_messages_aggregator)
    ibkr.account_id_override = 'U0000002'
    with pytest.raises(InputError, match='Statement is for U0000001, connection is U0000002'):
        import_flex_file(ibkr, FIXTURE.read_bytes())


@pytest.mark.parametrize('added_exchanges', [(LOCATION_IBKR,)])
def test_flex_import_endpoint(rotkehlchen_api_server_with_exchanges: APIServer, tmp_path: Path) -> None:  # noqa: E501
    server = rotkehlchen_api_server_with_exchanges
    name = server.rest_api.rotkehlchen.exchange_manager.connected_exchanges[LOCATION_IBKR][0].name
    url = api_url_for(server, 'ibkrfleximportresource')
    with FIXTURE.open('rb') as infile:
        result = assert_proper_sync_response_with_result(requests.post(url, data={'name': name}, files={'file': ('2026.xml', infile)}))  # noqa: E501
    assert result['added'] > 0 and result['skipped'] == 0

    raw = FIXTURE.read_text(encoding='utf-8')
    start, end = raw.index('<CorporateActions>'), raw.index('</CorporateActions>') + len('</CorporateActions>')  # noqa: E501
    (broken := tmp_path / 'broken.xml').write_text(raw[:start] + raw[end:], encoding='utf-8')
    assert_error_response(
        response=requests.put(url, json={'name': name, 'file': str(broken)}),
        contained_in_msg='missing section CorporateActions',
        status_code=HTTPStatus.BAD_REQUEST,
    )
    assert_error_response(
        response=requests.put(url, json={'name': 'nope', 'file': str(broken)}),
        contained_in_msg='No Interactive Brokers connection named nope',
        status_code=HTTPStatus.CONFLICT,
    )
