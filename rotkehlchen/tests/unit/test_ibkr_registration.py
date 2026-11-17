"""trodki: Interactive Brokers location and connector registration."""
from typing import TYPE_CHECKING

from rotkehlchen.data_migrations.migrations.migration_32 import insert_ibkr_location
from rotkehlchen.db.constants import IBKR_ACCOUNT_ID_KEY, IBKR_GATEWAY_URL_KEY
from rotkehlchen.exchanges.constants import SUPPORTED_EXCHANGES, serialize_exchange_connectors
from rotkehlchen.locations.constants import LOCATION_IBKR
from rotkehlchen.types import ApiKey, ApiSecret

if TYPE_CHECKING:
    from rotkehlchen.db.dbhandler import DBHandler


def test_ibkr_is_supported() -> None:
    assert LOCATION_IBKR in SUPPORTED_EXCHANGES
    connector = next(c for c in serialize_exchange_connectors() if c['connector'] == LOCATION_IBKR)
    assert connector['is_exchange_without_api_secret'] is False
    assert connector['is_exchange_with_passphrase'] is False


def test_migration_32_adds_location_idempotently(database: DBHandler) -> None:
    with database.user_write() as write_cursor:
        write_cursor.execute('DELETE FROM locations WHERE identifier = ?', (LOCATION_IBKR,))
        insert_ibkr_location(write_cursor)
        insert_ibkr_location(write_cursor)

    with database.conn.read_ctx() as cursor:
        rows = cursor.execute(
            'SELECT parent_identifier FROM locations WHERE identifier = ?', (LOCATION_IBKR,),
        ).fetchall()
    assert rows == [('exchanges',)]


def test_ibkr_extras_roundtrip(database: DBHandler) -> None:
    identifier = database.add_exchange(
        name='IBKR Business',
        connector=LOCATION_IBKR,
        api_key=ApiKey('flextoken'),
        api_secret=ApiSecret(b'123456'),
        ibkr_gateway_url='https://localhost:5001',
        ibkr_account_id='U0000002',
    )
    assert database.get_exchange_credentials_extras(identifier) == {
        IBKR_GATEWAY_URL_KEY: 'https://localhost:5001',
        IBKR_ACCOUNT_ID_KEY: 'U0000002',
    }

    with database.user_write() as write_cursor:
        database.edit_exchange(
            write_cursor=write_cursor,
            identifier=identifier,
            new_name=None,
            api_key=None,
            api_secret=None,
            passphrase=None,
            kraken_account_type=None,
            kraken_futures_api_key=None,
            kraken_futures_api_secret=None,
            binance_selected_trade_pairs=None,
            okx_location=None,
            ibkr_account_id='',
        )
    assert database.get_exchange_credentials_extras(identifier) == {
        IBKR_GATEWAY_URL_KEY: 'https://localhost:5001',
    }
