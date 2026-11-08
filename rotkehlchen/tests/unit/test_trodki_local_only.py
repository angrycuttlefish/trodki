"""trodki guard: the app must not talk to rotki-hosted services or ship vendor telemetry.

trodki is a local-only fork. The only outbound traffic should be what fetching the user's own
data needs (venue APIs, block explorers, RPC nodes, price oracles). This test fails if a
rotki-hosted endpoint, a premium/sync client or a telemetry sender comes back, for example
through an upstream rebase.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / 'rotkehlchen'
FRONTEND_ROOTS = (
    REPO_ROOT / 'frontend' / 'app' / 'src',
    REPO_ROOT / 'frontend' / 'app' / 'electron',
    REPO_ROOT / 'frontend' / 'app' / 'shared',
)
ROTKI_HOST = re.compile(r'(?:[a-z0-9-]+\.)*rotki\.com')
# Documentation pages only open on a user click and receive no user data.
ALLOWED_HOSTS = frozenset({'docs.rotki.com'})
# Identifiers rather than requests: Gnosis Pay only accepts rotki.com as the sign-in
# message domain, WalletConnect needs metadata, and devtools is dev-only.
ALLOWED_FRONTEND_FILES = frozenset({
    'src/modules/integrations/gnosis-pay/use-gnosis-pay-signing.ts',
    'src/modules/integrations/gnosis-pay/components/GnosisPaySignMessage.vue',
    'src/modules/wallet/use-wallet-connect.ts',
    'src/plugins/devtools.ts',
})
REMOVED_BACKEND_MODULES = (
    'rotkehlchen.premium.sync',
    'rotkehlchen.premium.backup_container',
    'rotkehlchen.sigil',
    'rotkehlchen.usage_analytics',
    'rotkehlchen.indexer_stats',
    'rotkehlchen.mcp.usage_analytics',
    'rotkehlchen.mcp.premium',
    'rotkehlchen.externalapis.github',
)


def _app_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    return [
        path for path in root.rglob('*')
        if path.suffix in suffixes and
        'tests' not in path.relative_to(root).parts and
        'node_modules' not in path.parts and
        not path.name.endswith(('.spec.ts', '.generated.ts', '.generated.js'))
    ]


def _rotki_hosts(text: str) -> set[str]:
    return {match.group(0) for match in ROTKI_HOST.finditer(text)} - ALLOWED_HOSTS


def test_backend_has_no_rotki_hosted_endpoints() -> None:
    offenders = {
        str(path.relative_to(REPO_ROOT)): hosts
        for path in _app_files(BACKEND_ROOT, ('.py',))
        if (hosts := _rotki_hosts(path.read_text(encoding='utf-8')))
    }
    assert offenders == {}, f'rotki-hosted endpoints in backend code: {offenders}'


@pytest.mark.parametrize('root', FRONTEND_ROOTS, ids=lambda p: p.name)
def test_frontend_has_no_rotki_hosted_endpoints(root: Path) -> None:
    if not root.exists():
        pytest.skip(f'{root} not present')
    offenders = {}
    for path in _app_files(root, ('.ts', '.vue', '.js')):
        relative = str(path.relative_to(REPO_ROOT / 'frontend' / 'app'))
        if relative in ALLOWED_FRONTEND_FILES:
            continue
        if hosts := _rotki_hosts(path.read_text(encoding='utf-8')):
            offenders[relative] = hosts
    assert offenders == {}, f'rotki-hosted endpoints in frontend code: {offenders}'


@pytest.mark.parametrize('module', REMOVED_BACKEND_MODULES)
def test_removed_modules_stay_removed(module: str) -> None:
    path = REPO_ROOT / Path(*module.split('.'))
    assert not path.with_suffix('.py').exists(), f'{module} was removed in trodki'
    imports = [
        str(p.relative_to(REPO_ROOT)) for p in _app_files(BACKEND_ROOT, ('.py',))
        if re.search(rf'\b{re.escape(module)}\b', p.read_text(encoding='utf-8'))
    ]
    assert imports == [], f'{module} is imported by {imports}'
