import logging
from typing import TYPE_CHECKING, Final

from rotkehlchen.chain.hyperliquid.manager import HYPERLIQUID_CORE_HISTORY_RANGE_PREFIX
from rotkehlchen.db.constants import HISTORY_MAPPING_KEY_STATE, HistoryMappingState
from rotkehlchen.locations.constants import LOCATION_HYPERLIQUID
from rotkehlchen.logging import RotkehlchenLogsAdapter, enter_exit_debug_log
from rotkehlchen.utils.progress import perform_userdb_migration_steps, progress_step

if TYPE_CHECKING:
    from rotkehlchen.data_migrations.progress import MigrationProgressHandler
    from rotkehlchen.rotkehlchen import Rotkehlchen

logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)

# Notes of the events the previous model wrote for perp fills and funding. Maker rebates use
# the same note for spot and perp fills; the re-pull recreates the spot ones identically.
OLD_PERP_AND_FUNDING_NOTES: Final = (
    'Hyperliquid perp trade - %',
    'Hyperliquid trade fee',
    'Hyperliquid maker rebate',
    'Hyperliquid funding payment',
)


@enter_exit_debug_log()
def data_migration_31(rotki: Rotkehlchen, progress_handler: MigrationProgressHandler) -> None:
    """trodki: re-pull Hyperliquid Core history with perps booked as margin.

    Perp fills used to be stored as spot trades (TRADE spend/receive of the coin) and funding as
    interest. They are now margin events (realized PnL, fee, funding). The new events reuse the
    old group identifiers and sequence indexes, so a re-pull alone would be ignored as
    duplicates: the old events are deleted (customized ones are kept) and the Hyperliquid core
    history query ranges are reset, so the next history sync fetches everything again.
    The migration itself makes no network request.
    """
    @progress_step(description='Removing Hyperliquid perp events stored as spot trades')
    def _delete_old_perp_events(rotki: Rotkehlchen) -> None:
        notes_filter = ' OR '.join('notes LIKE ?' for _ in OLD_PERP_AND_FUNDING_NOTES)
        with rotki.data.db.user_write() as write_cursor:
            write_cursor.execute(
                f'DELETE FROM history_events WHERE location=? AND ({notes_filter}) AND '
                'identifier NOT IN (SELECT parent_identifier FROM history_events_mappings '
                'WHERE name=? AND value=?)',
                (
                    LOCATION_HYPERLIQUID,
                    *OLD_PERP_AND_FUNDING_NOTES,
                    HISTORY_MAPPING_KEY_STATE,
                    HistoryMappingState.CUSTOMIZED.serialize_for_db(),
                ),
            )
            log.debug(f'Deleted {write_cursor.rowcount} old Hyperliquid perp/funding events')

    @progress_step(description='Scheduling a full Hyperliquid core history re-pull')
    def _reset_core_history_ranges(rotki: Rotkehlchen) -> None:
        with rotki.data.db.user_write() as write_cursor:
            write_cursor.execute(
                'DELETE FROM used_query_ranges WHERE name LIKE ?',
                (f'{HYPERLIQUID_CORE_HISTORY_RANGE_PREFIX}_%',),
            )

    perform_userdb_migration_steps(rotki, progress_handler, should_vacuum=False)
