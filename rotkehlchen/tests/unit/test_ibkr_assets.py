"""trodki: Interactive Brokers contracts as conid-keyed custom assets."""
import datetime
from typing import TYPE_CHECKING

from rotkehlchen.exchanges.ibkr.assets import get_or_create_contract_asset
from rotkehlchen.exchanges.ibkr.constants import IBKR_ETF, IBKR_OPTION, IBKR_OTHER, IBKR_STOCK
from rotkehlchen.fval import FVal

if TYPE_CHECKING:
    from rotkehlchen.assets.asset import CustomAsset
    from rotkehlchen.db.dbhandler import DBHandler


def _option(
        database: DBHandler,
        description: str = 'ARKG 15JAN27 46 C',
        conid: int = 762299516,
) -> CustomAsset:
    return get_or_create_contract_asset(
        database,
        conid=conid,
        description=description,
        asset_class='OPT',
        underlying='ARKG',
        put_or_call='C',
        strike=FVal(46),
        expiry=datetime.date(2027, 1, 15),
        multiplier=FVal(100),
    )


def test_contract_asset_deterministic(database: DBHandler) -> None:
    first, second = _option(database), _option(database)
    assert first.identifier == second.identifier == 'ibkr-762299516'
    assert first.custom_asset_type == IBKR_OPTION
    assert first.name == 'ARKG 15JAN27 46 C'
    assert first.notes is not None
    for fragment in ('conid 762299516', 'underlying ARKG', 'strike 46', 'expiry 2027-01-15', 'call', 'multiplier 100'):  # noqa: E501
        assert fragment in first.notes


def test_same_conid_two_accounts_one_asset(database: DBHandler) -> None:
    """Both accounts report the same conid; it must be one asset."""
    assert _option(database).identifier == _option(database).identifier
    from rotkehlchen.globaldb.handler import GlobalDBHandler
    with GlobalDBHandler().conn.read_ctx() as cursor:
        assert cursor.execute(
            'SELECT COUNT(*) FROM custom_assets WHERE identifier=?', ('ibkr-762299516',),
        ).fetchone()[0] == 1


def test_description_change_keeps_identity(database: DBHandler) -> None:
    _option(database)
    renamed = _option(database, description='ARKG JAN2027 46 C')
    assert renamed.identifier == 'ibkr-762299516'
    assert renamed.name == 'ARKG JAN2027 46 C'


def test_name_clash_with_other_conid_gets_conid_suffix(database: DBHandler) -> None:
    _option(database)
    other = _option(database, conid=111)
    assert other.identifier == 'ibkr-111'
    assert other.name == 'ARKG 15JAN27 46 C (conid 111)'


def test_asset_types_by_class(database: DBHandler) -> None:
    def kind(asset_class: str, description: str, conid: int) -> str:
        return get_or_create_contract_asset(
            database, conid=conid, description=description, asset_class=asset_class,
            underlying=None, put_or_call=None, strike=None, expiry=None, multiplier=FVal(1),
        ).custom_asset_type

    assert kind('STK', 'AAPL', 1) == IBKR_STOCK
    assert kind('ETF', 'SPY', 2) == IBKR_ETF
    assert kind('FUT', 'ESZ6', 3) == IBKR_OTHER
