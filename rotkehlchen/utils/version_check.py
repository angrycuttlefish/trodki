import logging
import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from typing import NamedTuple

from packaging.version import Version

logger = logging.getLogger(__name__)


def get_system_spec() -> dict[str, str]:
    """Collect information about the system and installation."""
    if sys.platform == 'darwin':
        system_info = f'macOS {platform.mac_ver()[0]} {platform.architecture()[0]}'
    else:
        system_info = '{} {} {} {}'.format(
            platform.system(),
            '_'.join(platform.architecture()),
            platform.release(),
            platform.machine(),
        )

    try:
        rotki_version = version('rotkehlchen')
    except (PackageNotFoundError, ValueError) as e:
        logger.error(f'Failed to retrieve rotki version due to {e}. Defaulting to 0.0.0')
        rotki_version = '0.0.0'

    return {
        'rotkehlchen': rotki_version,
        'python_implementation': platform.python_implementation(),
        'python_version': platform.python_version(),
        'system': system_info,
    }


class VersionCheckResult(NamedTuple):
    our_version: Version
    latest_version: Version | None = None
    download_url: str | None = None


def get_current_version() -> VersionCheckResult:
    """Get the current version. trodki does not query any remote for newer releases."""
    return VersionCheckResult(our_version=Version(get_system_spec()['rotkehlchen']))
