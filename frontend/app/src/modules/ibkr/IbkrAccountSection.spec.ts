import type { IbkrAccountRow } from '@/modules/ibkr/ibkr-positions';
import { bigNumberify } from '@rotki/common';
import { mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';
import IbkrAccountSection from '@/modules/ibkr/IbkrAccountSection.vue';
import '@test/i18n';

const importFlexFile = vi.fn<(name: string, file: File) => Promise<{ added: number; skipped: number }>>();

vi.mock('@/modules/ibkr/use-ibkr-api', () => ({
  useIbkrApi: vi.fn(() => ({ importFlexFile })),
}));

function account(status: IbkrAccountRow['status']): IbkrAccountRow {
  return {
    accountId: 'U0000001',
    gatewayUrl: 'https://localhost:5000',
    name: 'IBKR Personal',
    positions: [],
    status,
    totals: { currency: 'USD', marketValue: bigNumberify(0), unrealizedPnl: bigNumberify(0) },
  };
}

function mountSection(status: IbkrAccountRow['status']): ReturnType<typeof mount> {
  return mount(IbkrAccountSection, {
    props: { account: account(status), loaded: true, loading: false },
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
