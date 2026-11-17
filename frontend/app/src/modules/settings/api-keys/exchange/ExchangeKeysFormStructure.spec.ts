import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import ExchangeKeysFormStructure from '@/modules/settings/api-keys/exchange/ExchangeKeysFormStructure.vue';
import '@test/i18n';

function labels(location: string): string[] {
  const wrapper = mount(ExchangeKeysFormStructure, {
    props: { location },
    slots: {
      apiKey: '<span data-testid="label">{{ params.label }}</span>',
      apiSecret: '<span data-testid="label">{{ params.label }}</span>',
    },
  });
  return wrapper.findAll('[data-testid="label"]').map(node => node.text());
}

describe('settings/api-keys/exchange/ExchangeKeysFormStructure', () => {
  it('should relabel key and secret as flex token and query id for ibkr', () => {
    expect(labels('ibkr')).toEqual(['exchange_settings.inputs.flex_token', 'exchange_settings.inputs.flex_query_id']);
  });

  it('should keep the api key and secret labels for other exchanges', () => {
    expect(labels('kraken')).toEqual(['exchange_settings.inputs.api_key', 'exchange_settings.inputs.api_secret']);
  });
});
