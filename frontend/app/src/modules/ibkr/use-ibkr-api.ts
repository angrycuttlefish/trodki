import { DOWNLOAD_TIMEOUT } from '@/modules/core/api/constants';
import { api } from '@/modules/core/api/rotki-api';
import { type PendingTask, PendingTaskSchema } from '@/modules/core/tasks/types';
import { type IbkrFlexImportResult, IbkrFlexImportResultSchema, type IbkrRealizedPnl, IbkrRealizedPnlSchema } from '@/modules/ibkr/ibkr-types';

interface UseIbkrApiReturn {
  fetchIbkrPositions: () => Promise<PendingTask>;
  fetchIbkrRealizedPnl: (fromTimestamp: number, toTimestamp: number) => Promise<IbkrRealizedPnl>;
  importFlexFile: (name: string, file: File) => Promise<IbkrFlexImportResult>;
}

export function useIbkrApi(): UseIbkrApiReturn {
  const fetchIbkrPositions = async (): Promise<PendingTask> => PendingTaskSchema.parse(
    await api.get<PendingTask>('/exchanges/ibkr/positions', { query: { asyncQuery: true } }),
  );

  /** IBKR's own realized PnL of the stored fills between the two timestamps (seconds). */
  const fetchIbkrRealizedPnl = async (fromTimestamp: number, toTimestamp: number): Promise<IbkrRealizedPnl> => IbkrRealizedPnlSchema.parse(
    await api.get<IbkrRealizedPnl>('/exchanges/ibkr/realized_pnl', { query: { fromTimestamp, toTimestamp }, skipCamelCase: true }),
  );

  /** Stores the history of an exported Flex statement for the named connection. */
  const importFlexFile = async (name: string, file: File): Promise<IbkrFlexImportResult> => {
    const data = new FormData();
    data.append('name', name);
    data.append('file', file);
    return IbkrFlexImportResultSchema.parse(await api.post<IbkrFlexImportResult>('/exchanges/ibkr/flex/import', data, { timeout: DOWNLOAD_TIMEOUT }));
  };

  return { fetchIbkrPositions, fetchIbkrRealizedPnl, importFlexFile };
}
