"""trodki: IBKR fixes from the whole-branch review."""
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from rotkehlchen.constants import ZERO
from rotkehlchen.db.constants import IBKR_ACCOUNT_ID_KEY, IBKR_GATEWAY_URL_KEY
from rotkehlchen.db.history_events import DBHistoryEvents
from rotkehlchen.errors.misc import InputError, RemoteError
from rotkehlchen.errors.serialization import DeserializationError
from rotkehlchen.exchanges.ibkr.assets import get_or_create_contract_asset
from rotkehlchen.exchanges.ibkr.events import flex_to_events
from rotkehlchen.exchanges.ibkr.flex_parser import parse_flex_statement
from rotkehlchen.exchanges.ibkr.types import GatewayStatus, IbkrPosition
from rotkehlchen.fval import FVal
from rotkehlchen.globaldb.handler import GlobalDBHandler
from rotkehlchen.history.events.structures.swap import SwapEvent
from rotkehlchen.history.events.structures.types import HistoryEventSubType, HistoryEventType
from rotkehlchen.tests.utils.exchanges import create_test_ibkr

if TYPE_CHECKING:
    from rotkehlchen.db.dbhandler import DBHandler
    from rotkehlchen.exchanges.ibkr.ibkr import Ibkr
    from rotkehlchen.user_messages import MessagesAggregator

FIXTURE = Path(__file__).parents[1] / 'data' / 'ibkr' / 'flex_statement.xml'
LABEL = 'IBKR Personal'


def _statement(replace: dict[str, str] | None = None) -> bytes:
    raw = FIXTURE.read_text(encoding='utf-8')
    for old, new in (replace or {}).items():
        assert old in raw, old
        raw = raw.replace(old, new)
    return raw.encode()


def _store(database: DBHandler, raw: bytes) -> int:
    events = flex_to_events(database, parse_flex_statement(raw), LABEL)
    with database.user_write() as write_cursor:
        return DBHistoryEvents(database).add_history_events(write_cursor, events)


SPLIT_ROW = '<CorporateAction accountId="U0000001" currency="USD" assetCategory="STK" symbol="AAPL" conid="265598" description="AAPL SPLIT 2 FOR 1" dateTime="20260601;202500" type="FS" quantity="10" actionID="3001" transactionID="3001" levelOfDetail="DETAIL" />'  # noqa: E501
OLD_LINE_ROW = '<CorporateAction accountId="U0000001" currency="USD" assetCategory="STK" symbol="XYZ" conid="900" description="XYZ 1 FOR 10 REVERSE SPLIT" dateTime="20260701;202500" type="RS" quantity="-100" actionID="4001" transactionID="4101" levelOfDetail="DETAIL" />'  # noqa: E501
NEW_LINE_ROW = '<CorporateAction accountId="U0000001" currency="USD" assetCategory="STK" symbol="XYZ.NEW" conid="901" description="XYZ 1 FOR 10 REVERSE SPLIT" dateTime="20260701;202500" type="RS" quantity="10" actionID="4001" transactionID="4102" levelOfDetail="DETAIL" />'  # noqa: E501
REVERSE_SPLIT = (SPLIT_ROW, OLD_LINE_ROW + NEW_LINE_ROW)


def test_corporate_action_on_unseen_conid_is_stored(database: DBHandler) -> None:
    """A reverse split's new conid never appears in Trades; storing it must not fail"""
    added = _store(database, _statement(dict([REVERSE_SPLIT])))
    with database.conn.read_ctx() as cursor:
        assets = {row[0] for row in cursor.execute(
            "SELECT asset FROM history_events WHERE location='ibkr' AND asset IN ('ibkr-900', 'ibkr-901')",  # noqa: E501
        )}
    assert added > 0
    assert assets == {'ibkr-900', 'ibkr-901'}  # both legs of one action, none dropped


