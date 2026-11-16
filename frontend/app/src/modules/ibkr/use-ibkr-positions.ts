import { type IbkrAccountRow, type IbkrTotal, toAccountRows, totalOf } from '@/modules/ibkr/ibkr-positions';
import { IbkrPositionsSchema } from '@/modules/ibkr/ibkr-types';
import { useIbkrApi } from '@/modules/ibkr/use-ibkr-api';
import { useStakingRows, type UseStakingRowsReturn } from '@/modules/staking/use-staking-rows';
import { ActivityPart } from '@/modules/task-center/core/types';

type UseIbkrPositionsReturn = UseStakingRowsReturn<IbkrAccountRow, IbkrTotal>;

/** Loads every Interactive Brokers connection with its open positions, as one row per account. */
export function useIbkrPositions(): UseIbkrPositionsReturn {
  const { fetchIbkrPositions } = useIbkrApi();

  return useStakingRows({
    parse: result => IbkrPositionsSchema.parse(result),
    part: ActivityPart.IBKR_POSITIONS,
    query: fetchIbkrPositions,
    toRows: toAccountRows,
    toTotal: totalOf,
  });
}
