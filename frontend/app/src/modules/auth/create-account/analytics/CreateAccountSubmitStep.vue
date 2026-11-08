<script lang="ts" setup>
import CreateAccountErrorAlert from '@/modules/auth/create-account/analytics/CreateAccountErrorAlert.vue';

const {
  error = '',
  loading,
} = defineProps<{
  loading: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  back: [];
  confirm: [];
}>();

const { t } = useI18n({ useScope: 'global' });

const submitLabel = computed<string>(() => t('create_account.actions.create_account'));
</script>

<template>
  <div class="space-y-6">
    <CreateAccountErrorAlert
      v-if="error"
      :error="error"
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
        data-testid="create-account-analytics-continue"
        size="lg"
        class="w-full"
        :disabled="loading"
        :loading="loading"
        color="primary"
        @click="emit('confirm')"
      >
        {{ submitLabel }}
      </RuiButton>
    </div>
  </div>
</template>
