"""trodki: Interactive Brokers constants."""
from typing import Final

DEFAULT_GATEWAY_URL: Final = 'https://localhost:5000'

# custom_asset_type of the assets created for IBKR contracts
IBKR_STOCK: Final = 'IBKR Stock'
IBKR_ETF: Final = 'IBKR ETF'
IBKR_OPTION: Final = 'IBKR Option'
IBKR_OTHER: Final = 'IBKR Other'
