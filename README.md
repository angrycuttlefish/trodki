# trodki

Local-only portfolio tracking and trading analytics. A fork of
[rotki](https://github.com/rotki/rotki) (AGPL-3.0), adapted so that:

- **Nothing leaves this machine** except the requests needed to fetch your own data
  (venue APIs, block explorers, price sources). No telemetry, no cloud sync, no
  vendor-hosted services.
- **No caps.** History events, PnL events and report lookups are unlimited.
- Features that upstream reserves for paid tiers are re-implemented locally.
- **DuckDB analytics store** (FIFO lots, positions, trading metrics) sits beside the
  encrypted SQLite operational database.
- Extra venues: Ostium, Lighter, Extended, Variational, IBKR, Davy.

trodki is an independent fork. It is not affiliated with or endorsed by the rotki
project. The original README is kept in [UPSTREAM_README.md](UPSTREAM_README.md).

## Licence

AGPL-3.0, same as upstream. See [LICENSE.md](LICENSE.md). Upstream copyright notices
are retained; modifications in this fork are released under the same licence.

## Development

Same toolchain as upstream; see [CLAUDE.md](CLAUDE.md):

    uv sync
    pnpm install --dir frontend
    pnpm dev:web
