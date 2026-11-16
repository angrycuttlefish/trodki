"""trodki: Interactive Brokers Flex statement parser."""
import datetime
from pathlib import Path

import pytest

from rotkehlchen.errors.serialization import DeserializationError
from rotkehlchen.exchanges.ibkr.flex_parser import parse_flex_statement, parse_ibkr_datetime
from rotkehlchen.fval import FVal

FIXTURE = Path(__file__).parents[1] / 'data' / 'ibkr' / 'flex_statement.xml'


def test_parse_all_sections() -> None:
    statement = parse_flex_statement(FIXTURE.read_bytes())
    assert statement.account_id == 'U0000001'
    assert (statement.from_date, statement.to_date) == (datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))  # noqa: E501
    assert len(statement.trades) == 12  # the ORDER-level row is not a fill
    assert len(statement.eae) == 2
    assert len(statement.cash) == 4
    assert len(statement.corporate_actions) == 1

    close = next(t for t in statement.trades if t.trade_id == '1004')
    assert (close.asset_class, close.conid, close.underlying, close.put_or_call) == ('OPT', 762299516, 'ARKG', 'C')  # noqa: E501
    assert (close.quantity, close.trade_money, close.commission) == (FVal(-10), FVal(-3120), FVal('6.5'))  # noqa: E501
    assert (close.open_close, close.fifo_pnl_realized, close.multiplier) == ('C', FVal(187), FVal(100))  # noqa: E501
    assert close.strike == FVal(46) and close.expiry == datetime.date(2027, 1, 15)
    assert close.raw['tradeID'] == '1004'

    expiry = next(t for t in statement.trades if t.trade_id == '1008')
    assert expiry.notes == ('Ep',)
    assert next(t for t in statement.trades if t.trade_id == '1002').asset_class == 'ETF'
    assert next(t for t in statement.trades if t.trade_id == '1001').open_close == 'O'
    assert next(t for t in statement.trades if t.trade_id == '1012').open_close is None


def test_datetime_both_formats_eastern() -> None:
    assert parse_ibkr_datetime('20260126;132548') == 1769451948000  # EST, UTC-5
    assert parse_ibkr_datetime('2026-01-26 13:25:48') == 1769451948000
    assert parse_ibkr_datetime('20260701;100000') == 1782914400000  # EDT, UTC-4
    assert parse_ibkr_datetime('20260215') == parse_ibkr_datetime('20260215;000000')
    with pytest.raises(DeserializationError):
        parse_ibkr_datetime('15/02/2026')


def test_missing_section_named_in_error() -> None:
    raw = FIXTURE.read_text(encoding='utf-8')
    start, end = raw.index('<CorporateActions>'), raw.index('</CorporateActions>') + len('</CorporateActions>')  # noqa: E501
    with pytest.raises(DeserializationError, match='CorporateActions'):
        parse_flex_statement((raw[:start] + raw[end:]).encode())


def test_not_a_flex_statement() -> None:
    with pytest.raises(DeserializationError, match='Flex statement'):
        parse_flex_statement(b'<html>nope</html>')
    with pytest.raises(DeserializationError):
        parse_flex_statement(b'not xml at all')
