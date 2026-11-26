<script setup lang="ts">
import type { BigNumber } from '@rotki/common';
import type { IbkrFlexImportResult } from '@/modules/ibkr/ibkr-types';
import { startPromise } from '@shared/utils';
import { msg } from '@/message-key';
import { isRequestCancellation } from '@/modules/core/api/rotki-api';
import { useLogger } from '@/modules/core/logging/logger';
import IbkrAccountSection from '@/modules/ibkr/IbkrAccountSection.vue';
import { useFlexImportMessage } from '@/modules/ibkr/use-flex-import-message';
import { useIbkrApi } from '@/modules/ibkr/use-ibkr-api';
import { useIbkrPositions } from '@/modules/ibkr/use-ibkr-positions';
import TablePageLayout from '@/modules/shell/layout/TablePageLayout.vue';

definePage({
  meta: {
    nav: { labelKey: msg.$t('navigation_menu.balances_sub.ibkr_positions'), icon: 'lu-chart-candlestick', parent: '/balances/', order: 22, drawer: 'balances-ibkr' },
  },
});

const { t } = useI18n({ useScope: 'global' });

const importMessage = ref<{ text: string; type: 'success' | 'warning' }>();

const { loaded, loading, refresh, rows } = useIbkrPositions();
const { fetchIbkrRealizedPnl } = useIbkrApi();
const { describe: describeImport } = useFlexImportMessage();

const logger = useLogger('ibkr-positions');
const realizedPnl = ref<Record<string, Record<string, BigNumber>>>({});
let realizedPnlRequestId = 0;

/** IBKR's realized PnL of the closes since 1 January, per connection and currency. */
async function loadRealizedPnl(): Promise<void> {
  const requestId = ++realizedPnlRequestId;
  const now = new Date();
  try {
    const { accounts } = await fetchIbkrRealizedPnl(
      Math.floor(Date.UTC(now.getUTCFullYear(), 0, 1) / 1000),
      Math.floor(now.getTime() / 1000),
    );
    if (requestId === realizedPnlRequestId)
      set(realizedPnl, accounts);
  }
  catch (error: unknown) {
    if (!isRequestCancellation(error))
      logger.error('Failed to load IBKR realized PnL', error);
  }
}

async function refreshAll(): Promise<void> {
  await Promise.all([refresh(), loadRealizedPnl()]);
}

function onImported(name: string, result: IbkrFlexImportResult): void {
  set(importMessage, describeImport(name, result));
  startPromise(loadRealizedPnl());
}

onMounted(() => {
  startPromise(refreshAll());
});
</script>

<template>
  <TablePageLayout :title="[t('navigation_menu.balances'), t('navigation_menu.balances_sub.ibkr_positions')]">
    <template #buttons>
      <RuiButton
        variant="outlined"
        color="primary"
        data-testid="ibkr-refresh"
        :loading="loading"
        @click="startPromise(refreshAll())"
      >
        <template #prepend>
          <RuiIcon name="lu-refresh-ccw" />
        </template>
        {{ t('common.refresh') }}
      </RuiButton>
    </template>

    <RuiAlert
      v-if="importMessage"
      :type="importMessage.type"
      closeable
      @close="importMessage = undefined"
    >
      {{ importMessage.text }}
    </RuiAlert>

    <div
      v-if="loaded && rows.length === 0"
      class="text-rui-text-secondary"
      data-testid="ibkr-no-connections"
    >
      {{ t('ibkr_page.no_connections') }}
    </div>

    <IbkrAccountSection
      v-for="account in rows"
      :key="account.name"
      :account="account"
      :loaded="loaded"
      :loading="loading"
      :realized-pnl="realizedPnl[account.name]"
      @imported="onImported(account.name, $event)"
    />
  </TablePageLayout>
</template>
