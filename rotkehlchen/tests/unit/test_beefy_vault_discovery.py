"""trodki: every active Beefy vault token of a chain is created before token detection."""
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from rotkehlchen.assets.asset import EvmToken
from rotkehlchen.assets.utils import get_or_create_evm_token
from rotkehlchen.chain.evm.decoding.beefy_finance import utils as beefy_utils
from rotkehlchen.chain.evm.decoding.beefy_finance.constants import CPT_BEEFY_FINANCE
from rotkehlchen.chain.evm.types import string_to_evm_address
from rotkehlchen.constants.assets import A_WETH
from rotkehlchen.errors.asset import UnknownAsset
from rotkehlchen.errors.misc import RemoteError
from rotkehlchen.types import ChainID

if TYPE_CHECKING:
    from rotkehlchen.db.dbhandler import DBHandler

pytestmark = pytest.mark.parametrize('beefy_vault_discovery_enabled', [True], indirect=True)
COW = string_to_evm_address('0xCC83F9d3e2ABa9fcfb048E0FDF46e4724A44acBA')
RCOW = string_to_evm_address('0x7aC789958Ba9a0Cf35F8D6cFeae45190C9dB573d')
MOO = string_to_evm_address('0xb3e09fb538186983661f1c581B3eDc2778d24EF8')
MOO_UNDERLYING = string_to_evm_address('0x754704Bc059F8C67012fEd69BC8A327a5aafb603')
MOO_ETH = string_to_evm_address('0x1111111111111111111111111111111111111111')
EOL = string_to_evm_address('0x2222222222222222222222222222222222222222')
VAULTS = [  # gov listed before the cow vault it wraps, as the API may return them
    {'id': 'slv-gld-rp', 'type': 'gov', 'status': 'active', 'earnContractAddress': RCOW, 'earnedToken': 'rCowUniswapRobinhoodGLD-SLV', 'token': 'GLD-SLV', 'tokenAddress': COW, 'tokenDecimals': 18},  # noqa: E501
    {'id': 'slv-gld', 'type': 'cowcentrated', 'status': 'active', 'earnContractAddress': COW, 'earnedToken': 'cowUniswapRobinhoodGLD-SLV', 'token': 'GLD-SLV', 'tokenAddress': '0x48Abc7052509cAF820C4C22559F08381f9AFD823', 'tokenDecimals': 18},  # noqa: E501
    {'id': 'usdc', 'type': 'standard', 'status': 'active', 'earnContractAddress': MOO, 'earnedToken': 'mooAaveV3USDC', 'token': 'USDC', 'tokenAddress': MOO_UNDERLYING, 'tokenDecimals': 6},  # noqa: E501
    {'id': 'eth', 'type': 'standard', 'status': 'active', 'earnContractAddress': MOO_ETH, 'earnedToken': 'mooETH', 'token': 'ETH'},  # noqa: E501
    {'id': 'old', 'type': 'standard', 'status': 'eol', 'earnContractAddress': EOL, 'earnedToken': 'mooOld', 'token': 'X', 'tokenAddress': MOO_UNDERLYING, 'tokenDecimals': 6},  # noqa: E501
]


@pytest.fixture(autouse=True)
def _reset_refresh_times() -> None:
    beefy_utils._vault_tokens_created_at.clear()


def _inquirer(database: DBHandler) -> Any:
    return SimpleNamespace(chain_id=ChainID.ETHEREUM, database=database, wrapped_native_token=A_WETH.resolve_to_evm_token())  # noqa: E501


def _token(address: str) -> EvmToken:
    return EvmToken(f'eip155:1/erc20:{address}')


def test_active_vault_tokens_are_created_with_protocol_and_underlying(database: DBHandler) -> None:
    with patch.object(beefy_utils, 'request_get', return_value=VAULTS) as api:
        beefy_utils.create_beefy_vault_tokens(_inquirer(database))
        beefy_utils.create_beefy_vault_tokens(_inquirer(database))  # refreshed at most daily

    assert api.call_count == 1
    cow, rcow, moo, moo_eth = _token(COW), _token(RCOW), _token(MOO), _token(MOO_ETH)
    assert (cow.symbol, cow.protocol, cow.underlying_tokens) == ('cowUniswapRobinhoodGLD-SLV', CPT_BEEFY_FINANCE, ())  # noqa: E501
    # the reward pool's underlying is the cow token, whose symbol is kept so it is priced
    assert rcow.protocol == CPT_BEEFY_FINANCE and rcow.underlying_tokens[0].address == COW
    assert _token(COW).symbol == 'cowUniswapRobinhoodGLD-SLV'
    assert (moo.decimals, moo.underlying_tokens[0].address) == (18, MOO_UNDERLYING)
    assert _token(MOO_UNDERLYING).decimals == 6
    assert moo_eth.underlying_tokens[0].address == A_WETH.resolve_to_evm_token().evm_address
    with pytest.raises(UnknownAsset):
        _token(EOL)


def test_existing_vault_token_is_tagged_without_changing_its_metadata(database: DBHandler) -> None:
    get_or_create_evm_token(userdb=database, evm_address=MOO, chain_id=ChainID.ETHEREUM, symbol='mooAaveV3MonadUSDC', name='Moo AaveV3 Monad USDC', decimals=18)  # noqa: E501
    with patch.object(beefy_utils, 'request_get', return_value=VAULTS[2:3]):
        beefy_utils.create_beefy_vault_tokens(_inquirer(database))

    moo = _token(MOO)
    assert (moo.name, moo.symbol, moo.protocol) == ('Moo AaveV3 Monad USDC', 'mooAaveV3MonadUSDC', CPT_BEEFY_FINANCE)  # noqa: E501
    assert moo.underlying_tokens[0].address == MOO_UNDERLYING


def test_api_failure_is_retried_next_time(database: DBHandler) -> None:
    with patch.object(beefy_utils, 'request_get', side_effect=[RemoteError('beefy down'), VAULTS[2:3]]) as api:  # noqa: E501
        beefy_utils.create_beefy_vault_tokens(_inquirer(database))
        with pytest.raises(UnknownAsset):
            _token(MOO)
        beefy_utils.create_beefy_vault_tokens(_inquirer(database))

    assert api.call_count == 2
    assert _token(MOO).protocol == CPT_BEEFY_FINANCE
