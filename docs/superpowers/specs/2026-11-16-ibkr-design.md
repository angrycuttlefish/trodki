# IBKR (Interactive Brokers) integration — design

Date: 2026-11-16. Status: draft for approval.

## Intent

The user holds two Interactive Brokers accounts, one **personal** and one **business**, each under its own IBKR
username. They want both tracked in trodki next to their crypto. Most of their activity is **options**: in one
account's Flex export, 316 of 332 fills are options. So options have to be first-class. Each open option position
must show what it is (underlying, strike, expiry, put/call, size) and what it is worth now. Option fills must flow
into history and realized PnL.

The user chose a **live connection** for positions, rather than end-of-day statements. They also chose to
**not** take over the trading session: they keep trading in TWS and IBKR Mobile while trodki watches.

## Goals

1. Each IBKR account is an exchange connection in trodki: location `ibkr`, two connections (personal, business).
   - Its open positions count toward net worth through the normal balance flow and the dashboard.
   - Values come from IBKR's own marks.
2. Short positions, mainly short options, reduce net worth.
   - **Success criterion:** trodki's total for an account (assets minus liabilities, cash included) matches IBKR's
     net liquidation value for that account. The only allowed differences are FX rounding and mark timing.
3. A dedicated **IBKR positions page** for option detail. One table per account, grouped by underlying, with:
   - contract description, asset class, put/call, strike, expiry, days to expiry, multiplier
   - position (signed contracts or shares), average cost, mark, market value, unrealized PnL, currency
   - per-account totals for market value and unrealized PnL
4. Full trade history from **Flex**: stock, ETF and option fills; option exercise, assignment and expiry; cash
   movements (deposits, withdrawals, dividends, interest, fees); FX conversions; corporate actions.
   - Stored as trodki history events, so trodki's history and accounting include IBKR.
   - **Success criterion:** the IBKR page shows realized PnL per account and per period, in each trade's own
     currency, summed from IBKR's `FifoPnlRealized` on the stored fills. It matches IBKR's reports exactly.
   - trodki's main accounting report works in the main currency at historical FX rates and is **not** expected to
     match IBKR number for number. That difference is documented.
   - Profit and loss for each IBKR account must stay separable, ready for the planned entities feature.
5. Multi-currency: the business account trades in USD, GBP, EUR, CAD and CHF. Values convert to the user's main
   currency.

## Ownership (personal vs business)

The user wants personal and business assets in **one profile**, with ownership shown explicitly and filterable.
That is a separate, profile-wide **entities** feature, designed after this one. It covers ownership on every wallet,
connection and manual balance, plus filters on balances, the dashboard and PnL reports.

For IBKR, that means:
- Each IBKR account is its own connection, named by the user (e.g. "IBKR Personal", "IBKR Business").
- Everything IBKR stores (balances, positions, history events) is attributable to exactly one connection, through
  `location_label`, the connection identifier and the account id. The entities feature can then assign an owner per
  connection without a data migration.

## Non-goals

- Greeks, implied volatility, live quotes, market data subscriptions.
- Placing or cancelling orders, or any trading.
- Futures, bonds, warrants, CFDs, crypto held at IBKR. If they appear, treat them as opaque positions: shown on the
  page and valued at IBKR's mark, nothing more.
- Starting, stopping or installing the IBKR gateway from trodki (v1 documents how to run it).
- Intraday PnL charts and strategy (spread) grouping beyond "grouped by underlying".

## Anti-goals (a failure even if everything else works)

- **Never call an `/iserver/*` endpoint.** Those need a brokerage session. IBKR allows one brokerage session per
  username across all platforms, so trodki would log the user out of TWS or Mobile. Only read-only endpoints are
  allowed (`/portfolio/*`, `/tickle`, `/sso/validate`). Add a test that enforces this.
- Never type, store or handle the user's IBKR password or 2FA. The user logs in to the gateway in their own browser.
- Never trip IBKR's rate-limit penalty box. Breaking the 10 req/s global limit puts the IP in a 15-minute penalty
  box, and repeat offenders can be blocked permanently.
- No traffic anywhere except the local gateway and IBKR's Flex Web Service host. This is trodki's local-only rule.
- Never commit any account data. Account IDs in tests are fake.

