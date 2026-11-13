<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api, errorMessage } from '@/api/client'
import { fmtBRL, fmtDate, fmtDateTime, fmtInt, relative } from '@/utils/format'
import StateBlock from '@/components/StateBlock.vue'
import KpiCard from '@/components/KpiCard.vue'
import EChart from '@/components/EChart.vue'
import VehiclesTable from '@/components/VehiclesTable.vue'

const props = defineProps({ companyId: { type: String, required: true }, days: { type: Number, default: 30 } })
const data = ref(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = (await api.get(`/inventory/companies/${props.companyId}/overview`, { params: { days: props.days } })).data
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}
watch(() => props.days, load)
onMounted(load)

const brandOption = computed(() => {
  const rows = (data.value?.by_brand || []).slice(0, 12).reverse()
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 110, right: 30, top: 10, bottom: 30 },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: { type: 'category', data: rows.map((r) => r.brand) },
    series: [{ type: 'bar', data: rows.map((r) => r.count), itemStyle: { color: '#0f766e' }, label: { show: true, position: 'right' } }],
  }
})
const bandOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 20, top: 10, bottom: 60 },
  xAxis: { type: 'category', data: (data.value?.price_bands || []).map((b) => b.band), axisLabel: { rotate: 25 } },
  yAxis: { type: 'value', minInterval: 1 },
  series: [{ type: 'bar', data: (data.value?.price_bands || []).map((b) => b.count), itemStyle: { color: '#14b8a6' } }],
}))
</script>

<template>
  <div class="stack" style="gap: 16px">
    <StateBlock :loading="loading" :error="error" @retry="load" :empty="data && !data.observed_total"
                empty-text="Nenhuma coleta de estoque realizada ainda. Use “Coletar estoque”.">
      <template v-if="data">
        <div class="row small muted">
          <span>Última coleta bem-sucedida: <strong>{{ fmtDateTime(data.summary.last_success_at) }}</strong> ({{ relative(data.summary.last_success_at) }})</span>
          <span>· Última coleta completa: {{ fmtDateTime(data.summary.last_complete_at) }}</span>
          <span>· Período: {{ fmtDate(data.period.start) }} a {{ fmtDate(data.period.end) }}</span>
        </div>
        <div v-if="data.summary.last_success_at && data.summary.last_complete_at !== data.summary.last_success_at" class="notice">
          <i class="pi pi-exclamation-circle" /> A coleta mais recente foi parcial: anúncios ausentes não foram marcados como “não encontrados”.
        </div>
        <div class="grid kpis">
          <KpiCard label="Veículos ativos" icon="pi pi-car" :value="fmtInt(data.active_count)" />
          <KpiCard label="Anúncios já observados" icon="pi pi-database" :value="fmtInt(data.observed_total)" hint="desde o início do monitoramento" />
          <KpiCard label="Novos no período" icon="pi pi-plus-circle" :value="fmtInt(data.new_in_period)" hint="observados pela primeira vez" />
          <KpiCard label="Não encontrados no período" icon="pi pi-eye-slash" :value="fmtInt(data.missing_in_period)" hint="não indica venda" />
          <KpiCard label="Alterações de preço" icon="pi pi-tag" :value="fmtInt(data.price_changes.length)" hint="no período" />
          <KpiCard label="Tempo observado (média)" icon="pi pi-clock" :value="data.observed_days.avg != null ? `${data.observed_days.avg} dias` : '—'"
                   :hint="`máximo ${data.observed_days.max ?? '—'} dias`" />
        </div>
        <div class="grid two">
          <div class="panel"><h3>Ranking de marcas</h3>
            <StateBlock :empty="!data.by_brand.length" empty-text="Sem veículos ativos."><EChart :option="brandOption" height="320px" /></StateBlock>
          </div>
          <div class="panel"><h3>Faixas de preço</h3>
            <StateBlock :empty="!data.price_bands.length"><EChart :option="bandOption" height="320px" /></StateBlock>
          </div>
        </div>
        <div class="grid two">
          <div class="panel">
            <h3>Ranking de modelos</h3>
            <DataTable :value="data.by_model" size="small" paginator :rows="10" scrollable>
              <Column header="Marca / modelo"><template #body="{ data: m }">{{ m.brand }} <strong>{{ m.model }}</strong></template></Column>
              <Column field="count" header="Qtd." class="right" sortable />
              <Column header="Faixa de preço"><template #body="{ data: m }"><span class="small nowrap">{{ fmtBRL(m.price_min) }} – {{ fmtBRL(m.price_max) }}</span></template></Column>
              <Column header="Km médio" class="right"><template #body="{ data: m }">{{ m.km_avg != null ? fmtInt(m.km_avg) : '—' }}</template></Column>
              <Column field="content_category" header="Categoria" />
            </DataTable>
          </div>
          <div class="panel">
            <h3>Alterações de preço no período</h3>
            <StateBlock :empty="!data.price_changes.length" empty-text="Nenhuma alteração de preço observada no período.">
              <DataTable :value="data.price_changes" size="small" paginator :rows="10" scrollable>
                <Column header="Data"><template #body="{ data: c }">{{ fmtDate(c.observed_at) }}</template></Column>
                <Column header="Veículo"><template #body="{ data: c }">{{ c.brand }} {{ c.model }}</template></Column>
                <Column header="Antes" class="right"><template #body="{ data: c }">{{ fmtBRL(c.previous_price) }}</template></Column>
                <Column header="Depois" class="right"><template #body="{ data: c }">{{ fmtBRL(c.price) }}</template></Column>
                <Column header="Variação" class="right"><template #body="{ data: c }">
                  <span :style="{ color: c.delta < 0 ? '#047857' : '#b91c1c' }">{{ c.delta != null ? fmtBRL(c.delta) : '—' }}</span></template></Column>
              </DataTable>
            </StateBlock>
          </div>
        </div>
        <div class="panel">
          <h3>Anúncios com maior tempo observado</h3>
          <DataTable :value="data.longest_observed" size="small" scrollable>
            <Column header="Veículo"><template #body="{ data: v }">{{ v.brand }} {{ v.model }} <span class="muted small">{{ v.version }}</span></template></Column>
            <Column header="Ano" field="year_model" />
            <Column header="Preço" class="right"><template #body="{ data: v }">{{ fmtBRL(v.price) }}</template></Column>
            <Column header="Primeira observação"><template #body="{ data: v }">{{ fmtDate(v.first_seen_at) }}</template></Column>
            <Column header="Dias observado" field="observed_days" class="right" />
          </DataTable>
          <p class="muted small">{{ data.observed_days.note }}</p>
        </div>
      </template>
    </StateBlock>
    <div class="panel">
      <h3>Veículos</h3>
      <VehiclesTable :company-id="companyId" />
    </div>
  </div>
</template>
