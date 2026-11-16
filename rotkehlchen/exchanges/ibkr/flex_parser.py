"""trodki: parser for Interactive Brokers Flex (activity) statements in XML.

The user's Flex query must include the sections in `REQUIRED_SECTIONS`. A section the query
leaves out is absent from the XML, which is an error: silently missing cash or corporate
actions would make the history wrong. Only `levelOfDetail="EXECUTION"` trade rows are fills.
Times are US Eastern, in either of IBKR's two formats.
"""
import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal
from xml.etree.ElementTree import ParseError  # noqa: S405  # types only, parsing is defusedxml
from zoneinfo import ZoneInfo

from defusedxml import ElementTree

from rotkehlchen.errors.serialization import DeserializationError
from rotkehlchen.fval import FVal
from rotkehlchen.types import TimestampMS

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element

REQUIRED_SECTIONS: Final = (
    'AccountInformation',
    'Trades',
    'OptionEAE',
    'CashTransactions',
    'CorporateActions',
)
IBKR_TIMEZONE: Final = ZoneInfo('America/New_York')
DATETIME_FORMATS: Final = ('%Y%m%d;%H%M%S', '%Y-%m-%d %H:%M:%S', '%Y%m%d', '%Y-%m-%d')
ETF_SUB_CATEGORY: Final = 'ETF'


@dataclass(frozen=True)
class FlexTrade:
    """One execution. `quantity` is signed (+ buy / - sell) and in contracts for options.
    `trade_money` already includes the multiplier. `commission` is positive for a cost."""
    trade_id: str
    timestamp: TimestampMS
    asset_class: str  # IBKR's assetCategory, or ETF when its subCategory says so
    conid: int
    symbol: str
    description: str
    underlying: str | None
    put_or_call: Literal['C', 'P'] | None
    strike: FVal | None
    expiry: datetime.date | None
    multiplier: FVal
    quantity: FVal
    trade_money: FVal
    commission: FVal
    commission_currency: str
    currency: str
    open_close: Literal['O', 'C'] | None
    notes: tuple[str, ...]
    fifo_pnl_realized: FVal
    raw: dict[str, str]


@dataclass(frozen=True)
class FlexEae:
    """An option exercise, assignment or expiration. Informational: the position change
    itself is also a `BookTrade` row in Trades."""
    conid: int
    timestamp: TimestampMS
    transaction_type: str
    quantity: FVal
    raw: dict[str, str]


@dataclass(frozen=True)
class FlexCash:
    transaction_id: str
    timestamp: TimestampMS
    type: str
    currency: str
    amount: FVal
    description: str
    conid: int | None
    raw: dict[str, str]


@dataclass(frozen=True)
class FlexCorporateAction:
    action_id: str
    timestamp: TimestampMS
    type: str
    conid: int
    asset_class: str
    symbol: str
    description: str
    quantity: FVal
    raw: dict[str, str]


@dataclass(frozen=True)
class FlexStatement:
    account_id: str
    from_date: datetime.date
    to_date: datetime.date
    trades: list[FlexTrade]
    eae: list[FlexEae]
    cash: list[FlexCash]
    corporate_actions: list[FlexCorporateAction]


def parse_ibkr_datetime(value: str) -> TimestampMS:
    """May raise DeserializationError"""
    for fmt in DATETIME_FORMATS:
        try:
            moment = datetime.datetime.strptime(value.strip(), fmt).replace(tzinfo=IBKR_TIMEZONE)
        except ValueError:
            continue
        return TimestampMS(int(moment.timestamp() * 1000))
    raise DeserializationError(f'Unknown IBKR date/time format {value!r}')


def _date(value: str) -> datetime.date:
    """May raise DeserializationError"""
    return datetime.datetime.fromtimestamp(parse_ibkr_datetime(value) / 1000, tz=IBKR_TIMEZONE).date()  # noqa: E501


def _fval(attrs: dict[str, str], key: str, default: str = '0') -> FVal:
    """May raise DeserializationError"""
    try:
        return FVal(attrs.get(key) or default)
    except ValueError as e:
        raise DeserializationError(f'Invalid IBKR number {attrs.get(key)!r} in {key}') from e


def _optional_int(value: str | None) -> int | None:
    return int(value) if value not in (None, '') else None


