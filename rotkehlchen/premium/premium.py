"""Local capability layer for trodki.

Upstream rotki gates features and caps data volumes behind a paid subscription that is
verified against rotki's servers. trodki is local-only: there is no subscription, no
server and no limit. This module keeps the names upstream code imports (so upstream
changes still rebase cleanly) but every check grants access and every limit is
``UNLIMITED``.

``Premium`` is kept as a type only. Upstream threads a ``Premium | None`` through many
constructors; in trodki it is always ``None`` and no code path needs an instance.
"""
from enum import Enum
from typing import Final, TypedDict

ASSET_MOVEMENT_MATCHING_CAPABILITY: Final = 'asset_movement_matching'
GNOSIS_PAY_CAPABILITY: Final = 'gnosispay'
MONERIUM_CAPABILITY: Final = 'monerium'
MCP_CAPABILITY: Final = 'mcp'

# No limits. JS-safe (2**53 - 1) because the value is serialized to the frontend.
UNLIMITED: Final = 2**53 - 1
LOCAL_TIER: Final = 'Local'


class PremiumFeatureCapability(TypedDict):
    enabled: bool
    minimum_tier: str | None


class PremiumCapabilities(TypedDict):
    """Capabilities and limits reported to the frontend (shape kept from upstream)."""
    current_tier: str
    limit_of_devices: int
    pnl_events_limit: int
    max_backup_size_mb: int
    history_events_limit: int
    reports_lookup_limit: int
    eth_staked_limit: int
    eth_staking_view: PremiumFeatureCapability
    graphs_view: PremiumFeatureCapability
    event_analysis_view: PremiumFeatureCapability
    asset_movement_matching: PremiumFeatureCapability
    gnosispay: PremiumFeatureCapability
    monerium: PremiumFeatureCapability
    mcp: PremiumFeatureCapability


class UserLimitType(Enum):
    """The limit kinds upstream enforces by tier. In trodki every one is UNLIMITED."""
    HISTORY_EVENTS = 'history_events_limit'
    PNL_EVENTS = 'pnl_events_limit'
    PNL_REPORTS_LOOKUP = 'reports_lookup_limit'
    ETH_STAKED = 'eth_staked_limit'


class Premium:
    """Placeholder type. trodki never creates one (see module docstring)."""


def get_local_capabilities() -> PremiumCapabilities:
    """Every feature enabled, nothing limited."""
    enabled = PremiumFeatureCapability(enabled=True, minimum_tier=None)
    return PremiumCapabilities(
        current_tier=LOCAL_TIER,
        limit_of_devices=0,
        pnl_events_limit=UNLIMITED,
        max_backup_size_mb=0,
        history_events_limit=UNLIMITED,
        reports_lookup_limit=UNLIMITED,
        eth_staked_limit=UNLIMITED,
        eth_staking_view=enabled,
        graphs_view=enabled,
        event_analysis_view=enabled,
        asset_movement_matching=enabled,
        gnosispay=enabled,
        monerium=enabled,
        mcp=enabled,
    )


def has_premium_check(premium: Premium | None) -> bool:
    """Every feature is always available."""
    return True


def get_user_limit(premium: Premium | None, limit_type: UserLimitType) -> tuple[int, bool]:
    """No caps: (UNLIMITED, True) for every limit type."""
    return UNLIMITED, True


def has_premium_capability(premium: Premium | None, capability_name: str) -> bool:
    """Every capability is enabled locally."""
    return True
