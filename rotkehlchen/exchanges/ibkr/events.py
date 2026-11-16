"""trodki: Interactive Brokers Flex statement rows as history events.

Event model:
- Long stock/ETF fills, the stock leg of an option exercise/assignment and FX conversions are
  swaps, so trodki's accounting carries their cost basis.
- Options, and stock sold short, are derivatives whose PnL IBKR reports per close
  (`fifoPnlRealized`, net of commission). They are booked like trodki's Hyperliquid perps: a
  MARGIN profit/loss for the realized PnL plus a MARGIN fee for the commission, and an
  informational event for a fill with neither. That keeps a short option from being "sold
  before it was acquired" and an expiry (a zero-proceeds BookTrade) from needing a price.
- Every event keeps the full Flex row in `extra_data`, so IBKR's own realized PnL can be
  summed per account and period (`realized_pnl`).
"""
import json
import logging
from typing import TYPE_CHECKING, Any, Final

from rotkehlchen.api.websockets.typedefs import UserMessageFeature
from rotkehlchen.assets.asset import Asset
from rotkehlchen.constants import ZERO
from rotkehlchen.exchanges.ibkr.assets import get_or_create_contract_asset
from rotkehlchen.fval import FVal
from rotkehlchen.history.events.structures.asset_movement import create_asset_movement_with_fee
from rotkehlchen.history.events.structures.base import HistoryEvent
from rotkehlchen.history.events.structures.swap import create_swap_events
from rotkehlchen.history.events.structures.types import HistoryEventSubType, HistoryEventType
from rotkehlchen.history.events.utils import create_group_identifier_from_unique_id
from rotkehlchen.locations.constants import LOCATION_IBKR
from rotkehlchen.logging import RotkehlchenLogsAdapter
from rotkehlchen.types import AssetAmount, TimestampMS
from rotkehlchen.user_messages import Unsupported

if TYPE_CHECKING:
    from rotkehlchen.db.dbhandler import DBHandler
    from rotkehlchen.exchanges.ibkr.flex_parser import (
        FlexCash,
        FlexCorporateAction,
        FlexStatement,
        FlexTrade,
    )
    from rotkehlchen.history.events.structures.base import HistoryBaseEntry
    from rotkehlchen.user_messages import MessagesAggregator

logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)

SWAP_ASSET_CLASSES: Final = ('STK', 'ETF')
SPLIT_TYPES: Final = ('FS', 'RS')  # forward and reverse split
DEPOSIT_WITHDRAWAL_TYPE: Final = 'Deposits/Withdrawals'
INTEREST_TYPES: Final = ('Broker Interest Received', 'Broker Interest Paid', 'Bond Interest Received', 'Bond Interest Paid')  # noqa: E501


def _contract(database: DBHandler, trade: FlexTrade) -> Asset:
    return get_or_create_contract_asset(
        database,
        conid=trade.conid,
        description=trade.description,
        asset_class=trade.asset_class,
        underlying=trade.underlying,
        put_or_call=trade.put_or_call,
        strike=trade.strike,
        expiry=trade.expiry,
        multiplier=trade.multiplier,
    )


def _extra(raw: dict[str, str], **kwargs: Any) -> dict[str, Any]:
    return {'ibkr': raw} | kwargs


