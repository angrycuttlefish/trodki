"""trodki: Interactive Brokers contracts as custom assets.

Every contract is a `CustomAsset` whose identifier is derived from IBKR's permanent contract
id (conid), so positions from the gateway and fills from Flex statements of both accounts
resolve to the same asset. The name is only a label: matching never depends on it.
"""
from typing import TYPE_CHECKING, Final

from rsqlite import IntegrityError

from rotkehlchen.assets.asset import CustomAsset
from rotkehlchen.db.custom_assets import DBCustomAssets
from rotkehlchen.errors.misc import InputError
from rotkehlchen.exchanges.ibkr.constants import IBKR_ETF, IBKR_OPTION, IBKR_OTHER, IBKR_STOCK
from rotkehlchen.globaldb.handler import GlobalDBHandler

if TYPE_CHECKING:
    import datetime

    from rotkehlchen.db.dbhandler import DBHandler
    from rotkehlchen.fval import FVal

CONTRACT_ASSET_PREFIX: Final = 'ibkr-'
ASSET_TYPE_BY_CLASS: Final = {'STK': IBKR_STOCK, 'ETF': IBKR_ETF, 'OPT': IBKR_OPTION}


def contract_asset_identifier(conid: int) -> str:
    return f'{CONTRACT_ASSET_PREFIX}{conid}'


def get_or_create_contract_asset(
        database: DBHandler,
        *,
        conid: int,
        description: str,
        asset_class: str,
        underlying: str | None,
        put_or_call: str | None,
        strike: FVal | None,
        expiry: datetime.date | None,
        multiplier: FVal,
) -> CustomAsset:
    """Return the asset of the contract, creating it or refreshing its name and notes.

    `asset_class` is IBKR's class (STK, OPT, ...), or ETF when the source says so.
    """
    identifier = contract_asset_identifier(conid)
    notes = ', '.join(part for part in (
        f'conid {conid}',
        None if underlying is None else f'underlying {underlying}',
        None if strike is None else f'strike {strike}',
        None if expiry is None else f'expiry {expiry.isoformat()}',
        {'C': 'call', 'P': 'put'}.get(put_or_call or ''),
        f'multiplier {multiplier}',
    ) if part is not None)
    asset = CustomAsset.initialize(
        identifier=identifier,
        name=description,
        custom_asset_type=ASSET_TYPE_BY_CLASS.get(asset_class, IBKR_OTHER),
        notes=notes,
    )
    existing = _existing_contract(identifier)
    if existing == (asset.name, asset.custom_asset_type, asset.notes):
        return asset

    db_custom_assets = DBCustomAssets(database)
    try:
        _save(db_custom_assets, asset, exists=existing is not None)
    except IntegrityError:  # another connection created this conid at the same moment
        return asset
    except InputError:

        asset = CustomAsset.initialize(  # another contract already uses this description
            identifier=identifier,
            name=f'{description} (conid {conid})',
            custom_asset_type=asset.custom_asset_type,
            notes=notes,
        )
        _save(db_custom_assets, asset, exists=_existing_contract(identifier) is not None)

    return asset


def _existing_contract(identifier: str) -> tuple[str, str, str | None] | None:
    """Name, type and notes of the contract's asset, if it exists"""
    with GlobalDBHandler().conn.read_ctx() as cursor:
        return cursor.execute(
            'SELECT B.name, A.type, A.notes FROM custom_assets A JOIN assets B '
            'ON A.identifier = B.identifier WHERE A.identifier=?',
            (identifier,),
        ).fetchone()


def _save(db_custom_assets: DBCustomAssets, asset: CustomAsset, exists: bool) -> None:
    """May raise InputError if the name and type are taken by another asset"""
    if exists:
        db_custom_assets.edit_custom_asset(asset)
    else:
        db_custom_assets.add_custom_asset(asset)
