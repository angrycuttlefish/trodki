<script lang="ts" setup>
import type { CreateAccountPayload } from '@/modules/auth/login';
import CreateAccountSubmitStep
  from '@/modules/auth/create-account/analytics/CreateAccountSubmitStep.vue';
import CreateAccountCredentials
  from '@/modules/auth/create-account/credentials/CreateAccountCredentials.vue';
import { useCreateAccountSteps } from '@/modules/auth/create-account/use-create-account-steps';
import { useCreateAccountWizard } from '@/modules/auth/create-account/use-create-account-wizard';
import { useSavedProfiles } from '@/modules/auth/use-saved-profiles';

const step = defineModel<number>('step', { required: true });

const {
  error = '',
  loading,
} = defineProps<{
  loading: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  'cancel': [];
  'confirm': [payload: CreateAccountPayload];
  'clear-error': [];
}>();

const { t } = useI18n({ useScope: 'global' });

const {
  buildPayload,
  modelCredentialsForm,
  modelPasswordConfirm,
  modelUserPrompted,
  nextStep,
  prevStep: rewind,
} = useCreateAccountWizard(step);

const { hasProfiles, loadProfiles } = useSavedProfiles();
const { steps } = useCreateAccountSteps();

/** Names the step on screen, since the side stepper that also names it is hidden on small screens. */
const heading = computed<string>(() => {
  const current = get(step);
  if (current > 1)
    return get(steps)[current - 1]?.title ?? '';
  return t('create_account.title');
});

const cancel = (): void => emit('cancel');
const errorClear = (): void => emit('clear-error');

/** The error belongs to the submit the user is stepping away from, so going back clears it. */
function prevStep(): void {
  rewind();
  if (error)
    errorClear();
}

function confirm(): void {
  emit('confirm', buildPayload());
}

onBeforeMount(loadProfiles);
</script>

<template>
  <Transition
    appear
    enter-from-class="translate-y-5 opacity-0"
    enter-to-class="translate-y-0 opacity-1"
    enter-active-class="transform duration-300"
    leave-from-class="translate-y-0 opacity-1"
    leave-to-class="-translate-y-5 opacity-0"
    leave-active-class="transform duration-100"
  >
    <div>
      <div class="max-w-110 mx-auto">
        <div class="flex flex-col">
          <div class="text-caption uppercase tracking-wide text-rui-text-secondary mb-1">
            {{ t('create_account.step_progress', { current: step, total: steps.length }) }}
          </div>
          <h1 class="text-h4 mb-2">
            {{ heading }}
          </h1>
          <div class="w-full">
            <RuiTabItems
              class="overflow-visible!"
              :model-value="step - 1"
            >
              <RuiTabItem>
                <CreateAccountCredentials
                  v-model:form="modelCredentialsForm"
                  v-model:password-confirm="modelPasswordConfirm"
                  v-model:user-prompted="modelUserPrompted"
                  :loading="loading"
                  @back="cancel()"
                  @next="nextStep()"
                />
              </RuiTabItem>
              <RuiTabItem>
                <CreateAccountSubmitStep
                  :loading="loading"
                  :error="error"
                  @back="prevStep()"
                  @confirm="confirm()"
                />
              </RuiTabItem>
            </RuiTabItems>
          </div>
          <div
            v-if="hasProfiles"
            class="flex flex-wrap gap-1 sm:gap-0 items-center justify-center py-6 text-rui-text-secondary"
          >
            <span>{{ t('create_account.have_account.description') }}</span>
            <RuiButton
              color="primary"
              size="lg"
              variant="text"
              :disabled="loading"
              type="button"
              data-testid="login"
              class="py-1"
              @click="cancel()"
            >
              {{ t('create_account.have_account.log_in') }}
            </RuiButton>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>
