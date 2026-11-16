"""trodki: import exported IBKR Flex statements.

Flex Web Service only covers the saved query's period (at most 365 days), so older years are
backfilled by running the same query by hand in Client Portal for each year and importing
the XML. Events have deterministic identifiers, so overlapping statements never double count.
"""
from typing import TYPE_CHECKING

from rotkehlchen.db.history_events import DBHistoryEvents
from rotkehlchen.errors.misc import InputError
from rotkehlchen.exchanges.ibkr.events import flex_to_events
from rotkehlchen.exchanges.ibkr.flex_parser import parse_flex_statement

if TYPE_CHECKING:
    from rotkehlchen.exchanges.ibkr.ibkr import Ibkr


def import_flex_file(ibkr: Ibkr, raw: bytes) -> tuple[int, int]:
    """Store the events of one statement for the connection. Returns (added, skipped).

    May raise:
    - DeserializationError if the file is not a complete Flex statement
    - InputError if the statement belongs to another account than the connection's
    """
    statement = parse_flex_statement(raw)
    expected = ibkr.account_id_override or ibkr.flex_account_id
    if expected is not None and statement.account_id != expected:
        raise InputError(f'Statement is for {statement.account_id}, connection is {expected}')

    ibkr.flex_account_id = statement.account_id
    events = flex_to_events(ibkr.db, statement, ibkr.name, ibkr.msg_aggregator)
    with ibkr.db.user_write() as write_cursor:
        added = DBHistoryEvents(ibkr.db).add_history_events(write_cursor, events)
    return added, len(events) - added
