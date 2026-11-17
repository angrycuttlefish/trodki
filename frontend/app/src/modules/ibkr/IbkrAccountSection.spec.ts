import type { IbkrAccountRow } from '@/modules/ibkr/ibkr-positions';
import { type BigNumber, bigNumberify } from '@rotki/common';
import { mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';
import IbkrAccountSection from '@/modules/ibkr/IbkrAccountSection.vue';
import '@test/i18n';

const importFlexFile = vi.fn<(name: string, file: File) => Promise<{ added: number; skipped: number }>>();

vi.mock('@/modules/ibkr/use-ibkr-api', () => ({
  useIbkrApi: vi.fn(() => ({ importFlexFile })),
}));

function account(status: IbkrAccountRow['status'], error: string | null): IbkrAccountRow {
  return {
    accountId: 'U0000001',
    error,
    gatewayUrl: 'https://localhost:5000',
    name: 'IBKR Personal',
    positions: [],
    status,
    totals: { currency: 'USD', marketValue: bigNumberify(0), unrealizedPnl: bigNumberify(0) },
  };
}

function mountSection(
  status: IbkrAccountRow['status'],
  error: string | null = null,
  realizedPnl: Record<string, BigNumber> = {},
): ReturnType<typeof mount> {
  return mount(IbkrAccountSection, {
    props: { account: account(status, error), loaded: true, loading: false, realizedPnl },
    global: { stubs: { IbkrPositionsTable: true, FiatDisplay: true } },
  });
}

describe('modules/ibkr/IbkrAccountSection', () => {
  it('should show the gateway login link when status is logged_out', () => {
    const link = mountSection('logged_out').find('[data-testid="ibkr-gateway-login"]');

    expect(link.exists()).toBe(true);
    expect(link.attributes('href')).toBe('https://localhost:5000');
  });

  it('should not show the login link when the gateway is ok', () => {
    expect(mountSection('ok').find('[data-testid="ibkr-gateway-login"]').exists()).toBe(false);
  });

  it('should show the error of a connection that could not be read', () => {
    const alert = mountSection('ok', 'IBKR Personal: session expired').find('[data-testid="ibkr-account-error"]');

    expect(alert.text()).toContain('IBKR Personal: session expired');
  });

  it('should show the realized pnl per currency', () => {
    const pnl = mountSection('ok', null, { EUR: bigNumberify(-12.5), USD: bigNumberify(284.4) }).findAll('[data-testid="ibkr-realized-pnl"]');

    expect(pnl.map(node => node.attributes('data-currency'))).toEqual(['EUR', 'USD']);
  });

  it('should call importFlexFile with the selected connection and file', async () => {
    importFlexFile.mockResolvedValue({ added: 12, skipped: 0 });
    const wrapper = mountSection('ok');
    const file = new File(['<FlexQueryResponse/>'], '2025.xml', { type: 'text/xml' });
    const input = wrapper.find<HTMLInputElement>('[data-testid="ibkr-flex-import-input"]');
    Object.defineProperty(input.element, 'files', { value: [file] });

    await input.trigger('change');

    expect(importFlexFile).toHaveBeenCalledWith('IBKR Personal', file);
    expect(wrapper.emitted('imported')).toEqual([[{ added: 12, skipped: 0 }]]);
  });
});