def _trade_events(
        database: DBHandler,
        account: str,
        trade: FlexTrade,
        label: str,
) -> list[HistoryBaseEntry]:
    group = create_group_identifier_from_unique_id(LOCATION_IBKR, f'ibkr-{account}-{trade.trade_id}')  # noqa: E501
    extra = _extra(trade.raw, fifo_pnl_realized=str(trade.fifo_pnl_realized))
    fee = None if trade.commission == ZERO else AssetAmount(
        asset=Asset(trade.commission_currency),
        amount=abs(trade.commission),
    )
    is_buy = trade.quantity > ZERO

    if trade.asset_class == 'CASH':  # an FX conversion such as EUR.USD
        base, cash = Asset(trade.symbol.split('.')[0]), AssetAmount(Asset(trade.currency), abs(trade.trade_money))  # noqa: E501
        converted = AssetAmount(base, abs(trade.quantity))
        return list(create_swap_events(
            timestamp=trade.timestamp,
            location=LOCATION_IBKR,
            spend=cash if is_buy else converted,
            receive=converted if is_buy else cash,
            fee=fee,
            group_identifier=group,
            location_label=label,
            extra_data=extra | {'ibkr_fx_conversion': True},  # type: ignore[arg-type]  # extra keys are kept as is
        ))

    opens_or_closes_long = (is_buy and trade.open_close != 'C') or (not is_buy and trade.open_close == 'C')  # noqa: E501
    if trade.asset_class in SWAP_ASSET_CLASSES and opens_or_closes_long and trade.trade_money != ZERO:  # noqa: E501
        shares = AssetAmount(_contract(database, trade), abs(trade.quantity))
        cash = AssetAmount(Asset(trade.currency), abs(trade.trade_money))
        return list(create_swap_events(
            timestamp=trade.timestamp,
            location=LOCATION_IBKR,
            spend=cash if is_buy else shares,
            receive=shares if is_buy else cash,
            fee=fee,
            group_identifier=group,
            location_label=label,
            extra_data=extra,  # type: ignore[arg-type]  # extra keys are kept as is
        ))

    contract = _contract(database, trade)
    side = 'Bought' if is_buy else 'Sold'
    notes = f'{side} {abs(trade.quantity)} {trade.description} on IBKR'
    events: list[HistoryBaseEntry] = []
    if trade.fifo_pnl_realized != ZERO:
        events.append(HistoryEvent(
            group_identifier=group,
            sequence_index=len(events),
            timestamp=trade.timestamp,
            location=LOCATION_IBKR,
            event_type=HistoryEventType.MARGIN,
            event_subtype=HistoryEventSubType.PROFIT if trade.fifo_pnl_realized > ZERO else HistoryEventSubType.LOSS,  # noqa: E501
            asset=Asset(trade.currency),
            amount=abs(trade.fifo_pnl_realized),
            location_label=label,
            notes=f'{notes} - realized PnL',
            extra_data=extra,
        ))
    if fee is not None:
        events.append(HistoryEvent(
            group_identifier=group,
            sequence_index=len(events),
            timestamp=trade.timestamp,
            location=LOCATION_IBKR,
            event_type=HistoryEventType.MARGIN,
            event_subtype=HistoryEventSubType.FEE,
            asset=fee.asset,
            amount=fee.amount,
            location_label=label,
            notes=f'{notes} - commission',
            extra_data=extra,
        ))
    if len(events) == 0:
        events.append(HistoryEvent(
            group_identifier=group,
            sequence_index=0,
            timestamp=trade.timestamp,
            location=LOCATION_IBKR,
            event_type=HistoryEventType.INFORMATIONAL,
            event_subtype=HistoryEventSubType.NONE,
            asset=contract,
            amount=abs(trade.quantity),
            location_label=label,
            notes=notes,
            extra_data=extra,
        ))
    return events


def _cash_events(account: str, cash: FlexCash, label: str) -> list[HistoryBaseEntry]:
    unique_id = f'ibkr-{account}-cash-{cash.transaction_id}'
    group = create_group_identifier_from_unique_id(LOCATION_IBKR, unique_id)
    asset, amount, extra = Asset(cash.currency), abs(cash.amount), _extra(cash.raw)
    if cash.type == DEPOSIT_WITHDRAWAL_TYPE:
        return list(create_asset_movement_with_fee(
            timestamp=cash.timestamp,
            location=LOCATION_IBKR,
            event_subtype=HistoryEventSubType.RECEIVE if cash.amount > ZERO else HistoryEventSubType.SPEND,  # noqa: E501
            asset=asset,
            amount=amount,
            location_label=label,
            unique_id=unique_id,
            group_identifier=group,
            extra_data=extra,  # type: ignore[arg-type]  # extra keys are kept as is
            movement_notes=cash.description,
        ))

    if cash.amount < ZERO:
        event_type, event_subtype = HistoryEventType.SPEND, HistoryEventSubType.FEE
    elif cash.type in INTEREST_TYPES:
        event_type, event_subtype = HistoryEventType.RECEIVE, HistoryEventSubType.INTEREST
    else:  # dividends and other credits
        event_type, event_subtype = HistoryEventType.RECEIVE, HistoryEventSubType.NONE
    return [HistoryEvent(
        group_identifier=group,
        sequence_index=0,
        timestamp=cash.timestamp,
        location=LOCATION_IBKR,
        event_type=event_type,
        event_subtype=event_subtype,
        asset=asset,
        amount=amount,
        location_label=label,
        notes=f'IBKR {cash.type.lower()}: {cash.description}',
        extra_data=extra,
    )]


