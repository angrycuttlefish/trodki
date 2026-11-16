"""trodki: Interactive Brokers Flex statements as history events, and IBKR realized PnL."""
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
import requests

from rotkehlchen.assets.asset import Asset
from rotkehlchen.constants.assets import A_EUR, A_USD
from rotkehlchen.db.history_events import DBHistoryEvents
from rotkehlchen.exchanges.ibkr.events import flex_to_events, realized_pnl
from rotkehlchen.exchanges.ibkr.flex_parser import parse_flex_statement
from rotkehlchen.fval import FVal
from rotkehlchen.history.events.structures.asset_movement import AssetMovement
from rotkehlchen.history.events.structures.swap import SwapEvent
from rotkehlchen.history.events.structures.types import HistoryEventSubType, HistoryEventType
from rotkehlchen.locations.constants import LOCATION_IBKR
from rotkehlchen.tests.utils.api import api_url_for, assert_proper_sync_response_with_result
from rotkehlchen.tests.utils.exchanges import create_test_ibkr

if TYPE_CHECKING:
    from rotkehlchen.api.server import APIServer
    from rotkehlchen.db.dbhandler import DBHandler
    from rotkehlchen.history.events.structures.base import HistoryBaseEntry
    from rotkehlchen.user_messages import MessagesAggregator

FIXTURE = Path(__file__).parents[1] / 'data' / 'ibkr' / 'flex_statement.xml'
LABEL = 'IBKR Personal'


def _events(database: DBHandler) -> list[HistoryBaseEntry]:
    return flex_to_events(database, parse_flex_statement(FIXTURE.read_bytes()), LABEL)


def _of_trade(events: list[HistoryBaseEntry], trade_id: str) -> list[HistoryBaseEntry]:
    """The events of one fill: a swap keeps the Flex row on its first leg only"""
    groups = {e.group_identifier for e in events if (e.extra_data or {}).get('ibkr', {}).get('tradeID') == trade_id}  # noqa: E501
    return sorted((e for e in events if e.group_identifier in groups), key=lambda e: e.sequence_index)  # noqa: E501


def test_every_event_is_attributed(database: DBHandler) -> None:
    events = _events(database)
    assert all(e.location == LOCATION_IBKR and e.location_label == LABEL for e in events)
    assert len({(e.group_identifier, e.sequence_index) for e in events}) == len(events)


def test_stock_buy_is_a_swap(database: DBHandler) -> None:
    spend, receive, fee = _of_trade(_events(database), '1001')
    assert all(isinstance(e, SwapEvent) for e in (spend, receive, fee))
    assert (spend.asset, spend.amount) == (A_USD, FVal(2000))
    assert (receive.asset, receive.amount) == (Asset('ibkr-265598'), FVal(10))
    assert (fee.asset, fee.amount) == (A_USD, FVal(1))


def test_option_round_trip_pnl(database: DBHandler) -> None:
    events = _events(database)
    opening = _of_trade(events, '1003')
    assert [(e.event_type, e.event_subtype) for e in opening] == [(HistoryEventType.MARGIN, HistoryEventSubType.FEE)]  # noqa: E501
    closing = _of_trade(events, '1004')
    assert [(e.event_type, e.event_subtype, e.amount) for e in closing] == [
        (HistoryEventType.MARGIN, HistoryEventSubType.PROFIT, FVal(187)),
        (HistoryEventType.MARGIN, HistoryEventSubType.FEE, FVal('6.5')),
    ]


def test_short_option_then_cover(database: DBHandler) -> None:
    """A short option is never sold before being acquired: both legs are margin events."""
    events = _events(database)
    for trade_id in ('1005', '1006'):
        assert not any(isinstance(e, SwapEvent) for e in _of_trade(events, trade_id))
    cover = _of_trade(events, '1006')
    assert (cover[0].event_subtype, cover[0].amount) == (HistoryEventSubType.PROFIT, FVal('97.4'))


def test_expiry_and_assignment(database: DBHandler) -> None:
    events = _events(database)
    expiry = _of_trade(events, '1008')
    assert [(e.event_type, e.event_subtype, e.amount) for e in expiry] == [
        (HistoryEventType.MARGIN, HistoryEventSubType.LOSS, FVal('1051.95')),
    ]
    assigned = _of_trade(events, '1010')  # the option leg, no PnL and no fee
    assert [(e.event_type, e.event_subtype) for e in assigned] == [(HistoryEventType.INFORMATIONAL, HistoryEventSubType.NONE)]  # noqa: E501
    spend, receive = _of_trade(events, '1011')  # the stock leg of the assignment
    assert (spend.asset, spend.amount, receive.asset, receive.amount) == (A_USD, FVal(15000), Asset('ibkr-4815747'), FVal(100))  # noqa: E501


