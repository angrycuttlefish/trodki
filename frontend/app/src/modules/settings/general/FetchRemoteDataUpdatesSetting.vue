<script setup lang="ts">
import SettingsItem from '@/modules/settings/controls/SettingsItem.vue';
import SettingSwitch from '@/modules/settings/controls/SettingSwitch.vue';

const { t } = useI18n({ useScope: 'global' });
</script>

<template>
  <SettingsItem setting-key="fetchRemoteDataUpdates">
    <template #title>
      {{ t('general_settings.fetch_remote_data_updates.title') }}
    </template>
    <template #subtitle>
      {{ t('general_settings.fetch_remote_data_updates.subtitle') }}
    </template>
    <SettingSwitch
      setting="fetchRemoteDataUpdates"
      :label="t('general_settings.fetch_remote_data_updates.label')"
    />
  </SettingsItem>
</template>
