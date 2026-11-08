<script setup lang="ts">
const coingecko = defineModel<string>('coingecko', { required: true });
const cryptocompare = defineModel<string>('cryptocompare', { required: true });

const { coingeckoErrors, cryptocompareErrors, disabled = false } = defineProps<{
  coingeckoErrors: string[];
  cryptocompareErrors: string[];
  disabled?: boolean;
}>();

const emit = defineEmits<{
  touch: [field: 'coingecko' | 'cryptocompare'];
}>();

const { t } = useI18n({ useScope: 'global' });
</script>

<template>
  <RuiTextField
    v-model="coingecko"
    data-testid="coingecko-input"
    color="primary"
    clearable
    class="col-span-2"
    :hint="t('asset_form.labels.coingecko_hint')"
    :label="t('asset_form.labels.coingecko')"
    :error-messages="coingeckoErrors"
    :disabled="disabled"
    @update:model-value="emit('touch', 'coingecko')"
  />
  <RuiTextField
    v-model="cryptocompare"
    data-testid="cryptocompare-input"
    color="primary"
    clearable
    class="col-span-2"
    :label="t('asset_form.labels.cryptocompare')"
    :hint="t('asset_form.labels.cryptocompare_hint')"
    :error-messages="cryptocompareErrors"
    :disabled="disabled"
    @update:model-value="emit('touch', 'cryptocompare')"
  />
</template>
