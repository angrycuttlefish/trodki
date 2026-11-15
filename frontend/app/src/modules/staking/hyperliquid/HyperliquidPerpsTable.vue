<script setup lang="ts">
import type { DataTableColumn } from '@rotki/ui-library';
import type { HyperliquidPerpRow } from '@/modules/staking/hyperliquid/use-hyperliquid-perps';
import FiatDisplay from '@/modules/assets/amount-display/components/FiatDisplay.vue';
import HashLink from '@/modules/shell/components/HashLink.vue';
import { HYPERLIQUID_LOCATION } from '@/modules/staking/hyperliquid/constants';

const { rows, loaded, loading } = defineProps<{
  rows: HyperliquidPerpRow[];
  /** Whether a query has succeeded; until then an empty table says nothing could be loaded. */
  loaded: boolean;
  loading: boolean;
}>();

const { t } = useI18n({ useScope: 'global' });

const columns = computed<DataTableColumn<HyperliquidPerpRow>[]>(() => [{
  key: 'address',
  label: t('staking_page.hyperliquid.perps.address'),
}, {
  key: 'market',
  label: t('staking_page.hyperliquid.perps.market'),
  sortable: true,
}, {
  key: 'side',
  label: t('staking_page.hyperliquid.perps.side'),
  sortable: true,
}, {
  align: 'end',
  key: 'leverage',
  label: t('staking_page.hyperliquid.perps.leverage'),
}, {
  align: 'end',
  key: 'size',
  label: t('staking_page.hyperliquid.perps.size'),
}, {
  align: 'end',
  key: 'entryPrice',
  label: t('staking_page.hyperliquid.perps.entry_price'),
}, {
  align: 'end',
  key: 'markPrice',
  label: t('staking_page.hyperliquid.perps.mark_price'),
}, {
  align: 'end',
  key: 'liquidationPrice',
  label: t('staking_page.hyperliquid.perps.liquidation_price'),
}, {
  align: 'end',
  key: 'positionValue',
  label: t('staking_page.hyperliquid.perps.position_value'),
  sortable: true,
}, {
  align: 'end',
  key: 'marginUsed',
  label: t('staking_page.hyperliquid.perps.margin'),
  sortable: true,
}, {
  align: 'end',
  key: 'unrealizedPnl',
  label: t('staking_page.hyperliquid.perps.unrealized_pnl'),
  sortable: true,
}, {
  align: 'end',
  key: 'fundingSinceOpen',
  label: t('staking_page.hyperliquid.perps.funding'),
}]);
</script>

<template>
  <RuiDataTable
    dense
    outlined
    hide-default-footer
    row-attr="id"
    data-testid="hyperliquid-perp-positions"
    :cols="columns"
    :rows="rows"
    :loading="loading"
    :items-per-page="-1"
    :empty="{ label: loaded ? t('staking_page.hyperliquid.perps.empty') : t('staking_page.not_loaded') }"
  >
    <template #item.address="{ row }">
      <HashLink
        :text="row.address"
        :location="HYPERLIQUID_LOCATION"
      />
    </template>
    <template #item.side="{ row }">
      <RuiChip
        size="sm"
        :color="row.side === 'long' ? 'success' : 'error'"
      >
        {{ row.side }}
      </RuiChip>
    </template>
    <template #item.leverage="{ row }">
      {{ t('staking_page.hyperliquid.perps.leverage_value', { leverage: row.leverage.toFormat(), type: row.leverageType }) }}
    </template>
    <template #item.size="{ row }">
      {{ row.size.toFormat() }}
    </template>
    <template #item.entryPrice="{ row }">
      <FiatDisplay
        :value="row.entryPrice"
        from="USD"
      />
    </template>
    <template #item.markPrice="{ row }">
      <FiatDisplay
        :value="row.markPrice"
        from="USD"
      />
    </template>
    <template #item.liquidationPrice="{ row }">
      <FiatDisplay
        v-if="row.liquidationPrice"
        :value="row.liquidationPrice"
        from="USD"
      />
      <span v-else>-</span>
    </template>
    <template #item.positionValue="{ row }">
      <FiatDisplay
        :value="row.positionValue"
        from="USD"
      />
    </template>
    <template #item.marginUsed="{ row }">
      <FiatDisplay
        :value="row.marginUsed"
        from="USD"
      />
    </template>
    <template #item.unrealizedPnl="{ row }">
      <FiatDisplay
        :value="row.unrealizedPnl"
        from="USD"
        pnl
      />
    </template>
    <template #item.fundingSinceOpen="{ row }">
      <FiatDisplay
        :value="row.fundingSinceOpen"
        from="USD"
      />
    </template>
  </RuiDataTable>
</template>
