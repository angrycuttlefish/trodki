<script setup lang="ts">
import type { HTMLAttributes } from 'vue';
import LogLevelSetting from '@/modules/settings/backend/LogLevelSetting.vue';
import FetchRemoteDataUpdatesSetting from '@/modules/settings/general/FetchRemoteDataUpdatesSetting.vue';
import SettingCategory from '@/modules/settings/SettingCategory.vue';
defineProps<
  /* @vue-ignore */ HTMLAttributes
>();

const { t } = useI18n({ useScope: 'global' });
</script>

<template>
  <SettingCategory>
    <template #title>
      {{ t('general_settings.application.title') }}
    </template>
    <FetchRemoteDataUpdatesSetting />
    <LogLevelSetting />
  </SettingCategory>
</template>
