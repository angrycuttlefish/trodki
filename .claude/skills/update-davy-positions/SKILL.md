---
name: update-davy-positions
description: Pull the user's current Davy (mydavy.ie) holdings and cash for every trading account and write them into trodki as manual balances. ALWAYS trigger when the user types "/update-davy-positions", says "update my Davy positions", "sync Davy", "refresh Davy holdings in trodki", or similar.
---

# Update Davy positions in trodki

Reads holdings from Davy's own JSON API in the built-in browser pane (the user logs in) and
syncs them into the local trodki backend. Read-only on Davy: never click BUY/SELL/TRADE or
anything that places, changes or cancels an order. Never type the Davy password or 2FA code.

Files in this folder: `extract.js` (runs in the Davy tab), `sync_davy.py` (writes to trodki).

## Steps

1. **trodki running and logged in.** `curl -s http://127.0.0.1:4242/api/1/users` must show a
   user as `loggedin`. If the backend is down, start the dev app (see the trodki repo
   CLAUDE.md, "Windows" environment notes: `pnpm run dev:web` from `frontend/` in the
   background with `VIRTUAL_ENV`, `.venv/Scripts`, `~/.cargo/bin` and the OpenSSL vars). If
   no user is logged in, ask the user to log in at http://localhost:8080.

2. **Davy login.** Open `https://www.mydavy.ie/trading.htm` in the built-in browser pane
   (`preview_start` with the url). If it lands on `login.htm`, ask the user to log in in the
   pane and wait for them. Confirm with javascript_tool that `location.pathname` is
   `/trading.htm`.

3. **Extract.** Read `extract.js` and run its contents with the browser javascript_tool on
   the Davy tab. It walks every trading account (`/api/trading/accounts`),
   switches between them with `trading.htm?refreshAccount=<n>`, reads
   `/api/portfolioholdings/my-holdings?onlyTradable=false` (shares, ETFs and funds; no
   paging, unlike the page's "View all") and `/api/portfolioholdings/portfolio-values`
   (cash, totals, FX), checks each account's holdings add up to Davy's total, and switches
   back to the account that was selected. It returns one JSON string.
   - If it throws an HTTP 401/403 or returns the login page, the Davy session expired: ask
     the user to log in again and re-run.
   - If the account count differs from the last run, tell the user before syncing.

4. **Save** the returned JSON verbatim to `<scratchpad>/davy-YYYY-MM-DD.json`.

5. **Dry run, then sync.**
   `python .claude/skills/update-davy-positions/sync_davy.py <file> --dry-run`
   Show the user the planned adds/updates/removals. If there are removals or new assets,
   say which. Then run it without `--dry-run`.

6. **Report** the per-account table the script prints (positions, holdings, cash, total in
   EUR) and anything flagged with `!`. Tell the user to refresh balances in trodki
   (Balances > Manual balances, or the dashboard refresh) to see the new values.

## How it maps into trodki

| Davy | trodki |
|---|---|
| Security (by ISIN) | Custom asset, type `davy security`, name `<SYMBOL> <name>`, notes `ISIN <isin>`, shared across accounts |
| Market price | Manual latest price in the security's currency (pence converted to GBP); if that does not reproduce Davy's EUR value within 1%, the EUR value / quantity is used instead |
| Holding | Manual balance `Davy <account> <SYMBOL>`, location `banks`, tag `davy`, amount = quantity |
| Cash (EUR, Davy's converted cash value) | Manual balance `Davy <account> cash` in EUR; negative cash is a liability |
| Holding sold | Its `Davy <account> ...` balance is deleted (only for accounts in the snapshot) |

Prices are Davy's 20-minute-delayed marks at the time of the run; they stay fixed in trodki
until the next run. Account numbers and values stay out of the public trodki repo.
