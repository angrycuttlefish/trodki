import { type BigNumber, Zero } from '@rotki/common';
import { useStakingApi } from '@/modules/staking/api/use-staking-api';
import { type HyperliquidPerpPosition, HyperliquidPerpPositionsSchema } from '@/modules/staking/staking-types';
import { useStakingRows, type UseStakingRowsReturn } from '@/modules/staking/use-staking-rows';
import { ActivityPart } from '@/modules/task-center/core/types';

export interface HyperliquidPerpRow extends HyperliquidPerpPosition {
  address: string;
  /** Unique within the table: an address holds one position per market. */
  id: string;
}

export interface HyperliquidPerpTotal {
  marginUsed: BigNumber;
  positionValue: BigNumber;
  unrealizedPnl: BigNumber;
}

type UseHyperliquidPerpsReturn = UseStakingRowsReturn<HyperliquidPerpRow, HyperliquidPerpTotal>;

function sumOf(rows: HyperliquidPerpRow[], key: keyof HyperliquidPerpTotal): BigNumber {
  return rows.reduce<BigNumber>((acc, row) => acc.plus(row[key]), Zero);
}

/** Loads the open perp positions of every tracked Hyperliquid address, on every DEX. */
export function useHyperliquidPerps(): UseHyperliquidPerpsReturn {
  const { fetchHyperliquidPerpPositions } = useStakingApi();

  return useStakingRows({
    parse: result => HyperliquidPerpPositionsSchema.parse(result),
    part: ActivityPart.HYPERLIQUID_PERPS,
    query: fetchHyperliquidPerpPositions,
    toRows: ({ accounts }) => Object.entries(accounts).flatMap(([address, positions]) =>
      positions.map(position => ({ ...position, address, id: `${address}-${position.market}` })),
    ),
    toTotal: rows => ({
      marginUsed: sumOf(rows, 'marginUsed'),
      positionValue: sumOf(rows, 'positionValue'),
      unrealizedPnl: sumOf(rows, 'unrealizedPnl'),
    }),
  });
}