## Constraints and facts (from IBKR's docs, read 2026-11-16)

- **Client Portal Gateway.** Retail accounts authenticate through the gateway, a Java program run locally
  (`bin\run.bat root\conf.yaml`, default `https://localhost:5000`, self-signed TLS).
  - The user logs in in a browser on the same machine, and all API calls must come from that machine.
  - One gateway holds one username, so the two accounts need two gateways on different ports
    (`listenPort` in `conf.yaml`, e.g. 5000 and 5001).
- **Two-tier sessions.**
  - A read-only session covers the `/portfolio` endpoints and does not disturb a brokerage session elsewhere.
  - The brokerage session (`/iserver`) is exclusive per username. We stay read-only.
- **Positions.** `GET /portfolio/{accountId}/positions/{pageId}` returns up to 100 per page, and
  `/portfolio/accounts` must be called first. Per position: `conid, contractDesc, position, mktPrice, mktValue,
  avgCost` (includes the multiplier), `avgPrice, unrealizedPnl, realizedPnl` (today), `currency, assetClass, expiry,
  putOrCall, strike, ticker, undConid, multiplier`.
- **Cash and net value.** The read-only `/portfolio/{accountId}/ledger` (cash per currency) and
  `/portfolio/{accountId}/summary` (net liquidation) endpoints. The builder confirms their fields against a live
  call.
- **Pacing.**
  - Global limit is 10 req/s. `/portfolio/accounts` is limited to 1 per 5 s, `/tickle` to 1/s, `/sso/validate`
    to 1/min.
  - A 429 means the 15-minute penalty box.
- **History.**
  - The live API only has 7 days of trades (an `/iserver` call anyway, so off limits).
  - `/pa/transactions` takes one conid per call, at most once per 15 minutes.
  - So history comes from **Flex Web Service**: a token plus a saved Flex query id, no login. The flow is
    `SendRequest` → reference code → `GetStatement`, returning XML or CSV per the query.
  - Flex data is as of the prior close, and that is fine for history.
- **Flex field facts** (checked on the user's exports, and in the portfolio repo's `CLAUDE.md`):
  - Only `LevelOfDetail=EXECUTION` rows are fills.
  - `TradeID` is unique per account.
  - `DateTime` is US Eastern time, in two formats (`YYYYMMDD;HHMMSS` and `YYYY-MM-DD HH:MM:SS`).
  - `Quantity` is signed. `IBCommission` is signed (negative = cost). `TradeMoney` includes the multiplier.
  - `FifoPnlRealized` is net of commission.
  - Option rows carry `Conid, UnderlyingConid, UnderlyingSymbol, Multiplier, Strike, Expiry, Put/Call`.
  - `Notes/Codes` flags assignment, exercise and expiry (e.g. `A`, `Ex`, `Ep`).
- **trodki facts:**
  - There is no stock or option asset type. `CustomAsset` exists, has no oracle and is priced manually.
  - Exchanges return `dict[asset, Balance]` and price them themselves.
  - **Exchange balances have no liabilities path today.**
  - Exchange extra settings live in `integration_connection_settings`, with keys whitelisted in
    `USER_CREDENTIAL_MAPPING_KEYS`.
  - Built-in locations are seeded only on DB creation or a DB upgrade, so existing user DBs need a step that inserts
    the new `ibkr` location row.
  - Reference exchange module: `rotkehlchen/exchanges/coinex.py`. Reference positions feature: Hyperliquid perps
    (`/blockchains/hyperliquid/perps/positions` plus `HyperliquidPerpsTable.vue`).
- **Fork rules** (trodki `CLAUDE.md`): new code goes in new modules, and upstream files are touched only at
  registration points.

## Approaches considered

1. **IBKR as an exchange only.** Net worth and history work, but the balance views show only asset, amount and
   value, so option detail is invisible. Rejected: options are the point.
2. **Standalone IBKR page only.** Option detail works, but IBKR is missing from net worth and accounting. Rejected.
3. **Both, chosen by the user.** An exchange connection for balances and history, plus an IBKR positions endpoint
   and page for option detail. This is the same shape as the Hyperliquid perps work.

