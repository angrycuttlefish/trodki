"""trodki: Interactive Brokers Flex statements exported as CSV."""
import csv
import dataclasses
import io
from pathlib import Path

import pytest

from rotkehlchen.errors.serialization import DeserializationError
from rotkehlchen.exchanges.ibkr.flex_csv import parse_flex_csv, parse_flex_file
from rotkehlchen.exchanges.ibkr.flex_parser import FlexStatement, parse_flex_statement

DATA = Path(__file__).parents[1] / 'data' / 'ibkr'
CSV_FIXTURE = DATA / 'flex_statement.csv'
XML_FIXTURE = DATA / 'flex_statement.xml'


def _without_raw(statement: FlexStatement) -> dict:
    """The parsed rows, minus `raw`, which keeps each format's own column names"""
    return {
        name: [{k: v for k, v in dataclasses.asdict(row).items() if k != 'raw'} for row in getattr(statement, name)]  # noqa: E501
        for name in ('trades', 'eae', 'cash', 'corporate_actions')
    }


def _rows() -> list[list[str]]:
    return list(csv.reader(io.StringIO(CSV_FIXTURE.read_text(encoding='utf-8'))))


def _to_csv(rows: list[list[str]]) -> bytes:
    out = io.StringIO()
    csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator='\n').writerows(rows)
    return out.getvalue().encode()


def _is_header(row: list[str]) -> bool:
    """In the fixture every data row holds the account id or a date, a header row neither"""
    return not any(cell[:1].isdigit() or cell.startswith('U0') for cell in row)


def _drop_section(columns: set[str]) -> bytes:
    """The fixture without the section whose header holds all of `columns`"""
    kept, skipping = [], False
    for row in _rows():
        if _is_header(row):
            skipping = columns <= set(row)
        if not skipping:
            kept.append(row)
    return _to_csv(kept)


def test_csv_matches_xml() -> None:
    from_csv, from_xml = parse_flex_csv(CSV_FIXTURE.read_bytes()), parse_flex_statement(XML_FIXTURE.read_bytes())  # noqa: E501
    assert from_csv.account_id == 'U0000001'
    assert _without_raw(from_csv) == _without_raw(from_xml)
    assert len(from_csv.trades) == 12  # the ORDER-level row is not a fill
    assert from_csv.missing_sections == ()
    assert from_csv.trades[0].raw['tradeID'] == '1001'  # XML names: extra_data is format-blind


def test_csv_statement_period_spans_its_rows() -> None:
    statement = parse_flex_csv(CSV_FIXTURE.read_bytes())
    assert (statement.from_date.isoformat(), statement.to_date.isoformat()) == ('2026-01-02', '2026-07-01')  # noqa: E501


def test_header_and_trailer_records() -> None:
    """IBKR's "Include header and trailer records" option wraps every section in BOS/EOS
    and prefixes each row with HEADER or DATA and the section code"""
    wrapped, code = [['BOF', 'U0000001', 'trodki', '20260101', '20261231']], 0
    for row in _rows():
        if _is_header(row):
            code += 1
            wrapped += [['EOS', f'S{code - 1}']] if code > 1 else []
            wrapped += [['BOS', f'S{code}', 'Section'], ['HEADER', f'S{code}', *row]]
        else:
            wrapped.append(['DATA', f'S{code}', *row])
    wrapped += [['EOS', f'S{code}'], ['EOF', 'U0000001']]
    assert _without_raw(parse_flex_csv(_to_csv(wrapped))) == _without_raw(parse_flex_csv(CSV_FIXTURE.read_bytes()))  # noqa: E501


def test_trades_only_export_names_missing_sections() -> None:
    """The Client Portal trades export has no cash or corporate actions: its trades are
    still history, and the result says what the file lacked"""
    statement = parse_flex_csv(_drop_section({'Amount', 'TransactionID'}))
    assert statement.cash == [] and len(statement.trades) == 12
    assert statement.missing_sections == ('CashTransactions',)


def test_trades_section_required() -> None:
    with pytest.raises(DeserializationError, match='no Trades section'):
        parse_flex_csv(_drop_section({'Buy/Sell'}))


def test_several_accounts_rejected() -> None:
    rows = _rows()
    rows[3] = ['U0000002', *rows[3][1:]]
    with pytest.raises(DeserializationError, match='several accounts'):
        parse_flex_csv(_to_csv(rows))


def test_row_length_mismatch_rejected() -> None:
    rows = _rows()
    rows[3] = rows[3][:-1]
    with pytest.raises(DeserializationError, match='line 4'):
        parse_flex_csv(_to_csv(rows))


def test_not_a_flex_csv() -> None:
    with pytest.raises(DeserializationError):
        parse_flex_csv(b'name,price\nfoo,1\n')
    with pytest.raises(DeserializationError):
        parse_flex_csv(b'\xff\xfe\x00garbage')


def test_parse_flex_file_detects_the_format() -> None:
    assert parse_flex_file(XML_FIXTURE.read_bytes()).missing_sections == ()
    assert parse_flex_file(b'\xef\xbb\xbf' + CSV_FIXTURE.read_bytes()).account_id == 'U0000001'
    assert parse_flex_file(b'\n  ' + XML_FIXTURE.read_bytes()).account_id == 'U0000001'


def test_header_only_export_says_it_is_empty() -> None:
    """A period without fills exports the Trades header alone"""
    with pytest.raises(DeserializationError, match='no rows to import'):
        parse_flex_csv(_to_csv([next(row for row in _rows() if 'Buy/Sell' in row)]))
