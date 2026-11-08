import { describe, expect, it } from 'vitest';
import { useCreateAccountWizard } from '@/modules/auth/create-account/use-create-account-wizard';

describe('useCreateAccountWizard', () => {
  it('should step forward and back, never before the first step', () => {
    const step = ref<number>(1);
    const { nextStep, prevStep } = useCreateAccountWizard(step);

    nextStep();
    expect(get(step)).toBe(2);
    prevStep();
    expect(get(step)).toBe(1);
    prevStep();
    expect(get(step)).toBe(1);
  });

  it('should build the payload from the credentials alone', () => {
    const { buildPayload, modelCredentialsForm } = useCreateAccountWizard(ref<number>(1));
    set(modelCredentialsForm, { password: 'secret', username: 'alice' });

    expect(buildPayload()).toEqual({ credentials: { password: 'secret', username: 'alice' } });
  });
});