def _corporate_action_events(
        account: str,
        action: FlexCorporateAction,
        label: str,
        msg_aggregator: MessagesAggregator | None,
) -> list[HistoryBaseEntry]:
    if action.type not in SPLIT_TYPES or action.quantity == ZERO:
        message = f'IBKR corporate action {action.type} ({action.description}) is not supported and was skipped'  # noqa: E501
        log.warning(message)
        if msg_aggregator is not None:
            msg_aggregator.add_warning(
                message,
                classification=Unsupported(feature=UserMessageFeature.EXCHANGE_STRATEGY),
                subject=LOCATION_IBKR,
            )
        return []

    return [HistoryEvent(
        group_identifier=create_group_identifier_from_unique_id(LOCATION_IBKR, f'ibkr-{account}-ca-{action.action_id}'),  # noqa: E501
        sequence_index=0,
        timestamp=action.timestamp,
        location=LOCATION_IBKR,
        event_type=HistoryEventType.ADJUSTMENT,
        event_subtype=HistoryEventSubType.RECEIVE if action.quantity > ZERO else HistoryEventSubType.SPEND,  # noqa: E501
        asset=Asset(f'ibkr-{action.conid}'),
        amount=abs(action.quantity),
        location_label=label,
        notes=f'IBKR {action.description}',
        extra_data=_extra(action.raw),
    )]


def flex_to_events(
        database: DBHandler,
        statement: FlexStatement,
        location_label: str,
        msg_aggregator: MessagesAggregator | None = None,
) -> list[HistoryBaseEntry]:
    """All history events of a Flex statement, with deterministic group identifiers so that
    overlapping statements never store an event twice."""
    account = statement.account_id
    events: list[HistoryBaseEntry] = []
    for trade in statement.trades:
        events.extend(_trade_events(database, account, trade, location_label))
    for cash in statement.cash:
        events.extend(_cash_events(account, cash, location_label))
    for action in statement.corporate_actions:
        events.extend(_corporate_action_events(account, action, location_label, msg_aggregator))
    return events


def realized_pnl(
        database: DBHandler,
        connection_name: str,
        from_ts: int,
        to_ts: int,
) -> dict[str, FVal]:
    """IBKR's own realized PnL (`fifoPnlRealized`) of the connection's fills between the two
    timestamps (seconds), per trade currency. FX conversions are left out."""
    totals: dict[str, FVal] = {}
    seen: set[str] = set()
    with database.conn.read_ctx() as cursor:
        for (raw_extra,) in cursor.execute(
            'SELECT extra_data FROM history_events WHERE location=? AND location_label=? '
            'AND timestamp BETWEEN ? AND ? AND extra_data IS NOT NULL',
            (LOCATION_IBKR, connection_name, TimestampMS(from_ts * 1000), TimestampMS(to_ts * 1000)),  # noqa: E501
        ):
            extra = json.loads(raw_extra)
            row = extra.get('ibkr', {})
            if 'fifo_pnl_realized' not in extra or extra.get('ibkr_fx_conversion') is True or (trade_id := row.get('tradeID')) in seen:  # noqa: E501
                continue
            seen.add(trade_id)
            if (pnl := FVal(extra['fifo_pnl_realized'])) != ZERO:
                totals[row['currency']] = totals.get(row['currency'], ZERO) + pnl
    return totals
