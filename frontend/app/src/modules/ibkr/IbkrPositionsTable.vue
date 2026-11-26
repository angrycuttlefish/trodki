<script setup lang="ts">
import type { DataTableColumn } from '@rotki/ui-library';
import type { IbkrPositionRow } from '@/modules/ibkr/ibkr-positions';
import FiatDisplay from '@/modules/assets/amount-display/components/FiatDisplay.vue';

const { rows, loaded, loading } = defineProps<{
  rows: IbkrPositionRow[];
  /** Whether a query has succeeded; until then an empty table says nothing could be loaded. */
  loaded: boolean;
  loading: boolean;
}>();

const { t } = useI18n({ useScope: 'global' });

const columns = computed<DataTableColumn<IbkrPositionRow>[]>(() => [
  { key: 'underlying', label: t('ibkr_page.positions.underlying') },
  { key: 'contractDesc', label: t('ibkr_page.positions.contract') },
  { key: 'putOrCall', label: t('ibkr_page.positions.put_or_call') },
  { align: 'end', key: 'strike', label: t('ibkr_page.positions.strike') },
  { key: 'expiry', label: t('ibkr_page.positions.expiry') },
  { align: 'end', key: 'daysToExpiry', label: t('ibkr_page.positions.days_to_expiry') },
  { align: 'end', key: 'position', label: t('ibkr_page.positions.position') },
  { align: 'end', key: 'avgCost', label: t('ibkr_page.positions.avg_cost') },
  { align: 'end', key: 'mktPrice', label: t('ibkr_page.positions.mark') },
  { align: 'end', key: 'mktValue', label: t('ibkr_page.positions.market_value') },
  { align: 'end', key: 'unrealizedPnl', label: t('ibkr_page.positions.unrealized_pnl') },
]);
</script>

<template>
  <RuiDataTable
    dense
    outlined
    row-attr="id"
    data-testid="ibkr-positions"
    :cols="columns"
    :rows="rows"
    :loading="loading"
    :empty="{ label: loaded ? t('ibkr_page.positions.empty') : t('staking_page.not_loaded') }"
  >
    <template #item.putOrCall="{ row }">
      {{ row.putOrCall ?? '-' }}
    </template>
    <template #item.strike="{ row }">
      {{ row.strike?.toFormat() ?? '-' }}
    </template>
    <template #item.expiry="{ row }">
      {{ row.expiry ?? '-' }}
    </template>
    <template #item.daysToExpiry="{ row }">
      <span data-testid="ibkr-days-to-expiry">{{ row.daysToExpiry ?? '-' }}</span>
    </template>
    <template #item.position="{ row }">
      <span
        data-testid="ibkr-position-size"
        :class="{ 'text-rui-error': row.position.isNegative() }"
      >
        {{ row.position.toFormat() }}
      </span>
    </template>
    <template #item.avgCost="{ row }">
      {{ row.avgCost.toFormat() }} {{ row.currency }}
    </template>
    <template #item.mktPrice="{ row }">
      {{ row.mktPrice.toFormat() }} {{ row.currency }}
    </template>
    <template #item.mktValue="{ row }">
      <FiatDisplay
        :value="row.mktValue"
        :from="row.currency"
      />
    </template>
    <template #item.unrealizedPnl="{ row }">
      <FiatDisplay
        :value="row.unrealizedPnl"
        :from="row.currency"
        pnl
      />
    </template>
  </RuiDataTable>
</template>