def test_commission_is_not_counted_twice_on_margin_closes(database: DBHandler) -> None:
    """fifoPnlRealized is already net of the open and close commissions"""
    events = flex_to_events(database, parse_flex_statement(FIXTURE.read_bytes()), LABEL)
    option_fees = [
        e for e in events
        if e.event_type == HistoryEventType.MARGIN and e.event_subtype == HistoryEventSubType.FEE
    ]
    assert option_fees == []
    closes = [e for e in events if e.event_type == HistoryEventType.MARGIN]
    assert sum(e.amount if e.event_subtype == HistoryEventSubType.PROFIT else -e.amount for e in closes) == FVal('-767.55')  # noqa: E501


def test_close_then_open_sell_disposes_the_long_shares(database: DBHandler) -> None:
    """A sell flagged C;O closes a long position first, so it is a swap, not a margin event"""
    raw = _statement({
        'tradeID="1001" dateTime="20260126;132548" quantity="10"': 'tradeID="1001" dateTime="20260126;132548" quantity="10"',  # noqa: E501
        '</Trades>': '<Trade accountId="U0000001" currency="USD" assetCategory="STK" subCategory="COMMON" symbol="AAPL" description="APPLE INC" conid="265598" multiplier="1" tradeID="1013" dateTime="20260301;100000" quantity="-15" tradePrice="210" tradeMoney="-3150" ibCommission="-1" ibCommissionCurrency="USD" openCloseIndicator="C;O" notes="" fifoPnlRealized="99" buySell="SELL" transactionType="ExchTrade" levelOfDetail="EXECUTION" />\n</Trades>',  # noqa: E501
    })
    statement = parse_flex_statement(raw)
    assert next(t for t in statement.trades if t.trade_id == '1013').open_close == 'C'
    events = [e for e in flex_to_events(database, statement, LABEL) if (e.extra_data or {}).get('ibkr', {}).get('tradeID') == '1013']  # noqa: E501
    assert events and isinstance(events[0], SwapEvent)


def test_empty_ids_are_rejected_and_summaries_skipped() -> None:
    with pytest.raises(DeserializationError, match='tradeID'):
        parse_flex_statement(_statement({'tradeID="1001"': 'tradeID=""'}))
    summary = '<CashTransaction accountId="U0000001" currency="USD" description="TOTAL" dateTime="20260131;000000" amount="99" type="Dividends" transactionID="" levelOfDetail="SUMMARY" />\n</CashTransactions>'  # noqa: E501
    statement = parse_flex_statement(_statement({'</CashTransactions>': summary}))
    assert len(statement.cash) == 4  # the SUMMARY row is not a transaction
    with pytest.raises(DeserializationError, match='transactionID'):
        parse_flex_statement(_statement({'transactionID="2002"': 'transactionID=""'}))


def _ibkr(database: DBHandler, msg_aggregator: MessagesAggregator) -> Ibkr:
    ibkr = create_test_ibkr(database, msg_aggregator)
    ibkr.account_id_override = 'U0000001'
    return ibkr


def _position(conid: int, currency: str = 'USD') -> IbkrPosition:
    return IbkrPosition(
        conid=conid, contract_desc=f'C{conid}', asset_class='STK', position=FVal(2),
        mkt_price=FVal(50), mkt_value=FVal(100), avg_cost=FVal(40), unrealized_pnl=FVal(20),
        currency=currency, ticker='X', und_conid=None, put_or_call=None, strike=None, expiry=None,
        multiplier=FVal(1),
    )


def test_positions_summary_reports_errors_per_connection(database: DBHandler, function_scope_messages_aggregator: MessagesAggregator) -> None:  # noqa: E501
    ibkr = _ibkr(database, function_scope_messages_aggregator)
    with (
        patch.object(ibkr.gateway, 'status', return_value=GatewayStatus.OK),
        patch.object(ibkr.gateway, 'positions', side_effect=RemoteError('session expired')),
    ):
        summary = ibkr.query_positions_summary()
    assert (summary['positions'], summary['error']) == ([], f'{ibkr.name}: session expired')
    assert summary['totals']['market_value'] == '0'

    with (
        patch.object(ibkr.gateway, 'status', return_value=GatewayStatus.OK),
        patch.object(ibkr.gateway, 'positions', return_value=[_position(5, currency='CHF')]),
        patch('rotkehlchen.exchanges.ibkr.ibkr.Inquirer.find_price', return_value=ZERO),
    ):
        summary = ibkr.query_positions_summary()
    assert 'CHF' in summary['error']
    assert summary['positions'] != []  # the positions still show, only the totals are unknown


