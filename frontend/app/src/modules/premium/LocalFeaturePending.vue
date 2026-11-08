<script setup lang="ts">
/**
 * Stand-in for a view upstream rotki downloads from its premium server at runtime.
 *
 * trodki never loads remote code; these views are being rebuilt locally (roadmap phase 3).
 */
const { feature } = defineProps<{ feature: string }>();

const { t } = useI18n({ useScope: 'global' });
</script>

<template>
  <RuiCard>
    <div class="py-8 text-center text-rui-text-secondary">
      <div class="text-h6 mb-2">
        {{ feature }}
      </div>
      <div>
        {{ t('premium_components.local_feature_pending') }}
      </div>
    </div>
  </RuiCard>
</template>
