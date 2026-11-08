<script lang="ts" setup>
import type { LoginCredentials } from '@/modules/auth/login';
import CreateAccountCredentialsForm
  from '@/modules/auth/create-account/credentials/CreateAccountCredentialsForm.vue';

const form = defineModel<LoginCredentials>('form', { required: true });
const passwordConfirm = defineModel<string>('passwordConfirm', { required: true });
const userPrompted = defineModel<boolean>('userPrompted', { required: true });

const { loading } = defineProps<{
  loading: boolean;
}>();

const emit = defineEmits<{
  back: [];
  next: [];
}>();

const valid = ref<boolean>(false);

const { t } = useI18n({ useScope: 'global' });
</script>

<template>
  <div class="space-y-6">
    <p
      class="text-body-1 text-rui-text-secondary"
    >
      {{ t('create_account.credentials.description') }}
    </p>
    <CreateAccountCredentialsForm
      v-model:valid="valid"
      v-model:form="form"
      v-model:password-confirm="passwordConfirm"
      v-model:user-prompted="userPrompted"
      :loading="loading"
    />
    <div class="grid grid-cols-2 gap-4">
      <RuiButton
        size="lg"
        class="w-full"
        :disabled="loading"
        @click="emit('back')"
      >
        {{ t('common.actions.back') }}
      </RuiButton>
      <RuiButton
        size="lg"
        class="w-full"
        data-testid="create-account-credentials-continue"
        :disabled="!valid || loading"
        :loading="loading"
        color="primary"
        @click="emit('next')"
      >
        {{ t('common.actions.continue') }}
      </RuiButton>
    </div>
  </div>
</template>
