import type { IbkrPositionRow } from '@/modules/ibkr/ibkr-positions';
import { bigNumberify } from '@rotki/common';
import { libraryDefaults } from '@test/utils/provide-defaults';
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import IbkrPositionsTable from '@/modules/ibkr/IbkrPositionsTable.vue';
import '@test/i18n';

const shortCall: IbkrPositionRow = {
  assetClass: 'OPT',
  avgCost: bigNumberify(250),
  conid: 1,
  contractDesc: 'ARKG 15JAN27 46 C',
  currency: 'USD',
  daysToExpiry: 60,
  expiry: '2027-01-15',
  id: 'IBKR Personal-1',
  mktPrice: bigNumberify(1.5),
  mktValue: bigNumberify(-300),
  multiplier: bigNumberify(100),
  position: bigNumberify(-2),
  putOrCall: 'C',
  strike: bigNumberify(46),
  ticker: 'ARKG',
  undConid: null,
  underlying: 'ARKG',
  unrealizedPnl: bigNumberify(200),
};

describe('modules/ibkr/IbkrPositionsTable', () => {
  it('should show days to expiry and signed position for short options', () => {
    const wrapper = mount(IbkrPositionsTable, {
      props: { loaded: true, loading: false, rows: [shortCall] },
      global: {
        provide: libraryDefaults,
        stubs: { FiatDisplay: { props: ['value'], template: '<span>{{ value.toString() }}</span>' } },
      },
    });

    const row = wrapper.find('[data-testid="ibkr-positions"] tbody tr');
    expect(row.text()).toContain('ARKG 15JAN27 46 C');
    expect(row.find('[data-testid="ibkr-position-size"]').text()).toBe('-2');
    expect(row.find('[data-testid="ibkr-days-to-expiry"]').text()).toBe('60');
  });
});
