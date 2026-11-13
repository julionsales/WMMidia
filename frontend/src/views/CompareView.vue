<script setup>
import { useCatalogStore } from '@/stores/catalog'
import ComparePanel from '@/components/ComparePanel.vue'
import PeriodSelect from '@/components/PeriodSelect.vue'

const catalog = useCatalogStore()
</script>

<template>
  <div class="panel">
    <div class="panel-head">
      <h2><i class="pi pi-chart-bar" /> Comparar empresas</h2>
      <PeriodSelect v-model="catalog.periodDays" />
    </div>
    <ComparePanel :days="catalog.periodDays" />
  </div>
</template>
