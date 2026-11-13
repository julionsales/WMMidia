<script setup>
import { onMounted, ref } from 'vue'
import { useCatalogStore } from '@/stores/catalog'
import VehiclesTable from '@/components/VehiclesTable.vue'
import InventoryPanel from '@/components/InventoryPanel.vue'
import PeriodSelect from '@/components/PeriodSelect.vue'

const catalog = useCatalogStore()
const rankingCompany = ref(null)
onMounted(() => catalog.loadCompanies())
</script>

<template>
  <div class="panel">
    <h2><i class="pi pi-car" /> Veículos observados</h2>
    <VehiclesTable show-company />
  </div>
  <div class="panel">
    <div class="panel-head">
      <h2><i class="pi pi-chart-bar" /> Rankings e histórico por empresa</h2>
      <div class="toolbar">
        <Select v-model="rankingCompany" :options="catalog.companies" option-label="name" option-value="id" filter
                placeholder="Escolha uma empresa" style="min-width: 240px" />
        <PeriodSelect v-model="catalog.periodDays" />
      </div>
    </div>
    <InventoryPanel v-if="rankingCompany" :key="rankingCompany" :company-id="rankingCompany" :days="catalog.periodDays" />
    <p v-else class="muted small">Selecione uma empresa para ver rankings de marcas e modelos, faixas de preço, alterações e tempo observado.</p>
  </div>
</template>
