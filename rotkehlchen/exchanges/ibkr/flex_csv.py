"""trodki: parser for Interactive Brokers Flex (activity) statements exported as CSV.

A CSV statement is its sections one after another, each a header row then data rows; with
"Include header and trailer records" ticked, every row is also prefixed (`HEADER`/`DATA` plus
a section code) and sections are wrapped in BOF/BOS/EOS/EOF records. Section names are not in
the file, so each section is recognised by its columns. CSV column names are the XML attribute
names capitalised (`TradeID` for `tradeID`), with the exceptions in `CSV_TO_XML`, so rows are
renamed and handed to the XML parser's row builders.

Client Portal's own exports often hold only some sections (a trades export has no cash or
corporate actions). Their rows are still correct history, so a CSV statement only needs
Trades; the sections it lacks are listed in `FlexStatement.missing_sections`.
"""
import csv
import io
from typing import TYPE_CHECKING, Final

from rotkehlchen.errors.serialization import DeserializationError
from rotkehlchen.exchanges.ibkr.flex_parser import (
    REQUIRED_SECTIONS,
    FlexStatement,
    cash_row,
    corporate_action_row,
    eae_row,
    flex_date,
    is_detail,
    is_execution,
    parse_flex_statement,
    trade_row,
)

if TYPE_CHECKING:
    from collections.abc import Callable

CSV_TO_XML: Final = {
    'ClientAccountID': 'accountId',
    'AssetClass': 'assetCategory',
    'CurrencyPrimary': 'currency',
    'Notes/Codes': 'notes',
    'IBCommission': 'ibCommission',
    'IBCommissionCurrency': 'ibCommissionCurrency',
}
RECORD_MARKERS: Final = frozenset({'BOF', 'EOF', 'BOA', 'EOA', 'BOS', 'EOS'})
DATE_COLUMNS: Final = ('dateTime', 'date')
UTF8_BOM: Final = b'\xef\xbb\xbf'
HEADER_COLUMNS: Final = frozenset({
    'ClientAccountID', 'AccountAlias', 'Conid', 'Symbol', 'TradeID', 'TransactionID',
    'DateTime', 'Date/Time', 'Date', 'CurrencyPrimary', 'AccountType',
})


def _xml_name(column: str) -> str:
    if (name := CSV_TO_XML.get(column)) is not None:
        return name
    column = column.replace('/', '').replace(' ', '')
    return column[:1].lower() + column[1:]


def _section_of(columns: frozenset[str]) -> str | None:
    """Which Flex section a header row belongs to, or None for one trodki doesn't read
    (e.g. the conversion rates). Checked in this order: option EAE rows carry trade ids and
    cash rows can carry action ids, so the most specific columns come first."""
    if 'buySell' in columns and 'tradeID' in columns:
        return 'Trades'
    if {'date', 'transactionType', 'conid'} <= columns:
        return 'OptionEAE'
    if 'actionDescription' in columns or ('actionID' in columns and 'amount' not in columns):
        return 'CorporateActions'
    if {'transactionID', 'amount', 'type'} <= columns:
        return 'CashTransactions'
    if 'accountType' in columns and 'conid' not in columns:
        return 'AccountInformation'
    return None


def _names_columns(row: list[str]) -> bool:
    """No cell of a header row is empty or a number"""
    for cell in row:
        if cell == '':
            return False
        try:
            float(cell.replace(',', ''))
        except ValueError:
            continue
        return False
    return True


def _is_header(row: list[str], current: list[str] | None) -> bool:
    """A row of column names that either holds a column every Flex section can have, or
    can't be a data row of the current section because its length differs"""
    return _names_columns(row) and (
        not HEADER_COLUMNS.isdisjoint(row) or current is None or len(row) != len(current)
    )