Live-data scope, also the user's choice: read-only positions and marks from the gateway, history from Flex. Greeks
were dropped because they need a brokerage session, or a second username per account with its own market data fees.

## Design (decided)

### Connection and credentials

- New location `ibkr` (name "Interactive Brokers"), added to `SUPPORTED_EXCHANGES` and the connector dispatch. The
  user adds one connection per account.
- Per connection:
  - `api_key` = Flex Web Service token.
  - `api_secret` = Flex query id.
  - An extra setting `ibkr_gateway_url` (default `https://localhost:5000`): the gateway that is logged in as this
    account's username.
- The account id (e.g. `U1234567`) is read from `/portfolio/accounts` and checked against the Flex statement's
  account. An optional `ibkr_account_id` setting overrides it, for a login that sees more than one account.
- If a gateway session exposes more than one account and no override is set, the connection picks the one matching
  the Flex statement's account.
- TLS verification is skipped **only** when the gateway URL host is `localhost` or `127.0.0.1`.
- `validate_api_key` checks Flex (token and query id return a statement reference) and the gateway separately. A
  logged-out gateway does not block saving the connection; it only makes positions unavailable until the user logs
  in.

### Gateway session handling

- While a user is logged in to trodki, a background task calls `/tickle` per configured gateway about once a
  minute. That keeps the read-only session alive.
- It reports status per connection: `ok`, `logged_out` (with the URL to open and log in) or `unreachable`
  (gateway not running).
- The status shows on the IBKR page and as a warning when balances are queried.
- Re-login is always the user's job, in their browser.

### Rate limiting

- One shared limiter per gateway, below IBKR's global 10 req/s, plus per-endpoint spacing for `/portfolio/accounts`
  (≥ 5 s).
- On a 429: stop calling that gateway for 15 minutes and surface it. No retry loop.
- Flex calls back off per the Flex error codes (for example "statement not ready, retry").

### Assets

- Every IBKR contract becomes a `CustomAsset` with a **deterministic identifier derived from IBKR's `conid`**
  (for example `ibkr-<conid>`). The conid is IBKR's permanent contract id, so the same contract resolves to the same
  asset in both accounts, in positions and in Flex history.
  - Name: IBKR's contract description (e.g. `ARKG 15JAN27 46 C`).
  - `custom_asset_type`: `IBKR Stock`, `IBKR ETF`, `IBKR Option` or `IBKR Other`.
  - Notes: underlying, strike, expiry, put/call, multiplier, conid.
  - If `CustomAsset` identifiers can't take a custom string, the builder adds an equivalent conid → asset mapping.
    Either way, matching a contract must never depend on its name text.
- Cash balances use trodki's existing fiat assets (USD, EUR, GBP, CAD, CHF, ...).

### Balances and net worth

- `query_balances` reads the gateway positions and ledger for the account.
  - Long positions are assets, valued at `mktValue` converted from the position currency to the main currency.
  - Short positions (negative `position`) are **liabilities**, at the absolute `mktValue`.
  - Cash per currency is an asset; negative cash (margin loan) is a liability.
- trodki's exchange flow has no liabilities, so this needs one narrowly scoped extension. For example:
  - an optional liabilities part in the exchange balance result, used only by IBKR
  - aggregation that adds exchange liabilities to the totals the same way manual liabilities are added
  - The builder picks the exact mechanism, keeping upstream changes to registration-style hooks.
- Each positions fetch also stores the mark as the asset's current price (main currency), so anything else in trodki
  that prices these assets sees IBKR's value.
- If the gateway is logged out, balances report an error for that connection, as any failing exchange does.
  Nothing is silently zeroed.

### Positions endpoint and page

- New read-only endpoint `GET /exchanges/ibkr/positions` (async like the Hyperliquid one). Per connection it returns:
  - account id and gateway status
  - positions with the option fields listed under Goals, plus a computed `days_to_expiry`
  - totals for market value and unrealized PnL
- New frontend page **IBKR positions**, reachable from the drawer near balances (the builder picks the exact nav
  placement under the `meta.nav` conventions):
  - One section per account, rows grouped by underlying, with the columns from Goals.
  - Sorted by underlying, then expiry.
  - A refresh button, and gateway status with a link to the gateway login page when it's logged out.
