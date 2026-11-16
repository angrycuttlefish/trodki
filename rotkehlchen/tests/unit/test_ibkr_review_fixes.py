"""trodki: IBKR fixes from the whole-branch review."""
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from rotkehlchen.db.history_events import DBHistoryEvents
from rotkehlchen.errors.serialization import DeserializationError
from rotkehlchen.exchanges.ibkr.events import flex_to_events
from rotkehlchen.exchanges.ibkr.flex_parser import parse_flex_statement
from rotkehlchen.fval import FVal
from rotkehlchen.history.events.structures.swap import SwapEvent
from rotkehlchen.history.events.structures.types import HistoryEventSubType, HistoryEventType

if TYPE_CHECKING:
    from rotkehlchen.db.dbhandler import DBHandler

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
