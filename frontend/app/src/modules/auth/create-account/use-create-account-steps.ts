import type { ComputedRef } from 'vue';

interface CreateAccountStep {
  title: string;
  description?: string;
}

interface UseCreateAccountStepsReturn {
  steps: ComputedRef<CreateAccountStep[]>;
}

/**
 * The wizard's steps.
 *
 * @remarks
 * Shared by the side stepper and the wizard's own heading, so the two always name the step alike.
 */
export function useCreateAccountSteps(): UseCreateAccountStepsReturn {
  const { t } = useI18n({ useScope: 'global' });

  const steps = computed<CreateAccountStep[]>(() => [
    {
      description: t('create_account.steps.step_3.description'),
      title: t('create_account.steps.step_3.title'),
    },
    {
      title: t('create_account.steps.step_4.title'),
    },
  ]);

  return { steps };
}
