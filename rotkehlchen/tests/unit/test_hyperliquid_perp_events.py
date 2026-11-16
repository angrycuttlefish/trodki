"""trodki: Hyperliquid perps are booked as margin (realized PnL, fees, funding), not trades."""
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from rotkehlchen.assets.asset import Asset
from rotkehlchen.chain.evm.types import string_to_evm_address
from rotkehlchen.chain.hyperliquid.manager import HYPERLIQUID_CORE_HISTORY_RANGE_PREFIX
from rotkehlchen.constants import ZERO
from rotkehlchen.data_migrations.migrations.migration_31 import data_migration_31
from rotkehlchen.db.constants import HISTORY_MAPPING_KEY_STATE, HistoryMappingState
from rotkehlchen.db.history_events import DBHistoryEvents
from rotkehlchen.externalapis.hyperliquid import EntryContext, HyperliquidAPI
from rotkehlchen.fval import FVal
from rotkehlchen.history.events.structures.base import HistoryEvent
from rotkehlchen.history.events.structures.types import HistoryEventSubType, HistoryEventType
from rotkehlchen.locations.constants import LOCATION_HYPERLIQUID
from rotkehlchen.types import TimestampMS

if TYPE_CHECKING:
    from rotkehlchen.db.dbhandler import DBHandler
    from rotkehlchen.history.events.structures.base import HistoryBaseEntry

ADDRESS = string_to_evm_address('0x6575B595806cfF7a6F7F350A66e1D6168826c4C1')


def _fill(coin: str, **overrides: Any) -> dict[str, Any]:
    entry = {
        'coin': coin, 'px': '0.010163', 'sz': '1528940.0', 'side': 'B', 'time': 1700000000000,
        'startPosition': '0.0', 'dir': 'Open Long', 'closedPnl': '0.0', 'hash': '0xabc',
        'oid': 7, 'crossed': True, 'fee': '1.25', 'tid': 11, 'feeToken': 'USDC',
    }
    return entry | overrides


def _events(entry: dict[str, Any]) -> list[HistoryBaseEntry]:
    api = HyperliquidAPI()
    context = EntryContext(
        entry=entry,
        timestamp=TimestampMS(entry['time']),
        unique_id=str(entry['tid']),
        group_identifier=f'g{entry["tid"]}',
    )
    return api._create_fill_events(address=ADDRESS, contexts=[context])


def _kinds(events: list[HistoryBaseEntry]) -> list[tuple[HistoryEventType, HistoryEventSubType, FVal]]:  # noqa: E501
    return [(e.event_type, e.event_subtype, e.amount) for e in events]


@pytest.mark.parametrize('coin', ['kPEPE', 'UNI', 'AAVE', 'xyz:TSLA'])
def test_perp_fill_needs_no_coin_asset(globaldb: Any, coin: str) -> None:  # pylint: disable=unused-argument
    """Perp coins that are not resolvable as assets (UNI, kPEPE, HIP-3) are no longer dropped."""
    events = _events(_fill(coin))
    assert _kinds(events) == [(HistoryEventType.MARGIN, HistoryEventSubType.FEE, FVal('1.25'))]
    extra = events[0].extra_data
    assert extra is not None
    assert extra['market'] == coin
    assert extra['component'] == 'fee'
    assert (extra['side'], extra['direction'], extra['px'], extra['sz']) == ('B', 'Open Long', '0.010163', '1528940.0')  # noqa: E501
    assert (extra['start_position'], extra['oid'], extra['tid'], extra['hash']) == ('0.0', 7, 11, '0xabc')  # noqa: E501


def test_perp_close_books_realized_pnl_and_fee(globaldb: Any) -> None:  # pylint: disable=unused-argument
    profit = _events(_fill('BTC', dir='Close Long', side='A', closedPnl='42.5', fee='0.5'))
    assert _kinds(profit) == [
        (HistoryEventType.MARGIN, HistoryEventSubType.PROFIT, FVal('42.5')),
        (HistoryEventType.MARGIN, HistoryEventSubType.FEE, FVal('0.5')),
    ]
    assert [e.sequence_index for e in profit] == [0, 1]
    loss = _events(_fill('ETH', dir='Close Short', closedPnl='-10', fee='0.2', tid=12))
    assert _kinds(loss)[0] == (HistoryEventType.MARGIN, HistoryEventSubType.LOSS, FVal('10'))


def test_perp_maker_rebate_and_empty_fill(globaldb: Any) -> None:  # pylint: disable=unused-argument
    rebate = _events(_fill('BTC', fee='-0.3'))
    assert _kinds(rebate) == [(HistoryEventType.RECEIVE, HistoryEventSubType.CASHBACK, FVal('0.3'))]  # noqa: E501
    # neither PnL nor fee: kept as a zero informational event so the fill stays on record
    empty = _events(_fill('BTC', fee='0', tid=13))
    assert _kinds(empty) == [(HistoryEventType.INFORMATIONAL, HistoryEventSubType.NONE, ZERO)]
    assert empty[0].extra_data is not None and empty[0].extra_data['component'] == 'fill'


