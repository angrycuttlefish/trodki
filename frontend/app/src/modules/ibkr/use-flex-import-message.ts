import type { IbkrFlexImportResult } from '@/modules/ibkr/ibkr-types';

interface FlexImportMessage {
  text: string;
  type: 'success' | 'warning';
}

interface UseFlexImportMessageReturn {
  describe: (name: string, result: IbkrFlexImportResult) => FlexImportMessage;
}

/**
 * The page message for a finished Flex statement import.
 *
 * @remarks
 * A CSV export may lack sections (a trades export has no cash or corporate actions). Its trades
 * are still imported, so the message is a warning that names what the file did not contain.
 */
export function useFlexImportMessage(): UseFlexImportMessageReturn {
  const { t } = useI18n({ useScope: 'global' });

  function sectionName(section: string): string {
    switch (section) {
      case 'CashTransactions':
        return t('ibkr_page.flex_import.section.cash_transactions');
      case 'CorporateActions':
        return t('ibkr_page.flex_import.section.corporate_actions');
      case 'OptionEAE':
        return t('ibkr_page.flex_import.section.option_eae');
      default:
        return section;
    }
  }

  function describe(name: string, { added, missingSections, skipped }: IbkrFlexImportResult): FlexImportMessage {
    const done = t('ibkr_page.flex_import.done', { added, name, skipped });
    if (missingSections.length === 0)
      return { text: done, type: 'success' };
    const sections = missingSections.map(sectionName).join(', ');
    return { text: `${done} ${t('ibkr_page.flex_import.missing_sections', { sections })}`, type: 'warning' };
  }

  return { describe };
}
