"""trodki opt-in for public data downloads from rotki's GitHub repositories.

Upstream rotki automatically downloads asset database updates, accounting rules, spam
lists, RPC node lists, contract ABIs and airdrop indexes from its GitHub repos. They
carry no user data, but trodki is local-only, so they only happen when the user
enables the `fetch_remote_data_updates` setting (default off).
"""
from typing import Final

from rotkehlchen.db.settings import CachedSettings

REMOTE_DATA_DISABLED_MSG: Final = (
    "Fetching public data from rotki's GitHub repositories is disabled. "
    'Enable "Fetch public data updates" in Settings > General to use this.'
)


def remote_data_updates_enabled() -> bool:
    """Whether the user opted in to downloading public data from rotki's GitHub repos."""
    return CachedSettings().get_entry('fetch_remote_data_updates') is True
