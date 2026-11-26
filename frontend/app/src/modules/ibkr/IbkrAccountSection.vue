<script setup lang="ts">
import type { BigNumber } from '@rotki/common';
import type { IbkrAccountRow } from '@/modules/ibkr/ibkr-positions';
import type { IbkrFlexImportResult } from '@/modules/ibkr/ibkr-types';
import FiatDisplay from '@/modules/assets/amount-display/components/FiatDisplay.vue';
import IbkrPositionsTable from '@/modules/ibkr/IbkrPositionsTable.vue';
import { useIbkrApi } from '@/modules/ibkr/use-ibkr-api';

const { account, loaded, loading, realizedPnl = {} } = defineProps<{
  account: IbkrAccountRow;
  loaded: boolean;
  loading: boolean;
  /** IBKR's realized PnL of this year's closes, per trade currency. */
  realizedPnl?: Record<string, BigNumber>;
}>();

const emit = defineEmits<{
  imported: [result: IbkrFlexImportResult];
}>();

const { t } = useI18n({ useScope: 'global' });

const importing = ref<boolean>(false);
const importError = ref<string>();

const { importFlexFile } = useIbkrApi();

const realizedCurrencies = computed<string[]>(() => Object.keys(realizedPnl).sort());

const statusMessage = computed<string>(() => {
  switch (account.status) {
    case 'logged_out':
      return t('ibkr_page.gateway_status.logged_out');
    case 'unreachable':
      return t('ibkr_page.gateway_status.unreachable');
    case 'rate_limited':
      return t('ibkr_page.gateway_status.rate_limited');
    default:
      return '';
  }
});

/** Stores the history of the Flex statement the user picked, for this connection. */
async function onFileSelected(event: Event): Promise<void> {
  const input = event.target;
  const file = input instanceof HTMLInputElement ? input.files?.[0] : undefined;
  if (!(input instanceof HTMLInputElement) || !file)
    return;
  set(importing, true);
  set(importError, undefined);
  try {
    emit('imported', await importFlexFile(account.name, file));
  }
  catch (error: unknown) {
    set(importError, error instanceof Error ? error.message : String(error));
  }
  finally {
    set(importing, false);
    input.value = '';
  }
}
</script>

<template>
  <RuiCard data-testid="ibkr-account">
    <template #header>
      {{ account.name }}
      <span
        v-if="account.accountId"
        class="text-rui-text-secondary text-body-2"
      >
        {{ account.accountId }}
      </span>
    </template>

    <RuiAlert
      v-if="account.status !== 'ok'"
      type="warning"
      class="mb-4"
      data-testid="ibkr-gateway-status"
    >
      {{ statusMessage }}
      <a
        data-testid="ibkr-gateway-login"
        class="underline"
        target="_blank"
        rel="noopener noreferrer"
        :href="account.gatewayUrl"
      >
        {{ account.gatewayUrl }}
      </a>
    </RuiAlert>

    <RuiAlert
      v-if="account.error"
      type="error"
      class="mb-4"
      data-testid="ibkr-account-error"
    >
      {{ account.error }}
    </RuiAlert>

    <div class="flex flex-wrap gap-6 mb-4">
      <div>
        <div class="text-rui-text-secondary text-caption">
          {{ t('ibkr_page.positions.market_value') }}
        </div>
        <FiatDisplay
          :value="account.totals.marketValue"
          :from="account.totals.currency"
        />
      </div>
      <div>
        <div class="text-rui-text-secondary text-caption">
          {{ t('ibkr_page.positions.unrealized_pnl') }}
        </div>
        <FiatDisplay
          :value="account.totals.unrealizedPnl"
          :from="account.totals.currency"
          pnl
        />
      </div>
    </div>

    <div
      v-if="realizedCurrencies.length > 0"
      class="flex flex-wrap gap-6 mb-4"
    >
      <div class="text-rui-text-secondary text-caption w-full">
        {{ t('ibkr_page.realized_pnl_this_year') }}
      </div>
      <FiatDisplay
        v-for="currency in realizedCurrencies"
        :key="currency"
        data-testid="ibkr-realized-pnl"
        :data-currency="currency"
        :value="realizedPnl[currency]"
        :currency="currency"
        pnl
      />
    </div>

    <IbkrPositionsTable
      :rows="account.positions"
      :loaded="loaded"
      :loading="loading"
    />

    <div class="mt-4 flex items-center gap-3">
      <label class="cursor-pointer text-rui-primary text-body-2">
        {{ importing ? t('ibkr_page.flex_import.importing') : t('ibkr_page.flex_import.action') }}
        <input
          type="file"
          accept=".xml,.csv"
          class="hidden"
          data-testid="ibkr-flex-import-input"
          :disabled="importing"
          @change="onFileSelected($event)"
        />
      </label>
      <span
        v-if="importError"
        class="text-rui-error text-body-2"
      >
        {{ importError }}
      </span>
    </div>
  </RuiCard>
</template>