def test_perp_liquidation_names_the_liquidated_user(globaldb: Any) -> None:  # pylint: disable=unused-argument
    events = _events(_fill('BTC', closedPnl='-100', liquidation={'liquidatedUser': ADDRESS, 'markPx': '1', 'method': 'market'}))  # noqa: E501
    extra = events[0].extra_data
    assert extra is not None
    assert extra['liquidation'] is True
    assert extra['liquidated_user'] == ADDRESS


def test_spot_fill_is_still_a_swap(globaldb: Any) -> None:  # pylint: disable=unused-argument
    with (
        patch.object(HyperliquidAPI, '_resolve_fill_coin', return_value='HYPE'),
        patch('rotkehlchen.externalapis.hyperliquid.asset_from_hyperliquid', return_value=Asset('ETH')),  # noqa: E501
    ):
        events = _events(_fill('@107', px='20', sz='2', dir='Buy'))
    assert [e.event_type for e in events][:2] == [HistoryEventType.TRADE, HistoryEventType.TRADE]


def test_funding_is_margin_pnl(globaldb: Any) -> None:  # pylint: disable=unused-argument
    api = HyperliquidAPI()
    contexts = [EntryContext(
        entry={'time': 1700000000000, 'hash': '0x0', 'delta': {'type': 'funding', 'coin': coin, 'usdc': usdc, 'szi': '1', 'fundingRate': '0.0001'}},  # noqa: E501
        timestamp=TimestampMS(1700000000000),
        unique_id=f'f{coin}',
        group_identifier=f'gf{coin}',
    ) for coin, usdc in (('BTC', '1.5'), ('kPEPE', '-0.7'))]
    events = api._create_funding_events(address=ADDRESS, contexts=contexts)
    assert _kinds(events) == [
        (HistoryEventType.MARGIN, HistoryEventSubType.PROFIT, FVal('1.5')),
        (HistoryEventType.MARGIN, HistoryEventSubType.LOSS, FVal('0.7')),
    ]
    assert events[1].extra_data == {'component': 'funding', 'coin': 'kPEPE', 'szi': '1', 'funding_rate': '0.0001'}  # noqa: E501


def test_migration_31_drops_old_perp_events_and_resets_ranges(database: DBHandler) -> None:
    def old_event(group: str, seq: int, notes: str) -> HistoryEvent:
        return HistoryEvent(
            group_identifier=group, sequence_index=seq, timestamp=TimestampMS(1700000000000),
            location=LOCATION_HYPERLIQUID, event_type=HistoryEventType.TRADE,
            event_subtype=HistoryEventSubType.SPEND, asset=Asset('ETH'), amount=FVal(1),
            notes=notes, location_label=ADDRESS,
        )

    db_events = DBHistoryEvents(database)
    with database.user_write() as write_cursor:
        db_events.add_history_events(write_cursor, [
            old_event('perp', 0, 'Hyperliquid perp trade - Open Long'),
            old_event('perp', 2, 'Hyperliquid trade fee'),
            old_event('perp', 3, 'Hyperliquid maker rebate'),
            old_event('funding', 0, 'Hyperliquid funding payment'),
            old_event('customized', 0, 'Hyperliquid perp trade - Close Long'),
            old_event('spot', 0, 'Swap 1 USDC in Hyperliquid'),
        ])
        customized_id = write_cursor.execute(
            'SELECT identifier FROM history_events WHERE group_identifier=?', ('customized',),
        ).fetchone()[0]
        write_cursor.execute(
            'INSERT INTO history_events_mappings(parent_identifier, name, value) VALUES(?, ?, ?)',
            (customized_id, HISTORY_MAPPING_KEY_STATE, HistoryMappingState.CUSTOMIZED.serialize_for_db()),  # noqa: E501
        )
        write_cursor.execute(
            'INSERT INTO used_query_ranges(name, start_ts, end_ts) VALUES(?, 0, 1700000000)',
            (f'{HYPERLIQUID_CORE_HISTORY_RANGE_PREFIX}_{ADDRESS}',),
        )
        write_cursor.execute(
            "INSERT INTO used_query_ranges(name, start_ts, end_ts) VALUES('other_range', 0, 1)",
        )

    class Progress:  # not a mock: the step runner collects locals that have `_description`
        def __init__(self) -> None:
            self.steps: list[str] = []

        def set_total_steps(self, total: int) -> None:
            assert total == 2

        def new_step(self, description: str) -> None:
            self.steps.append(description)

    progress = Progress()
    rotki = SimpleNamespace(data=SimpleNamespace(db=database))
    data_migration_31(rotki, progress)
    assert len(progress.steps) == 2

    with database.conn.read_ctx() as cursor:
        remaining = {row[0] for row in cursor.execute('SELECT group_identifier FROM history_events')}  # noqa: E501
        ranges = {row[0] for row in cursor.execute('SELECT name FROM used_query_ranges')}
    assert remaining == {'customized', 'spot'}
    assert ranges == {'other_range'}
