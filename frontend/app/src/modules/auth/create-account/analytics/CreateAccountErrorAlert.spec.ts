import { I18nTStub } from '@test/stubs/I18nT';
import { mount, type VueWrapper } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import ExternalLink from '@/modules/shell/components/ExternalLink.vue';
import CreateAccountErrorAlert from './CreateAccountErrorAlert.vue';

function mountAlert(error: string): VueWrapper<InstanceType<typeof CreateAccountErrorAlert>> {
  return mount(CreateAccountErrorAlert, {
    global: { stubs: { I18nT: I18nTStub } },
    props: { error },
  });
}

describe('modules/auth/create-account/analytics/CreateAccountErrorAlert', () => {
  it('should render a plain error without a link', () => {
    const wrapper = mountAlert('Something went wrong');

    expect(wrapper.text()).toContain('Something went wrong');
    expect(wrapper.findComponent(ExternalLink).exists()).toBe(false);
  });

  it('should not render a link when the placeholder is absent', () => {
    const wrapper = mountAlert('DEVICE_LIMIT_LINK without underscores');

    expect(wrapper.findComponent(ExternalLink).exists()).toBe(false);
    expect(wrapper.text()).toContain('DEVICE_LIMIT_LINK without underscores');
  });

  it('should tolerate an empty error string', () => {
    const wrapper = mountAlert('');

    expect(wrapper.findComponent(ExternalLink).exists()).toBe(false);
  });
});