def _trade(attrs: dict[str, str]) -> FlexTrade:
    """May raise DeserializationError, KeyError, ValueError"""
    asset_class = attrs['assetCategory']
    if asset_class == 'STK' and attrs.get('subCategory') == ETF_SUB_CATEGORY:
        asset_class = 'ETF'
    put_or_call = attrs.get('putCall')
    open_close = attrs.get('openCloseIndicator')
    if not attrs.get('tradeID'):
        raise DeserializationError(f'IBKR trade row without a tradeID: {attrs!r}')
    return FlexTrade(
        trade_id=attrs['tradeID'],
        timestamp=parse_ibkr_datetime(attrs['dateTime']),
        asset_class=asset_class,
        conid=int(attrs['conid']),
        symbol=attrs.get('symbol', ''),
        description=attrs.get('description') or attrs.get('symbol', ''),
        underlying=attrs.get('underlyingSymbol') or None,
        put_or_call=put_or_call if put_or_call in ('C', 'P') else None,  # type: ignore[arg-type]  # checked
        strike=_fval(attrs, 'strike') if attrs.get('strike') else None,
        expiry=_date(attrs['expiry']) if attrs.get('expiry') else None,
        multiplier=_fval(attrs, 'multiplier', default='1'),
        quantity=_fval(attrs, 'quantity'),
        trade_money=_fval(attrs, 'tradeMoney'),
        commission=-_fval(attrs, 'ibCommission'),
        commission_currency=attrs.get('ibCommissionCurrency') or attrs['currency'],
        currency=attrs['currency'],
        open_close=_open_close(open_close),
        notes=tuple(code for code in attrs.get('notes', '').split(';') if code),
        fifo_pnl_realized=_fval(attrs, 'fifoPnlRealized'),
        raw=attrs,
    )


def _open_close(value: str | None) -> Literal['O', 'C'] | None:
    """`C;O` is one fill that closes a position and opens the opposite one. The close comes
    first, so it is read as a close: a long's shares are disposed of."""
    codes = (value or '').split(';')
    if 'C' in codes:
        return 'C'
    return 'O' if 'O' in codes else None


def _required_id(attrs: dict[str, str], key: str) -> str:
    """May raise DeserializationError: an empty id would merge distinct rows when deduplicated"""
    if not (value := attrs.get(key)):
        raise DeserializationError(f'IBKR Flex row without a {key}: {attrs!r}')
    return value


def _is_detail(attrs: dict[str, str]) -> bool:
    """Summary rows of a section repeat the totals of its detail rows"""
    return attrs.get('levelOfDetail', 'DETAIL') != 'SUMMARY'


def _section(statement: Element, name: str) -> Element:
    if (section := statement.find(name)) is None:
        raise DeserializationError(
            f'Flex statement is missing section {name}. Add it to the Flex query in Client Portal',
        )
    return section


def parse_flex_statement(raw: bytes) -> FlexStatement:
    """May raise DeserializationError if the XML is not a single-account Flex statement with
    every required section, or a row can't be read."""
    try:
        root = ElementTree.fromstring(raw)
    except ParseError as e:
        raise DeserializationError(f'IBKR Flex statement is not valid XML: {e!s}') from e

    if root.tag != 'FlexQueryResponse' or (statement := root.find('FlexStatements/FlexStatement')) is None:  # noqa: E501
        raise DeserializationError('The file is not an IBKR Flex statement')

    for name in REQUIRED_SECTIONS:
        _section(statement, name)

    try:
        trades = [
            _trade(dict(element.attrib))
            for element in _section(statement, 'Trades').findall('Trade')
            if element.get('levelOfDetail') == 'EXECUTION'
        ]
        eae = [FlexEae(
            conid=int(attrs['conid']),
            timestamp=parse_ibkr_datetime(attrs['date']),
            transaction_type=attrs['transactionType'],
            quantity=_fval(attrs, 'quantity'),
            raw=attrs,
        ) for attrs in (dict(e.attrib) for e in _section(statement, 'OptionEAE').findall('OptionEAE'))]  # noqa: E501
        cash = [FlexCash(
            transaction_id=_required_id(attrs, 'transactionID'),
            timestamp=parse_ibkr_datetime(attrs['dateTime']),
            type=attrs['type'],
            currency=attrs['currency'],
            amount=_fval(attrs, 'amount'),
            description=attrs.get('description', ''),
            conid=_optional_int(attrs.get('conid')),
            raw=attrs,
        ) for attrs in (dict(e.attrib) for e in _section(statement, 'CashTransactions').findall('CashTransaction')) if _is_detail(attrs)]  # noqa: E501
        corporate_actions = [FlexCorporateAction(
            # actionID is shared by every row of one action (e.g. both legs of a reverse split)
            action_id=_required_id(attrs, 'transactionID'),
            asset_class=attrs.get('assetCategory') or 'STK',
            symbol=attrs.get('symbol', ''),
            timestamp=parse_ibkr_datetime(attrs['dateTime']),
            type=attrs['type'],
            conid=int(attrs['conid']),
            description=attrs.get('description', ''),
            quantity=_fval(attrs, 'quantity'),
            raw=attrs,
        ) for attrs in (dict(e.attrib) for e in _section(statement, 'CorporateActions').findall('CorporateAction')) if _is_detail(attrs)]  # noqa: E501
        return FlexStatement(
            account_id=statement.attrib['accountId'],
            from_date=_date(statement.attrib['fromDate']),
            to_date=_date(statement.attrib['toDate']),
            trades=trades,
            eae=eae,
            cash=cash,
            corporate_actions=corporate_actions,
        )
    except (KeyError, ValueError) as e:
        raise DeserializationError(f'Could not read IBKR Flex statement: missing or invalid {e!s}') from e  # noqa: E501
