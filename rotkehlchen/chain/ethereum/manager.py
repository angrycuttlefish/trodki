import logging
from typing import TYPE_CHECKING, Final

from rotkehlchen.accounting.structures.balance import Balance, BalanceSheet
from rotkehlchen.chain.ethereum.transactions import EthereumTransactions
from rotkehlchen.chain.evm.manager import CurveManagerMixin, EvmManager
from rotkehlchen.constants.prices import ZERO_PRICE
from rotkehlchen.db.settings import CachedSettings
from rotkehlchen.errors.misc import RemoteError
from rotkehlchen.externalapis.lighter import LighterAPI
from rotkehlchen.inquirer import Inquirer
from rotkehlchen.logging import RotkehlchenLogsAdapter
from rotkehlchen.utils.network import create_session

from .accountant import EthereumAccountingAggregator
from .decoding.decoder import EthereumTransactionDecoder
from .tokens import EthereumTokens

if TYPE_CHECKING:
    from collections.abc import Sequence

    from rotkehlchen.externalapis.beaconchain.service import BeaconChain
    from rotkehlchen.externalapis.monerium import Monerium
    from rotkehlchen.premium.premium import Premium
    from rotkehlchen.types import ChecksumEvmAddress

    from .node_inquirer import EthereumInquirer


logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)

# Balance label of the Lighter account and pool balances of an Ethereum address (trodki)
LIGHTER_BALANCE_LABEL: Final = 'lighter'


class EthereumManager(EvmManager, CurveManagerMixin):
    def __init__(
            self,
            node_inquirer: EthereumInquirer,
            premium: Premium | None = None,
            monerium: Monerium | None = None,
            beacon_chain: BeaconChain | None = None,
    ) -> None:
        transactions = EthereumTransactions(
            ethereum_inquirer=node_inquirer,
            database=node_inquirer.database,
        )
        super().__init__(
            node_inquirer=node_inquirer,
            transactions=transactions,
            tokens=EthereumTokens(
                database=node_inquirer.database,
                evm_inquirer=node_inquirer,
            ),
            transactions_decoder=EthereumTransactionDecoder(
                database=node_inquirer.database,
                ethereum_inquirer=node_inquirer,
                transactions=transactions,
                premium=premium,
                beacon_chain=beacon_chain,
                monerium=monerium,
            ),
            accounting_aggregator=EthereumAccountingAggregator(
                node_inquirer=node_inquirer,
                msg_aggregator=transactions.msg_aggregator,
            ),
        )
        self.node_inquirer: EthereumInquirer  # just to make the type specific
        self.lighter = LighterAPI(database=node_inquirer.database, session=create_session())

    def query_balances(
            self,
            addresses: Sequence[ChecksumEvmAddress],
    ) -> dict[ChecksumEvmAddress, BalanceSheet]:
        """Query on-chain balances plus each address's Lighter balances."""
        balances = super().query_balances(addresses)
        self.add_lighter_balances(balances=balances, addresses=addresses)
        return balances

    def add_lighter_balances(
            self,
            balances: dict[ChecksumEvmAddress, BalanceSheet],
            addresses: Sequence[ChecksumEvmAddress],
    ) -> None:
        """Add each address's Lighter account and pool balances to `balances`.

        Lighter is a zk rollup on Ethereum whose accounts are keyed by the Ethereum address,
        so they are reported under the address with the `lighter` label. A Lighter failure
        is logged and leaves the other balances unaffected. The chains aggregator queries
        Ethereum through its own `query_eth_balances`, which calls this too.
        """
        main_currency = CachedSettings().main_currency
        for address in addresses:
            try:
                lighter_balances = self.lighter.query_balances(address)
            except Exception as e:
                log.error(f'Failed to query Lighter balances of {address}: {e}')
                continue

            if len(lighter_balances) != 0 and address not in balances:
                balances[address] = BalanceSheet()
            for asset, amount in lighter_balances.items():
                try:
                    price = Inquirer.find_price(from_asset=asset, to_asset=main_currency)
                except RemoteError:
                    price = ZERO_PRICE
                if amount >= 0:
                    balances[address].assets[asset][LIGHTER_BALANCE_LABEL] += Balance(
                        amount=amount,
                        value=amount * price,
                    )
                else:
                    balances[address].liabilities[asset][LIGHTER_BALANCE_LABEL] += Balance(
                        amount=-amount,
                        value=-amount * price,
                    )
