<script setup lang="ts">
import type { IbkrFlexImportResult } from '@/modules/ibkr/ibkr-types';
import { startPromise } from '@shared/utils';
import { msg } from '@/message-key';
import IbkrAccountSection from '@/modules/ibkr/IbkrAccountSection.vue';
import { useIbkrPositions } from '@/modules/ibkr/use-ibkr-positions';
import TablePageLayout from '@/modules/shell/layout/TablePageLayout.vue';

definePage({
  meta: {
    nav: { labelKey: msg.$t('navigation_menu.balances_sub.ibkr_positions'), icon: 'lu-chart-candlestick', parent: '/balances/', order: 22, drawer: 'balances-ibkr' },
  },
});

const { t } = useI18n({ useScope: 'global' });

const importMessage = ref<string>();

const { loaded, loading, refresh, rows } = useIbkrPositions();

function onImported(name: string, { added, skipped }: IbkrFlexImportResult): void {
  set(importMessage, t('ibkr_page.flex_import.done', { added, name, skipped }));
}

onMounted(() => {
  startPromise(refresh());
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
        @click="refresh()"
      >
        <template #prepend>
          <RuiIcon name="lu-refresh-ccw" />
        </template>
        {{ t('common.refresh') }}
      </RuiButton>
    </template>

    <RuiAlert
      v-if="importMessage"
      type="success"
      closeable
      @close="importMessage = undefined"
    >
      {{ importMessage }}
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
      @imported="onImported(account.name, $event)"
    />
  </TablePageLayout>
</template>
