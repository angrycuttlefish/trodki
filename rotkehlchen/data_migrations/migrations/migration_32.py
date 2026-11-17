import logging
from typing import TYPE_CHECKING

from rotkehlchen.db.locations import DBLocations
from rotkehlchen.logging import RotkehlchenLogsAdapter, enter_exit_debug_log
from rotkehlchen.utils.progress import perform_userdb_migration_steps, progress_step

if TYPE_CHECKING:
    from rotkehlchen.data_migrations.progress import MigrationProgressHandler
    from rotkehlchen.db.drivers.sqlite import DBCursor
    from rotkehlchen.rotkehlchen import Rotkehlchen

logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)


def insert_ibkr_location(write_cursor: DBCursor) -> None:
    """Add the catalog locations missing from an existing DB, such as `ibkr`. Idempotent."""
    DBLocations.seed_builtin_locations(write_cursor)


@enter_exit_debug_log()
def data_migration_32(rotki: Rotkehlchen, progress_handler: MigrationProgressHandler) -> None:
    """trodki: add the Interactive Brokers location to DBs created before it existed.

    Built-in locations are only seeded on DB creation, and adding an exchange connection
    validates its location against the DB. The migration makes no network request.
    """
    @progress_step(description='Adding the Interactive Brokers location')
    def _add_ibkr_location(rotki: Rotkehlchen) -> None:
        with rotki.data.db.user_write() as write_cursor:
            insert_ibkr_location(write_cursor)

    perform_userdb_migration_steps(rotki, progress_handler, should_vacuum=False)
