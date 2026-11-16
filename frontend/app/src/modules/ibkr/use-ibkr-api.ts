import { api } from '@/modules/core/api/rotki-api';
import { type PendingTask, PendingTaskSchema } from '@/modules/core/tasks/types';
import { type IbkrFlexImportResult, IbkrFlexImportResultSchema } from '@/modules/ibkr/ibkr-types';

interface UseIbkrApiReturn {
  fetchIbkrPositions: () => Promise<PendingTask>;
  importFlexFile: (name: string, file: File) => Promise<IbkrFlexImportResult>;
}

export function useIbkrApi(): UseIbkrApiReturn {
  const fetchIbkrPositions = async (): Promise<PendingTask> => PendingTaskSchema.parse(
    await api.get<PendingTask>('/exchanges/ibkr/positions', { query: { asyncQuery: true } }),
  );

  /** Stores the history of an exported Flex statement for the named connection. */
  const importFlexFile = async (name: string, file: File): Promise<IbkrFlexImportResult> => {
    const data = new FormData();
    data.append('name', name);
    data.append('file', file);
    return IbkrFlexImportResultSchema.parse(await api.post<IbkrFlexImportResult>('/exchanges/ibkr/flex/import', data));
  };

  return { fetchIbkrPositions, importFlexFile };
}
