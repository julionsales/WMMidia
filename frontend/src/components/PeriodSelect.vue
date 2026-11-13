<script setup>
import { PERIOD_OPTIONS } from '@/stores/catalog'
const model = defineModel({ type: Number, default: 30 })
</script>

<template>
  <SelectButton v-model="model" :options="PERIOD_OPTIONS" option-label="label" option-value="value" :allow-empty="false"
                aria-label="Período de análise" />
</template>
