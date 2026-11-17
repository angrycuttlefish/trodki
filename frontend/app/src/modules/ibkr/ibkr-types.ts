import { NumericString } from '@rotki/common';
import { z } from 'zod';

/** The state of an IBKR connection's local Client Portal Gateway. */
const IbkrGatewayStatus = z.enum(['ok', 'logged_out', 'unreachable', 'rate_limited']);

/** One open position, as IBKR's gateway reports it. Values are in the position's currency. */
const IbkrPositionSchema = z.object({
  assetClass: z.string(),
  avgCost: NumericString,
  conid: z.number(),
  contractDesc: z.string(),
  currency: z.string(),
  daysToExpiry: z.number().nullable(),
  expiry: z.string().nullable(),
  mktPrice: NumericString,
  mktValue: NumericString,
  multiplier: NumericString,
  position: NumericString,
  putOrCall: z.enum(['C', 'P']).nullable(),
  strike: NumericString.nullable(),
  ticker: z.string().nullable(),
  undConid: z.number().nullable(),
  unrealizedPnl: NumericString,
});

export type IbkrPosition = z.infer<typeof IbkrPositionSchema>;

const IbkrAccountSchema = z.object({
  accountId: z.string().nullable(),
  /** Why the connection could not be read, or its totals are incomplete. */
  error: z.string().nullable().default(null),
  gatewayUrl: z.string(),
  positions: z.array(IbkrPositionSchema),
  status: IbkrGatewayStatus,
  /** Totals converted to the main currency. */
  totals: z.object({
    currency: z.string(),
    marketValue: NumericString,
    unrealizedPnl: NumericString,
  }),
});

export type IbkrAccount = z.infer<typeof IbkrAccountSchema>;

/** Every IBKR connection, keyed by its name. */
export const IbkrPositionsSchema = z.object({
  accounts: z.record(z.string(), IbkrAccountSchema),
  failed: z.array(z.string()).default([]),
});

export type IbkrPositions = z.infer<typeof IbkrPositionsSchema>;

export const IbkrFlexImportResultSchema = z.object({
  added: z.number(),
  skipped: z.number(),
});

export type IbkrFlexImportResult = z.infer<typeof IbkrFlexImportResultSchema>;

/** IBKR's own realized PnL of each connection's fills, per trade currency. */
export const IbkrRealizedPnlSchema = z.object({
  accounts: z.record(z.string(), z.record(z.string(), NumericString)),
});

export type IbkrRealizedPnl = z.infer<typeof IbkrRealizedPnlSchema>;
