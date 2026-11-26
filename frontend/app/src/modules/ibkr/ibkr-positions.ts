import type { IbkrAccount, IbkrPosition, IbkrPositions } from '@/modules/ibkr/ibkr-types';
import { type BigNumber, Zero } from '@rotki/common';

export interface IbkrPositionRow extends IbkrPosition {
  /** Unique within the page: a connection holds one position per contract. */
  id: string;
  /** What the rows are grouped by: the option's underlying or the stock itself. */
  underlying: string;
}

export interface IbkrAccountRow extends Omit<IbkrAccount, 'positions'> {
  name: string;
  positions: IbkrPositionRow[];
}

export interface IbkrTotal {
  marketValue: BigNumber;
  unrealizedPnl: BigNumber;
}

/** Stocks before their options, then options by expiry. */
function compareInGroup(a: IbkrPositionRow, b: IbkrPositionRow): number {
  return (a.expiry ?? '').localeCompare(b.expiry ?? '') || a.contractDesc.localeCompare(b.contractDesc);
}

/**
 * One row per connection, its positions grouped by underlying (alphabetically) and, within a
 * group, ordered by expiry, so every leg of a strategy on one underlying sits together.
 */
export function toAccountRows({ accounts }: IbkrPositions): IbkrAccountRow[] {
  return Object.entries(accounts)
    .map(([key, { name: rawName, positions, ...account }]) => {
      const name = rawName ?? key;
      return {
        ...account,
        name,
        positions: positions
          .map(position => ({ ...position, id: `${name}-${position.conid}`, underlying: position.ticker ?? position.contractDesc }))
          .sort((a, b) => a.underlying.localeCompare(b.underlying) || compareInGroup(a, b)),
      };
    })
    .sort((a, b) => a.name.localeCompare(b.name));
}

export function totalOf(accounts: IbkrAccountRow[]): IbkrTotal {
  return accounts.reduce<IbkrTotal>((acc, { totals }) => ({
    marketValue: acc.marketValue.plus(totals.marketValue),
    unrealizedPnl: acc.unrealizedPnl.plus(totals.unrealizedPnl),
  }), { marketValue: Zero, unrealizedPnl: Zero });
}
