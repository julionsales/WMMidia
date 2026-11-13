<script setup>
// Comparação lado a lado, sem ranking universal de "melhor empresa".
import { computed, onMounted, ref, watch } from 'vue'
import { api, errorMessage } from '@/api/client'
import { useCatalogStore } from '@/stores/catalog'
import { FORMAT_LABEL, fmtDate, fmtInt, fmtNum, fmtPct } from '@/utils/format'
import StateBlock from '@/components/StateBlock.vue'
import EChart from '@/components/EChart.vue'
import GrowthCell from '@/components/GrowthCell.vue'

const props = defineProps({ initialIds: { type: Array, default: () => [] }, days: { type: Number, default: 30 } })
const catalog = useCatalogStore()
const ids = ref([...props.initialIds])
const data = ref(null)
const loading = ref(false)
const error = ref('')

async function load() {
  if (!ids.value.length) { data.value = null; return }
  loading.value = true
  error.value = ''
  try {
    data.value = (await api.get('/compare', { params: { ids: ids.value, days: props.days }, paramsSerializer: { indexes: null } })).data
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}
watch([ids, () => props.days], load, { deep: true })
onMounted(() => { catalog.loadCompanies(); load() })

const rows = computed(() => data.value?.rows || [])
const names = computed(() => rows.value.map((r) => r.name))
const allFormats = computed(() => [...new Set(rows.value.flatMap((r) => r.formats.map((f) => f.format)))])
const formatOption = computed(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  legend: { bottom: 0 },
  grid: { left: 40, right: 20, top: 20, bottom: 70 },
  xAxis: { type: 'category', data: names.value, axisLabel: { interval: 0, width: 110, overflow: 'truncate' } },
  yAxis: { type: 'value', minInterval: 1 },
  series: allFormats.value.map((fmt) => ({
    name: FORMAT_LABEL[fmt] || fmt, type: 'bar', stack: 'f',
    data: rows.value.map((r) => r.formats.find((f) => f.format === fmt)?.count || 0),
  })),
}))
const brands = computed(() => {
  const set = new Set()
  rows.value.forEach((r) => r.inventory.by_brand.slice(0, 6).forEach((b) => set.add(b.brand)))
  return [...set]
})
const stockOption = computed(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  legend: { bottom: 0, type: 'scroll' },
  grid: { left: 40, right: 20, top: 20, bottom: 70 },
  xAxis: { type: 'category', data: names.value, axisLabel: { interval: 0, width: 110, overflow: 'truncate' } },
  yAxis: { type: 'value', minInterval: 1 },
  series: brands.value.map((brand) => ({
    name: brand, type: 'bar', stack: 'b',
    data: rows.value.map((r) => r.inventory.by_brand.find((b) => b.brand === brand)?.count || 0),
  })),
}))
</script>

<template>
  <div class="stack" style="gap: 16px">
    <div class="toolbar">
      <MultiSelect v-model="ids" :options="catalog.companies" option-label="name" option-value="id" filter display="chip"
                   placeholder="Selecione empresas (até 8)" :selection-limit="8" style="min-width: 320px; max-width: 100%" />
      <span v-if="data" class="period-note"><i class="pi pi-calendar" /> {{ fmtDate(data.period.start) }} a {{ fmtDate(data.period.end) }}</span>
    </div>
    <StateBlock :loading="loading" :error="error" @retry="load" :empty="!ids.length" empty-text="Selecione ao menos uma empresa.">
      <template v-if="data">
        <div class="panel">
          <h3>Indicadores lado a lado</h3>
          <DataTable :value="rows" size="small" scrollable>
            <Column header="Empresa" frozen><template #body="{ data: r }"><RouterLink :to="`/empresas/${r.id}`">{{ r.name }}</RouterLink></template></Column>
            <Column header="Seguidores" class="right"><template #body="{ data: r }">{{ r.followers != null ? fmtInt(r.followers) : 'sem dado' }}</template></Column>
            <Column header="Crescimento (datas reais)"><template #body="{ data: r }"><GrowthCell :growth="r.growth" /></template></Column>
            <Column header="Posts / semana" class="right"><template #body="{ data: r }">
              {{ r.posts.per_week != null ? fmtNum(r.posts.per_week) : '—' }}<span v-if="r.posts.partial_sample" class="muted small" v-tooltip.top="'Amostra parcial: valor mínimo'"> ≥</span></template></Column>
            <Column header="Curtidas (mediana)" class="right"><template #body="{ data: r }">{{ fmtNum(r.likes?.median, 0) }} <span class="muted small">n={{ r.likes?.n ?? 0 }}</span></template></Column>
            <Column header="Comentários (mediana)" class="right"><template #body="{ data: r }">{{ fmtNum(r.comments?.median, 1) }} <span class="muted small">n={{ r.comments?.n ?? 0 }}</span></template></Column>
            <Column header="Interação est. (mediana)" class="right"><template #body="{ data: r }">{{ fmtPct(r.interaction?.median, 3) }} <span class="muted small">n={{ r.interaction?.n ?? 0 }}</span></template></Column>
            <Column header="Veículos ativos" class="right"><template #body="{ data: r }">{{ fmtInt(r.inventory.active_count) }}</template></Column>
            <Column header="Novos / não encontrados" class="right"><template #body="{ data: r }">{{ r.inventory.new_in_period }} / {{ r.inventory.missing_in_period }}</template></Column>
          </DataTable>
        </div>
        <div class="grid two">
          <div class="panel"><h3>Formatos publicados no período</h3>
            <StateBlock :empty="!allFormats.length" empty-text="Sem publicações coletadas."><EChart :option="formatOption" /></StateBlock></div>
          <div class="panel"><h3>Distribuição de estoque por marca (principais)</h3>
            <StateBlock :empty="!brands.length" empty-text="Sem estoque coletado."><EChart :option="stockOption" /></StateBlock></div>
        </div>
        <div v-for="r in rows.filter((x) => x.warnings.length)" :key="r.id" class="notice small">
          <i class="pi pi-info-circle" /> <strong>{{ r.name }}:</strong> {{ r.warnings.join(' ') }}
        </div>
        <div class="panel small">
          <h3>Como ler este comparativo</h3>
          <ul style="margin: 0; padding-left: 18px">
            <li v-for="n in data.notes" :key="n">{{ n }}</li>
            <li>Perfis com públicos e tamanhos diferentes não são diretamente comparáveis; considere o contexto de cada loja.</li>
          </ul>
        </div>
      </template>
    </StateBlock>
  </div>
</template>
