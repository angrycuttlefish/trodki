import type { Component, Ref } from 'vue';
import type { CreateAccountPayload } from '@/modules/auth/login';
import { mount, type VueWrapper } from '@vue/test-utils';
import { beforeEach, describe, expect, it, type Mock, vi } from 'vitest';
import CreateAccountWizard from '@/modules/auth/create-account/CreateAccountWizard.vue';
import { createRuiPlugin } from '@/plugins/rui';

const { hasProfiles, loadProfiles } = await vi.hoisted(async () => {
  const { ref } = await import('vue');
  return { hasProfiles: ref<boolean>(true), loadProfiles: vi.fn(async () => {}) };
});

vi.mock('@/modules/auth/use-saved-profiles', () => ({
  useSavedProfiles: (): { hasProfiles: Ref<boolean>; loadProfiles: Mock } => ({ hasProfiles, loadProfiles }),
}));

/** Both steps stand in as pass-throughs that expose their three outward signals. */
function stepStub(name: string): Component {
  return {
    emits: ['back', 'next', 'confirm'],
    name,
    props: ['loading', 'error'],
    template: `<div :data-testid="'${name}'">
      <button data-testid="stub-back" @click="$emit('back')" />
      <button data-testid="stub-next" @click="$emit('next')" />
      <button data-testid="stub-confirm" @click="$emit('confirm')" />
    </div>`,
  };
}

function createWrapper(props: Record<string, unknown> = {}): VueWrapper<any> {
  return mount(CreateAccountWizard, {
    global: {
      plugins: [createRuiPlugin({})],
      stubs: {
        CreateAccountCredentials: stepStub('CreateAccountCredentials'),
        CreateAccountSubmitStep: stepStub('CreateAccountSubmitStep'),
        RotkiLogo: true,
        // The real tabs render nothing without a measured layout, so every step renders at once.
        RuiTabItem: { template: '<div><slot /></div>' },
        RuiTabItems: { props: ['modelValue'], template: '<div><slot /></div>' },
      },
    },
    props: { loading: false, step: 1, ...props },
  });
}

function lastStep(wrapper: VueWrapper<any>): number | undefined {
  return wrapper.emitted<[number]>('update:step')?.at(-1)?.[0];
}

/**
 * Presses one of a step's three buttons.
 *
 * @remarks
 * Every step renders at once here, so the button is reached through the step's own component
 * rather than the document, where the first step's copy would answer instead.
 */
async function press(wrapper: VueWrapper<any>, step: string, button: string): Promise<void> {
  await wrapper.findComponent({ name: step }).find(`[data-testid=stub-${button}]`).trigger('click');
}

describe('createAccountWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    set(hasProfiles, true);
  });

  it('should load the saved profiles before it renders', () => {
    createWrapper();

    expect(loadProfiles).toHaveBeenCalledTimes(1);
  });

  describe('the heading', () => {
    it('should name the flow on the first step', () => {
      expect(createWrapper().find('h1').text()).toBe('create_account.title');
    });

    /** The side stepper naming the step is hidden on small screens, so the heading takes over. */
    it('should name the current step past the first', () => {
      const wrapper = createWrapper({ step: 2 });

      expect(wrapper.find('h1').text()).toBe('create_account.steps.step_4.title');
    });
  });

  describe('moving between steps', () => {
    it('should go from the credentials to the confirmation', async () => {
      const wrapper = createWrapper();

      await press(wrapper, 'CreateAccountCredentials', 'next');

      expect(lastStep(wrapper)).toBe(2);
    });

    it('should leave the wizard when backing out of the first step', async () => {
      const wrapper = createWrapper();

      await press(wrapper, 'CreateAccountCredentials', 'back');

      expect(wrapper.emitted('cancel')).toHaveLength(1);
    });

    it('should return to the credentials from the confirmation', async () => {
      const wrapper = createWrapper({ step: 2 });

      await press(wrapper, 'CreateAccountSubmitStep', 'back');

      expect(lastStep(wrapper)).toBe(1);
    });

    /** The error belongs to the submit the user is stepping away from. */
    it('should clear a submit error on the way back', async () => {
      const wrapper = createWrapper({ error: 'wrong password', step: 2 });

      await press(wrapper, 'CreateAccountSubmitStep', 'back');

      expect(wrapper.emitted('clear-error')).toHaveLength(1);
    });

    it('should not clear an error that was never raised', async () => {
      const wrapper = createWrapper({ step: 2 });

      await press(wrapper, 'CreateAccountSubmitStep', 'back');

      expect(wrapper.emitted('clear-error')).toBeUndefined();
    });
  });

  describe('submitting', () => {
    it('should hand the parent the credentials, and nothing else', async () => {
      const wrapper = createWrapper({ step: 2 });

      await press(wrapper, 'CreateAccountSubmitStep', 'confirm');

      expect(wrapper.emitted<[CreateAccountPayload]>('confirm')?.[0]?.[0]).toEqual({
        credentials: { password: '', username: '' },
      });
    });
  });

  describe('the log in shortcut', () => {
    it('should be offered when the machine already has a profile', async () => {
      const wrapper = createWrapper();

      await wrapper.find('[data-testid=login]').trigger('click');

      expect(wrapper.emitted('cancel')).toHaveLength(1);
    });

    it('should be withheld when no account has ever been created here', () => {
      set(hasProfiles, false);

      expect(createWrapper().find('[data-testid=login]').exists()).toBe(false);
    });
  });
});
