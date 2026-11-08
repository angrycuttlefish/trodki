<script lang="ts" setup>
const { error } = defineProps<{
  error: string;
}>();
</script>

<template>
  <RuiAlert type="error">
    {{ error }}
  </RuiAlert>
</template>
