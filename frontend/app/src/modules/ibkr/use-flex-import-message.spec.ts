import { describe, expect, it } from 'vitest';
import { useFlexImportMessage } from '@/modules/ibkr/use-flex-import-message';
import '@test/i18n';

const DONE = 'ibkr_page.flex_import.done::12, IBKR Personal, 3';

describe('modules/ibkr/use-flex-import-message', () => {
  it('should be a success naming the counts when the statement had every section', () => {
    expect(useFlexImportMessage().describe('IBKR Personal', { added: 12, missingSections: [], skipped: 3 }))
      .toEqual({ text: DONE, type: 'success' });
  });

  it('should warn and name each section a csv export lacked', () => {
    expect(useFlexImportMessage().describe('IBKR Personal', { added: 12, missingSections: ['CashTransactions', 'CorporateActions', 'OptionEAE'], skipped: 3 }))
      .toEqual({
        text: `${DONE} ibkr_page.flex_import.missing_sections::ibkr_page.flex_import.section.cash_transactions, ibkr_page.flex_import.section.corporate_actions, ibkr_page.flex_import.section.option_eae`,
        type: 'warning',
      });
  });

  it('should show an unknown section by its IBKR name', () => {
    expect(useFlexImportMessage().describe('IBKR Personal', { added: 12, missingSections: ['Transfers'], skipped: 3 }).text)
      .toBe(`${DONE} ibkr_page.flex_import.missing_sections::Transfers`);
  });
});