def _sections(text: str) -> dict[str, list[tuple[int, dict[str, str]]]]:
    """Rows of each known section, keyed by XML attribute name, with their line number.
    With header and trailer records, the HEADER/DATA marker and section code become two
    extra leading columns that nothing reads. May raise DeserializationError"""
    sections: dict[str, list[tuple[int, dict[str, str]]]] = {}
    section: str | None = None
    columns: list[str] | None = None
    for line, row in enumerate(csv.reader(io.StringIO(text)), start=1):
        if not any(row) or row[0] in RECORD_MARKERS:
            continue
        if _is_header(row, columns):
            columns = [_xml_name(cell) for cell in row]
            if (section := _section_of(frozenset(columns))) is not None:
                sections.setdefault(section, [])
            continue
        if columns is None:
            raise DeserializationError(f'IBKR Flex CSV line {line} has no header row before it')
        if section is None:
            continue
        if len(row) != len(columns):
            raise DeserializationError(
                f'IBKR Flex CSV line {line} has {len(row)} values for {len(columns)} columns',
            )
        sections[section].append((line, dict(zip(columns, row, strict=True))))
    return sections


def _build[T](
        rows: list[tuple[int, dict[str, str]]],
        builder: Callable[[dict[str, str]], T],
        keep: Callable[[dict[str, str]], bool],
) -> list[T]:
    """May raise DeserializationError naming the line that could not be read"""
    built = []
    for line, attrs in rows:
        if not keep(attrs):
            continue
        try:
            built.append(builder(attrs))
        except (DeserializationError, KeyError, ValueError) as e:
            raise DeserializationError(f'Could not read IBKR Flex CSV line {line}: missing or invalid {e!s}') from e  # noqa: E501
    return built


def parse_flex_csv(raw: bytes) -> FlexStatement:
    """May raise DeserializationError if the file has no Trades section, covers several
    accounts or a row can't be read."""
    try:
        text = raw.removeprefix(UTF8_BOM).decode('utf-8')
    except UnicodeDecodeError as e:
        raise DeserializationError('IBKR Flex CSV is not UTF-8 text') from e
    try:
        sections = _sections(text)
    except csv.Error as e:
        raise DeserializationError(f'IBKR Flex CSV could not be read: {e!s}') from e
    if 'Trades' not in sections:
        raise DeserializationError(
            'The file has no Trades section: it is not an IBKR Flex statement, or its '
            'Trades header row is missing (include the Buy/Sell and TradeID columns)',
        )

    if len(all_rows := [attrs for rows in sections.values() for _, attrs in rows]) == 0:
        raise DeserializationError('The file has no rows to import: IBKR found no activity in its period')  # noqa: E501
    if len(accounts := {account for attrs in all_rows if (account := attrs.get('accountId'))}) > 1:
        raise DeserializationError('The file covers several accounts. Export one file per account')
    if not accounts:
        raise DeserializationError('The file has no ClientAccountID column. Add it to the Flex query')  # noqa: E501

    trades = _build(sections['Trades'], trade_row, is_execution)
    eae = _build(sections.get('OptionEAE', []), eae_row, lambda _: True)
    cash = _build(sections.get('CashTransactions', []), cash_row, is_detail)
    corporate_actions = _build(sections.get('CorporateActions', []), corporate_action_row, is_detail)  # noqa: E501
    if len(dates := sorted(
        flex_date(value) for attrs in all_rows for key in DATE_COLUMNS if (value := attrs.get(key))
    )) == 0:
        raise DeserializationError('The file has no DateTime or Date column. Add it to the Flex query')  # noqa: E501
    return FlexStatement(
        account_id=accounts.pop(),
        from_date=dates[0],
        to_date=dates[-1],
        trades=trades,
        eae=eae,
        cash=cash,
        corporate_actions=corporate_actions,
        missing_sections=tuple(name for name in REQUIRED_SECTIONS if name not in sections and name != 'AccountInformation'),  # noqa: E501
    )


def parse_flex_file(raw: bytes) -> FlexStatement:
    """A Flex statement in either of IBKR's export formats, told apart by its first character.
    May raise DeserializationError"""
    if raw.removeprefix(UTF8_BOM).lstrip()[:1] == b'<':
        return parse_flex_statement(raw.removeprefix(UTF8_BOM).lstrip())
    return parse_flex_csv(raw)