def test_price_write_collision_does_not_fail_balances(database: DBHandler, function_scope_messages_aggregator: MessagesAggregator) -> None:  # noqa: E501
    ibkr = _ibkr(database, function_scope_messages_aggregator)
    with (
        patch.object(ibkr.gateway, 'positions', return_value=[_position(5)]),
        patch.object(ibkr.gateway, 'ledger', return_value={}),
        patch('rotkehlchen.exchanges.ibkr.ibkr.Inquirer.find_price', return_value=FVal(1)),
        patch('rotkehlchen.exchanges.ibkr.ibkr.GlobalDBHandler.add_manual_latest_price', side_effect=InputError('UNIQUE constraint failed')),  # noqa: E501
    ):
        balances, msg = ibkr.query_balances()
    assert msg == '' and balances is not None and len(balances) == 1


def test_unchanged_mark_is_not_rewritten(database: DBHandler, function_scope_messages_aggregator: MessagesAggregator) -> None:  # noqa: E501
    ibkr = _ibkr(database, function_scope_messages_aggregator)
    with (
        patch.object(ibkr.gateway, 'positions', return_value=[_position(5)]),
        patch.object(ibkr.gateway, 'ledger', return_value={}),
        patch('rotkehlchen.exchanges.ibkr.ibkr.Inquirer.find_price', return_value=FVal(1)),
        patch('rotkehlchen.exchanges.ibkr.ibkr.GlobalDBHandler.add_manual_latest_price', wraps=GlobalDBHandler.add_manual_latest_price) as write,  # noqa: E501
    ):
        ibkr.query_balances()
        ibkr.query_balances()
    assert write.call_count == 1


def test_asset_created_concurrently_is_reused(database: DBHandler) -> None:
    """Two connections can create the same new conid at once: the loser reuses the winner's"""
    created = get_or_create_contract_asset(
        database, conid=77, description='SPY', asset_class='ETF', underlying='SPY',
        put_or_call=None, strike=None, expiry=None, multiplier=FVal(1),
    )
    # a stale read: the asset was created after this connection looked for it
    with patch('rotkehlchen.exchanges.ibkr.assets._existing_contract', return_value=None):
        again = get_or_create_contract_asset(
            database, conid=77, description='SPY', asset_class='ETF', underlying='SPY',
            put_or_call=None, strike=None, expiry=None, multiplier=FVal(1),
        )
    assert again.identifier == created.identifier == 'ibkr-77'


def test_edited_extras_apply_to_the_live_connection(database: DBHandler, function_scope_messages_aggregator: MessagesAggregator) -> None:  # noqa: E501
    ibkr = _ibkr(database, function_scope_messages_aggregator)
    assert ibkr.edit_exchange_extras({IBKR_GATEWAY_URL_KEY: 'https://localhost:5001', IBKR_ACCOUNT_ID_KEY: ''}) == (True, '')  # noqa: E501
    assert (ibkr.gateway_url, ibkr.gateway.base_url, ibkr.account_id_override) == ('https://localhost:5001', 'https://localhost:5001', None)  # noqa: E501
    ibkr.account_id_override = 'U0000009'
    with patch.object(database, 'get_exchange_credentials_extras', return_value={IBKR_GATEWAY_URL_KEY: 'https://localhost:5000'}):  # noqa: E501
        ibkr.reset_to_db_extras()  # nothing stored means no override
    assert (ibkr.gateway_url, ibkr.account_id_override) == ('https://localhost:5000', None)
