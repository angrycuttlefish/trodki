import type { Ref } from 'vue';
import type { CreateAccountPayload, LoginCredentials } from '@/modules/auth/login';

interface UseCreateAccountWizardReturn {
  /** The username and password the account is created with. */
  modelCredentialsForm: Ref<LoginCredentials>;
  /** The repeated password, checked against the one in the credentials form. */
  modelPasswordConfirm: Ref<string>;
  /** Whether the user has been warned that a lost password cannot be recovered. */
  modelUserPrompted: Ref<boolean>;
  /** Moves to the following step. */
  nextStep: () => void;
  /** Moves back one step. */
  prevStep: () => void;
  /** Collects the answers into the payload the account is created from. */
  buildPayload: () => CreateAccountPayload;
}

/**
 * The state the create-account wizard carries between its steps, and the transitions that move it.
 *
 * @remarks
 * trodki accounts are local only: the wizard asks for credentials and confirms. There is no
 * premium setup, cloud restore or analytics opt-in.
 *
 * @param step - the wizard's current step, 1-based, shared with the page's stepper
 * @returns the credentials form plus the transitions between the steps
 */
export function useCreateAccountWizard(step: Ref<number>): UseCreateAccountWizardReturn {
  const modelCredentialsForm = ref<LoginCredentials>({ password: '', username: '' });
  const modelPasswordConfirm = shallowRef<string>('');
  const modelUserPrompted = shallowRef<boolean>(false);

  function nextStep(): void {
    set(step, get(step) + 1);
  }

  function prevStep(): void {
    set(step, Math.max(1, get(step) - 1));
  }

  function buildPayload(): CreateAccountPayload {
    return { credentials: get(modelCredentialsForm) };
  }

  return {
    buildPayload,
    modelCredentialsForm,
    modelPasswordConfirm,
    modelUserPrompted,
    nextStep,
    prevStep,
  };
}