- The page re-queries on open and on refresh. No background polling beyond the keep-alive tickle.

### History from Flex

- Required sections in the user's Flex query, documented in the setup notes:
  - Trades at execution level
  - Option Exercises, Assignments and Expirations
  - Cash Transactions
  - Account Information
- The format is XML, with dates in a fixed format the parser expects.
- Mapping:
  - **Fills** become a `SwapEvent` group: spend cash and receive the contract asset for a buy, or the reverse for a
    sell.
    - Amounts are in contracts or shares. Cash is `|TradeMoney|`, so the multiplier is already in.
    - Commission is the fee.
    - `unique_id` is `ibkr-<account>-<TradeID>`.
    - `extra_data` keeps the full Flex row, including `FifoPnlRealized`, `Open/CloseIndicator` and `Notes/Codes`.
  - **Opening a short** (sell to open) is represented so the contract becomes a liability and buying it back closes
    it. The builder chooses the event shape that trodki accounting handles correctly for short-then-cover.
  - **Expiry** removes the option at zero proceeds.
  - **Exercise and assignment** remove the option, and the stock leg arrives as a separate Flex trade. The builder
    makes sure the option's premium ends up in the stock leg's basis or in realized PnL the way IBKR reports it.
  - **Deposits and withdrawals** become `AssetMovement`s. Dividends, interest and fees become `HistoryEvent`s.
- **FX conversions** (`AssetClass=CASH`, e.g. `EUR.USD`) become fiat-to-fiat swaps, so cash per currency stays
  right. They are tagged in `extra_data` as conversions, and the IBKR realized-PnL view excludes them.
- **Corporate actions:** the Flex query also includes the Corporate Actions section. Splits and symbol or conid
  changes are mapped so positions and FIFO carry over. Any other action type is logged as a warning, with the raw row
  kept.
- Query ranges are tracked per connection as with other exchanges.
  - A Flex query covers at most 365 days, so ongoing syncs use the saved query's period (last 365 days).
  - **Backfill:** the user runs the same multi-section Flex query by hand in Client Portal, once per calendar year
    since each account opened, exports XML, and imports the files through a one-off import action.
  - The same parser handles both paths. The import accepts files in any order.
  - The trades-only CSVs in the portfolio repo are not the backfill source, because they lack cash, corporate actions
    and EAE (exercise, assignment, expiry) sections.
- Dedupe is by `TradeID` (and the equivalent Flex ids for the other sections) per account, so overlapping
  statements never double-count.
- No IBKR history exists in the user's DB today (checked 2026-11-16), so there is no cleanup before the first sync.

### Verification

- **Unit tests** with recorded-shape fixtures for gateway JSON and Flex XML/CSV. No VCR, no live calls in tests.
  They cover:
  - long and short options, multi-currency and paging
  - logged-out and unreachable gateways, and 429
  - fills, expiry, assignment, cash transactions, and both `DateTime` formats
- **A guard test** that no IBKR code path builds an `/iserver` URL.
- **In-app checks**, on both real accounts with the user logged in to both gateways:
  - Account totals match IBKR's net liquidation.
  - Position count and per-position mark and uPnL match IBKR's Portfolio view.
  - Realized PnL per period on the IBKR page matches IBKR's own realized PnL report for the same period.
  - TWS and Mobile stay logged in throughout.

## Calls made during review (check these)

- PnL is checked against IBKR's own per-fill realized PnL in the trade's currency. trodki's main accounting report is
  not required to match.
- FX conversions are fiat-to-fiat swaps, excluded from the IBKR realized-PnL view.
- Corporate actions: splits and symbol or conid changes are handled; anything else is logged.
- An optional manual account-id override exists per connection.

## Left to the builder

- The exact liabilities mechanism for exchange balances (within the constraint above).
- The deterministic identifier versus a mapping table for contract assets.
- How the `ibkr` location row reaches existing user DBs: a trodki data migration, like migration 31, or an
  idempotent seed at startup.
- The event shape for short-then-cover, and the premium handling on exercise and assignment, as long as the PnL
  criterion holds.
- Nav placement, table component structure, icon, i18n keys.
- Keep-alive scheduling (task manager versus a dedicated greenlet) and the exact limiter numbers within IBKR's
  limits.
