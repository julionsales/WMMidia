<script setup>
// Tabela de veículos com filtros, ordenação e paginação no servidor + exportação.
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api, download, errorMessage } from '@/api/client'
import { useCatalogStore } from '@/stores/catalog'
import { fmtBRL, fmtDate, fmtInt, VEHICLE_STATUS } from '@/utils/format'
import StateBlock from '@/components/StateBlock.vue'
import VehicleDialog from '@/components/VehicleDialog.vue'

const props = defineProps({ companyId: { type: String, default: '' }, showCompany: Boolean })
const catalog = useCatalogStore()
const state = reactive({ items: [], total: 0, loading: false, error: '' })
const facets = ref([])
const filters = reactive({
  company_id: props.companyId || null, brand: null, model: null, year_min: null, year_max: null,
  price_min: null, price_max: null, status: 'ativo', search: '',
})
const paging = reactive({ page: 1, size: 25, sort: 'brand', order: 'asc' })
const selectedVehicle = ref(null)
const statusOptions = [
  { label: 'Ativos', value: 'ativo' },
  { label: 'Não encontrados na última coleta', value: 'nao_encontrado' },
  { label: 'Todos', value: 'todos' },
]
const models = computed(() => facets.value.find((f) => f.brand === filters.brand)?.models || [])

function params() {
  const p = { ...filters, ...paging }
  Object.keys(p).forEach((k) => { if (p[k] === null || p[k] === '') delete p[k] })
  return p
}

async function load() {
  state.loading = true
  state.error = ''
  try {
    const { data } = await api.get('/inventory/vehicles', { params: params() })
    state.items = data.items
    state.total = data.total
  } catch (e) {
    state.error = errorMessage(e)
  } finally {
    state.loading = false
  }
}
async function loadFacets() {
  try {
    facets.value = (await api.get('/inventory/facets', { params: filters.company_id ? { company_id: filters.company_id } : {} })).data
  } catch {
    facets.value = []
  }
}

let timer
watch(() => ({ ...filters }), (now, before) => {
  if (now.company_id !== before.company_id) { filters.brand = null; loadFacets() }
  if (now.brand !== before.brand) filters.model = null
  clearTimeout(timer)
  timer = setTimeout(() => { paging.page = 1; load() }, 300)
})

function onPage(e) { paging.page = e.page + 1; paging.size = e.rows; load() }
function onSort(e) { paging.sort = e.sortField || 'brand'; paging.order = e.sortOrder === -1 ? 'desc' : 'asc'; load() }
function exportAs(fmt) {
  const p = params()
  delete p.page; delete p.size; delete p.sort; delete p.order
  download(`/exports/vehicles.${fmt}`, p)
}
function clear() {
  Object.assign(filters, { brand: null, model: null, year_min: null, year_max: null, price_min: null, price_max: null, status: 'ativo', search: '' })
}

onMounted(async () => {
  if (props.showCompany) catalog.loadCompanies()
  await loadFacets()
  load()
})
</script>

<template>
  <div class="stack" style="gap: 10px">
    <div class="toolbar">
      <Select v-if="showCompany" v-model="filters.company_id" :options="catalog.companies" option-label="name" option-value="id"
              placeholder="Todas as empresas" show-clear filter style="min-width: 200px" />
      <Select v-model="filters.brand" :options="facets" option-label="label" option-value="brand" placeholder="Marca" show-clear filter />
      <Select v-model="filters.model" :options="models" placeholder="Modelo" show-clear filter :disabled="!filters.brand" />
      <InputNumber v-model="filters.year_min" placeholder="Ano de" :use-grouping="false" :min="1950" :max="2100" input-style="width: 90px" />
      <InputNumber v-model="filters.year_max" placeholder="Ano até" :use-grouping="false" :min="1950" :max="2100" input-style="width: 90px" />
      <InputNumber v-model="filters.price_min" placeholder="Preço de" mode="currency" currency="BRL" locale="pt-BR" :max-fraction-digits="0" input-style="width: 130px" />
      <InputNumber v-model="filters.price_max" placeholder="Preço até" mode="currency" currency="BRL" locale="pt-BR" :max-fraction-digits="0" input-style="width: 130px" />
      <Select v-model="filters.status" :options="statusOptions" option-label="label" option-value="value" />
      <InputText v-model="filters.search" placeholder="Buscar modelo/versão" />
      <Button icon="pi pi-filter-slash" text v-tooltip.top="'Limpar filtros'" @click="clear" />
      <span class="spacer" />
      <Button label="CSV" icon="pi pi-download" size="small" text @click="exportAs('csv')" />
      <Button label="Excel" icon="pi pi-file-excel" size="small" text @click="exportAs('xlsx')" />
    </div>
    <StateBlock :error="state.error" @retry="load">
      <DataTable :value="state.items" lazy paginator :rows="paging.size" :total-records="state.total" :loading="state.loading"
                 :first="(paging.page - 1) * paging.size" :rows-per-page-options="[25, 50, 100]" size="small" scrollable data-key="id"
                 :sort-field="paging.sort" :sort-order="paging.order === 'asc' ? 1 : -1" @page="onPage" @sort="onSort"
                 selection-mode="single" @row-select="selectedVehicle = $event.data">
        <template #empty><span class="muted">Nenhum veículo encontrado com estes filtros.</span></template>
        <Column v-if="showCompany" header="Empresa" field="company_name" />
        <Column field="brand" header="Marca" sortable><template #body="{ data }">{{ data.brand_display }}</template></Column>
        <Column field="model" header="Modelo" sortable />
        <Column header="Versão" style="min-width: 200px"><template #body="{ data }"><span class="small">{{ data.version || '—' }}</span></template></Column>
        <Column field="year" header="Ano" sortable>
          <template #body="{ data }">{{ data.year_fabrication ? `${data.year_fabrication}/` : '' }}{{ data.year_model || '—' }}</template>
        </Column>
        <Column field="km" header="Km" sortable class="right"><template #body="{ data }">{{ data.km != null ? fmtInt(data.km) : '—' }}</template></Column>
        <Column field="price" header="Preço" sortable class="right">
          <template #body="{ data }">
            <span class="nowrap">{{ fmtBRL(data.price, data.price_on_request) }}</span>
            <div v-if="data.price_change_count" class="muted small">{{ data.price_change_count }} alteração(ões)</div>
          </template>
        </Column>
        <Column field="first_seen" header="Primeira observação" sortable><template #body="{ data }">{{ fmtDate(data.first_seen_at) }}</template></Column>
        <Column field="last_seen" header="Última observação" sortable><template #body="{ data }">{{ fmtDate(data.last_seen_at) }}</template></Column>
        <Column header="Tempo observado" class="right"><template #body="{ data }">{{ data.observed_days }} dia(s)</template></Column>
        <Column header="Situação">
          <template #body="{ data }"><Tag :value="VEHICLE_STATUS[data.status]?.label" :severity="VEHICLE_STATUS[data.status]?.severity" /></template>
        </Column>
        <Column header="">
          <template #body="{ data }">
            <a v-if="data.url" :href="data.url" target="_blank" rel="noopener" v-tooltip.top="'Abrir anúncio'" @click.stop><i class="pi pi-external-link" /></a>
          </template>
        </Column>
      </DataTable>
    </StateBlock>
    <p class="muted small" style="margin: 0">Clique em uma linha para ver o histórico de preço e de presença.
      "Não encontrado na última coleta" não indica venda confirmada.</p>
    <VehicleDialog :vehicle-id="selectedVehicle?.id" @close="selectedVehicle = null" />
  </div>
</template>
