"""Sync a Davy positions snapshot (from extract.js) into the running trodki backend.

For every Davy security: a custom asset (type `davy security`, notes `ISIN <isin>`), a manual
latest price, and per account a manual balance labelled `Davy <account> <symbol>` at location
`banks`, tagged `davy`. Each account's cash is `Davy <account> cash` in the account currency
(a liability when negative). Balances of accounts in the snapshot that Davy no longer lists
are deleted; accounts missing from the snapshot are left alone.

Usage: python sync_davy.py SNAPSHOT.json [--dry-run] [--api http://127.0.0.1:4242]
Stdlib only.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from decimal import Decimal

ASSET_TYPE = 'davy security'
TAG = 'davy'
LOCATION = 'banks'
PENCE = {'GBX', 'GBp', 'GBPX'}


class Api:
    def __init__(self, base: str, dry_run: bool) -> None:
        self.base = base.rstrip('/') + '/api/1'
        self.dry_run = dry_run

    def call(self, method: str, path: str, body: dict | None = None, write: bool = False):
        if write and self.dry_run:
            print(f'  [dry-run] {method} {path} {json.dumps(body)[:300]}')
            return None
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            self.base + path, data=data, method=method,
            headers={} if data is None else {'Content-Type': 'application/json'},
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read())['result']
        except urllib.error.HTTPError as e:
            sys.exit(f'{method} {path} failed: HTTP {e.code} {e.read().decode()[:500]}')
        except urllib.error.URLError as e:
            sys.exit(f'trodki backend not reachable at {self.base}: {e.reason}')


def fmt(value: Decimal) -> str:
    return format(value.normalize(), 'f')


def native_price(h: dict, fx: dict[str, float]) -> tuple[str, Decimal]:
    """The security's price in its own currency when it reproduces Davy's EUR value,
    else the EUR price implied by Davy's value (so trodki always matches Davy)."""
    qty, value = Decimal(str(h['quantity'])), Decimal(str(h['value']))
    cur, price = h['price_currency'], Decimal(str(h['price'])) / Decimal(str(h['price_units'] or 1))
    if cur in PENCE:
        cur, price = 'GBP', price / 100
    if cur == 'EUR':
        rate = Decimal(1)
    elif (r := fx.get(f'{cur}/EUR')) is not None:
        rate = Decimal(str(r))
    else:
        rate = None
    if rate is not None and value and abs(qty * price / rate - value) / value < Decimal('0.01'):
        return cur, price
    print(f'  ! {h["symbol"]}: {cur} price does not reproduce Davy value, using EUR value/qty')
    return 'EUR', value / qty


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('snapshot')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--api', default='http://127.0.0.1:4242')
    args = parser.parse_args()
    with open(args.snapshot, encoding='utf-8') as f:
        snap = json.load(f)
    api = Api(args.api, args.dry_run)

    users = api.call('GET', '/users')
    if 'loggedin' not in users.values():
        sys.exit('No trodki user is logged in: log in at http://localhost:8080 first.')

    for acct in snap['accounts']:
        if not acct['holdings_sum_matches']:
            sys.exit(f'Account {acct["account"]}: holdings do not add up to Davy total, aborting.')

    if not any(t['name'].lower() == TAG for t in (api.call('GET', '/tags') or {}).values()):
        api.call('PUT', '/tags', {
            'name': TAG, 'description': 'Davy positions (update-davy-positions skill)',
            'background_color': '7a1f3d', 'foreground_color': 'ffffff',
        }, write=True)

    # custom assets by ISIN
    existing = api.call('POST', '/assets/custom', {
        'custom_asset_type': ASSET_TYPE, 'limit': 10000, 'offset': 0,
    })['entries']
    by_isin = {
        e['notes'].removeprefix('ISIN ').strip(): e['identifier']
        for e in existing if (e.get('notes') or '').startswith('ISIN ')
    }
    prices: dict[str, tuple[str, Decimal]] = {}
    for acct in snap['accounts']:
        for h in acct['holdings']:
            isin = h['isin']
            if isin not in by_isin:
                result = api.call('PUT', '/assets/custom', {
                    'name': f'{h["symbol"]} {h["name"]}',
                    'custom_asset_type': ASSET_TYPE,
                    'notes': f'ISIN {isin}',
                }, write=True)
                by_isin[isin] = result or f'<new {isin}>'
                print(f'  + asset {h["symbol"]} {h["name"]}')
            prices[isin] = native_price(h, acct['fx'])

    for isin, (cur, price) in prices.items():
        api.call('PUT', '/assets/prices/latest', {
            'from_asset': by_isin[isin], 'to_asset': cur, 'price': fmt(price),
        }, write=True)

    # desired manual balances, keyed by label
    desired: dict[str, dict] = {}
    for acct in snap['accounts']:
        n = acct['account']
        qty_by_isin: dict[str, tuple[str, Decimal]] = {}
        for h in acct['holdings']:
            sym, qty = qty_by_isin.get(h['isin'], (h['symbol'], Decimal(0)))
            qty_by_isin[h['isin']] = (sym, qty + Decimal(str(h['quantity'])))
        for isin, (sym, qty) in qty_by_isin.items():
            if qty > 0:
                desired[f'Davy {n} {sym}'] = {
                    'asset': by_isin[isin], 'amount': fmt(qty), 'balance_type': 'asset',
                }
        if (cash := Decimal(str(acct['cash']))) != 0:
            desired[f'Davy {n} cash'] = {
                'asset': acct['currency'], 'amount': fmt(abs(cash)),
                'balance_type': 'asset' if cash > 0 else 'liability',
            }

    current = api.call('GET', '/balances/manual')['balances']
    ours = {b['label']: b for b in current if TAG in (b.get('tags') or [])}
    synced_prefixes = tuple(f'Davy {a["account"]} ' for a in snap['accounts'])

    to_add, to_edit, to_delete = [], [], []
    for label, want in desired.items():
        row = {**want, 'label': label, 'location': LOCATION, 'tags': [TAG]}
        if (have := ours.get(label)) is None:
            to_add.append(row)
        elif (have['asset'], Decimal(have['amount']), have['balance_type'], have['location']) != (
            want['asset'], Decimal(want['amount']), want['balance_type'], LOCATION,
        ):
            to_edit.append({**row, 'identifier': have['identifier']})
    for label, have in ours.items():
        if label not in desired and label.startswith(synced_prefixes):
            to_delete.append(have['identifier'])
            print(f'  - {label} (no longer held)')

    if to_edit:
        api.call('PATCH', '/balances/manual', {'balances': to_edit}, write=True)
    if to_add:
        api.call('PUT', '/balances/manual', {'balances': to_add}, write=True)
    if to_delete:
        api.call('DELETE', '/balances/manual', {'ids': to_delete}, write=True)

    print(f'\nSnapshot {snap["taken_at"]}: added {len(to_add)}, updated {len(to_edit)}, '
          f'removed {len(to_delete)}, unchanged {len(desired) - len(to_add) - len(to_edit)}')
    print(f'{"account":<10}{"positions":>10}{"holdings EUR":>16}{"cash EUR":>12}{"total EUR":>14}')
    for a in snap['accounts']:
        print(f'{a["account"]:<10}{len(a["holdings"]):>10}{a["holdings_value"]:>16,.2f}'
              f'{a["cash"]:>12,.2f}{a["portfolio_value"]:>14,.2f}')


if __name__ == '__main__':
    main()
