<script setup>
import { computed } from 'vue'
import { RUN_STATUS } from '@/utils/format'
const props = defineProps({ status: { type: String, default: '' }, partial: Boolean })
const meta = computed(() => RUN_STATUS[props.status] || { label: props.status || 'Sem coleta', severity: 'secondary' })
</script>

<template>
  <Tag :value="meta.label" :severity="meta.severity" />
</template>
