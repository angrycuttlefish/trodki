// Runs in the logged-in mydavy.ie tab (built-in browser pane, javascript_tool).
// Reads every trading account through Davy's own JSON API (the same calls the Trading page
// makes) and returns one JSON string. Read-only: only GETs; switching the selected account
// is the page's own `trading.htm?refreshAccount=<n>` load, fetched (not navigated).
(async () => {
  const get = async (url) => {
    const r = await fetch(url, { credentials: 'include', headers: { Accept: 'application/json' } });
    if (!r.ok) throw new Error(`${url} -> HTTP ${r.status}`);
    const contentType = r.headers.get('content-type') || '';
    if (r.url.includes('login') || !contentType.includes('application/json'))
      throw new Error(`${url} redirected to login or returned non-JSON (${contentType}); log in to mydavy.ie first`);
    return r.json();
  };
  const select = async (account) => {
    const r = await fetch(`/trading.htm?refreshAccount=${encodeURIComponent(account)}`, { credentials: 'include' });
    if (!r.ok) throw new Error(`select ${account} -> HTTP ${r.status}`);
  };

  const accounts = await get('/api/trading/accounts');
  const original = (await get('/api/portfolioholdings/portfolio-values')).accountNumber;
  const out = { taken_at: new Date().toISOString(), accounts: [] };

  try {
    for (const acct of accounts) {
      await select(acct.accountNumber);
      const [h, pv] = await Promise.all([
        get('/api/portfolioholdings/my-holdings?onlyTradable=false'),
        get('/api/portfolioholdings/portfolio-values'),
      ]);
      if (h.accountNumber !== acct.accountNumber || pv.accountNumber !== acct.accountNumber)
        throw new Error(`asked for ${acct.accountNumber}, Davy returned ${h.accountNumber}/${pv.accountNumber}`);

      const items = [...(h.shares || []), ...(h.etfs || []), ...(h.funds || [])];
      const holdings = items.map(({ portfolioItem: p }) => ({
        isin: p.instrument.isin,
        symbol: p.instrument.joinedSymbol,
        name: p.instrument.name,
        long_name: p.instrument.longName,
        type: p.instrument.assetType,
        quantity: p.quantity,
        price: p.price,
        price_currency: p.priceCur || p.instrument?.price?.currency || null,
        price_units: p.instrument?.price?.units ?? 1,
        value: p.value,
        book_cost: p.bookCost,
      }));
      const sum = holdings.reduce((s, x) => s + (x.value || 0), 0);
      out.accounts.push({
        account: acct.accountNumber,
        name: acct.name,
        currency: pv.currency,
        cash: pv.cashValue,
        holdings_value: pv.totalHoldingValue,
        portfolio_value: pv.portfolioValue,
        holdings_sum_matches: Math.abs(sum - pv.totalHoldingValue) < 0.05,
        fx: Object.fromEntries((pv.exchangeRates || []).map((r) => [r.description, r.rate])),
        holdings,
      });
    }
  } finally {
    await select(original);
  }
  return JSON.stringify(out);
})();
