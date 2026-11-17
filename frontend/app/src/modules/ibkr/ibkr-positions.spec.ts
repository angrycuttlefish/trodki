import { describe, expect, it } from 'vitest';
import { toAccountRows } from '@/modules/ibkr/ibkr-positions';
import { IbkrPositionsSchema } from '@/modules/ibkr/ibkr-types';

function position(conid: number, ticker: string, expiry: string | null, position = '1'): Record<string, unknown> {
  return {
    assetClass: expiry ? 'OPT' : 'STK',
    avgCost: '1',
    conid,
    contractDesc: `${ticker} ${conid}`,
    currency: 'USD',
    daysToExpiry: expiry ? 10 : null,
    expiry,
    mktPrice: '1',
    mktValue: '100',
    multiplier: expiry ? '100' : '1',
    position,
    putOrCall: expiry ? 'C' : null,
    strike: expiry ? '50' : null,
    ticker,
    undConid: null,
    unrealizedPnl: '5',
  };
}

const response = IbkrPositionsSchema.parse({
  accounts: {
    'IBKR Business': { accountId: null, gatewayUrl: 'https://localhost:5001', positions: [], status: 'logged_out', totals: { currency: 'EUR', marketValue: '0', unrealizedPnl: '0' } },
    'IBKR Personal': {
      accountId: 'U0000001',
      gatewayUrl: 'https://localhost:5000',
      positions: [position(3, 'TSLA', '2026-12-18'), position(1, 'AAPL', '2027-01-15'), position(2, 'AAPL', '2026-12-18'), position(4, 'AAPL', null)],
      status: 'ok',
      totals: { currency: 'EUR', marketValue: '400', unrealizedPnl: '20' },
    },
  },
});

describe('modules/ibkr/ibkr-positions', () => {
  it('should group rows by underlying and sort by expiry', () => {
    const personal = toAccountRows(response).find(account => account.name === 'IBKR Personal');

    expect(personal?.positions.map(row => row.conid)).toEqual([4, 2, 1, 3]);
    expect(personal?.positions.map(row => row.underlying)).toEqual(['AAPL', 'AAPL', 'AAPL', 'TSLA']);
  });

  it('should total market value and unrealized pnl per account', () => {
    const [business, personal] = toAccountRows(response);

    expect(business.name).toBe('IBKR Business');
    expect(business.status).toBe('logged_out');
    expect(personal.totals.marketValue.toString()).toBe('400');
    expect(personal.totals.unrealizedPnl.toString()).toBe('20');
  });
});