def test_fx_conversion_is_a_fiat_swap(database: DBHandler) -> None:
    spend, receive, fee = _of_trade(_events(database), '1012')
    assert (spend.asset, spend.amount, receive.asset, receive.amount) == (A_USD, FVal('1191.6'), A_EUR, FVal(1000))  # noqa: E501
    assert (fee.asset, fee.amount) == (A_USD, FVal(2))
    assert spend.extra_data is not None and spend.extra_data.get('ibkr_fx_conversion') is True


def test_cash_transactions_mapped(database: DBHandler) -> None:
    by_id = {(e.extra_data or {}).get('ibkr', {}).get('transactionID'): e for e in _events(database)}  # noqa: E501
    deposit = by_id['2001']
    assert isinstance(deposit, AssetMovement)
    assert (deposit.event_type, deposit.event_subtype) == (HistoryEventType.EXCHANGE_TRANSFER, HistoryEventSubType.RECEIVE)  # noqa: E501
    assert (deposit.asset, deposit.amount) == (A_USD, FVal(50000))
    assert (by_id['2002'].event_type, by_id['2002'].event_subtype, by_id['2002'].amount) == (HistoryEventType.RECEIVE, HistoryEventSubType.NONE, FVal('2.6'))  # noqa: E501
    assert (by_id['2003'].event_type, by_id['2003'].event_subtype) == (HistoryEventType.RECEIVE, HistoryEventSubType.INTEREST)  # noqa: E501
    assert (by_id['2004'].event_type, by_id['2004'].event_subtype, by_id['2004'].amount) == (HistoryEventType.SPEND, HistoryEventSubType.FEE, FVal('4.5'))  # noqa: E501
    split = by_id['3001']
    assert (split.event_type, split.event_subtype, split.asset, split.amount) == (HistoryEventType.ADJUSTMENT, HistoryEventSubType.RECEIVE, Asset('ibkr-265598'), FVal(10))  # noqa: E501


def test_realized_pnl_and_fx_excluded(database: DBHandler) -> None:
    events = _events(database)
    with database.user_write() as write_cursor:
        DBHistoryEvents(database).add_history_events(write_cursor, events)
    # 187 + 97.4 - 1051.95 from the fixture's closes
    assert realized_pnl(database, LABEL, from_ts=0, to_ts=2**31) == {'USD': FVal('-767.55')}
    assert realized_pnl(database, 'other connection', from_ts=0, to_ts=2**31) == {}


def test_sync_twice_dedupes(database: DBHandler, function_scope_messages_aggregator: MessagesAggregator) -> None:  # noqa: E501
    ibkr = create_test_ibkr(database, function_scope_messages_aggregator)
    ibkr.name = LABEL
    db_events = DBHistoryEvents(database)
    with patch('rotkehlchen.exchanges.ibkr.flex.FlexWebService.fetch_statement', return_value=FIXTURE.read_bytes()):  # noqa: E501
        for _ in range(2):
            events, _end = ibkr.query_online_history_events(start_ts=0, end_ts=2**31)
            with database.user_write() as write_cursor:
                db_events.add_history_events(write_cursor, events)
    assert ibkr.flex_account_id == 'U0000001'
    with database.conn.read_ctx() as cursor:
        stored = cursor.execute('SELECT COUNT(*) FROM history_events WHERE location=?', (LOCATION_IBKR,)).fetchone()[0]  # noqa: E501
    assert stored == len(events)


@pytest.mark.parametrize('added_exchanges', [(LOCATION_IBKR,)])
def test_realized_pnl_endpoint(rotkehlchen_api_server_with_exchanges: APIServer) -> None:
    rotki = rotkehlchen_api_server_with_exchanges.rest_api.rotkehlchen
    ibkr = rotki.exchange_manager.connected_exchanges[LOCATION_IBKR][0]
    with rotki.data.db.user_write() as write_cursor:
        DBHistoryEvents(rotki.data.db).add_history_events(
            write_cursor,
            flex_to_events(rotki.data.db, parse_flex_statement(FIXTURE.read_bytes()), ibkr.name),
        )
    result = assert_proper_sync_response_with_result(requests.get(
        api_url_for(rotkehlchen_api_server_with_exchanges, 'ibkrrealizedpnlresource'),
        params={'from_timestamp': 1769904000, 'to_timestamp': 1775001600},  # Feb and March 2026
    ))
    # 187 + 97.4, without the January expiry
    assert result == {'accounts': {ibkr.name: {'USD': '284.4'}}}
