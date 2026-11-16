<script setup lang="ts">
import { Blockchain } from '@rotki/common';
import FiatDisplay from '@/modules/assets/amount-display/components/FiatDisplay.vue';
import StakingPageLayout from '@/modules/staking/components/StakingPageLayout.vue';
import StakingTotals, { type StakingTotal } from '@/modules/staking/components/StakingTotals.vue';
import { HYPE_IDENTIFIER, HYPERLIQUID_STAKING_RESTRICTIONS } from '@/modules/staking/hyperliquid/constants';
import HyperliquidPerpsTable from '@/modules/staking/hyperliquid/HyperliquidPerpsTable.vue';
import HyperliquidStakingTable from '@/modules/staking/hyperliquid/HyperliquidStakingTable.vue';
import { useHyperliquidPerps } from '@/modules/staking/hyperliquid/use-hyperliquid-perps';
import { useHyperliquidStaking } from '@/modules/staking/hyperliquid/use-hyperliquid-staking';

defineOptions({
  name: 'HyperliquidPage',
});

const { t } = useI18n({ useScope: 'global' });

const { failedAddresses, loaded, loading, refresh, rows, total } = useHyperliquidStaking();
const perps = useHyperliquidPerps();
const perpRows = perps.rows;
const perpTotal = perps.total;
const perpsLoaded = perps.loaded;
const perpsLoading = perps.loading;

const anyLoading = computed<boolean>(() => get(loading) || get(perpsLoading));
const anyFailed = computed<string[]>(() => [...new Set([...get(failedAddresses), ...get(perps.failedAddresses)])]);

async function refreshAll(): Promise<void> {
  await Promise.all([refresh(), perps.refresh()]);
}

const stateTotals = computed<StakingTotal[]>(() => {
  const { delegated, pendingWithdrawal, undelegated } = get(total);
  return [{
    amount: delegated,
    key: 'delegated',
    label: t('staking_page.hyperliquid.table.delegated'),
    testid: 'hyperliquid-delegated-total',
  }, {
    amount: undelegated,
    key: 'undelegated',
    label: t('staking_page.hyperliquid.table.undelegated'),
    testid: 'hyperliquid-undelegated-total',
  }, {
    amount: pendingWithdrawal,
    key: 'pendingWithdrawal',
    label: t('staking_page.hyperliquid.table.pending_withdrawal'),
    testid: 'hyperliquid-pending-withdrawal-total',
  }];
});
</script>

<template>
  <StakingPageLayout
    location="hyperliquid"
    :chain="Blockchain.HYPERLIQUID"
    :asset="HYPE_IDENTIFIER"
    :failed-addresses="anyFailed"
    :loading="anyLoading"
    :refresh="refreshAll"
    :restrictions="HYPERLIQUID_STAKING_RESTRICTIONS"
  >
    <StakingTotals
      :asset="HYPE_IDENTIFIER"
      :totals="stateTotals"
      :loading="loading"
    />

    <HyperliquidStakingTable
      :rows="rows"
      :loaded="loaded"
      :loading="loading"
    />

    <div class="flex flex-wrap items-baseline gap-x-6 gap-y-1">
      <h6 class="text-h6">
        {{ t('staking_page.hyperliquid.perps.title') }}
      </h6>
      <span class="text-rui-text-secondary text-sm">
        {{ t('staking_page.hyperliquid.perps.position_value') }}:
        <FiatDisplay
          :value="perpTotal.positionValue"
          from="USD"
          class="inline"
        />
      </span>
      <span class="text-rui-text-secondary text-sm">
        {{ t('staking_page.hyperliquid.perps.margin') }}:
        <FiatDisplay
          :value="perpTotal.marginUsed"
          from="USD"
          class="inline"
        />
      </span>
      <span class="text-rui-text-secondary text-sm">
        {{ t('staking_page.hyperliquid.perps.unrealized_pnl') }}:
        <FiatDisplay
          :value="perpTotal.unrealizedPnl"
          from="USD"
          pnl
          class="inline"
        />
      </span>
    </div>

    <HyperliquidPerpsTable
      :rows="perpRows"
      :loaded="perpsLoaded"
      :loading="perpsLoading"
    />
  </StakingPageLayout>
</template>
