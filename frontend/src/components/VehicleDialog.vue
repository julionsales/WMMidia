<script setup>
import { computed, ref, watch } from 'vue'
import { api, errorMessage } from '@/api/client'
import { fmtBRL, fmtDate, fmtDateTime, fmtInt, VEHICLE_STATUS } from '@/utils/format'
import EChart from '@/components/EChart.vue'
import StateBlock from '@/components/StateBlock.vue'

const props = defineProps({ vehicleId: { type: String, default: '' } })
const emit = defineEmits(['close'])
const data = ref(null)
const loading = ref(false)
const error = ref('')
const visible = computed({ get: () => Boolean(props.vehicleId), set: (v) => { if (!v) emit('close') } })
const KIND = { novo: 'Primeira observação', presente: 'Presente', reapareceu: 'Reapareceu', nao_encontrado: 'Não encontrado' }

async function load() {
  if (!props.vehicleId) return
  loading.value = true
  error.value = ''
  try {
    data.value = (await api.get(`/inventory/vehicles/${props.vehicleId}`)).data
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}
watch(() => props.vehicleId, load)

const option = computed(() => {
  const points = (data.value?.price_history || []).filter((p) => p.price != null)
  const last = data.value?.vehicle?.last_seen_at
  const series = points.map((p) => [p.date, p.price])
  if (series.length && last) series.push([last, series[series.length - 1][1]])
  return {
    tooltip: { trigger: 'axis', valueFormatter: (v) => fmtBRL(v) },
    grid: { left: 80, right: 20, top: 20, bottom: 40 },
    xAxis: { type: 'time' },
    yAxis: { type: 'value', scale: true, axisLabel: { formatter: (v) => fmtBRL(v) } },
    series: [{ type: 'line', step: 'end', data: series, itemStyle: { color: '#0f766e' } }],
  }
})
</script>

<template>
  <Dialog v-model:visible="visible" modal header="Histórico do anúncio" :style="{ width: '760px' }" :breakpoints="{ '800px': '96vw' }">
    <StateBlock :loading="loading" :error="error" @retry="load">
      <template v-if="data">
        <h3 style="margin-top: 0">{{ data.vehicle.brand_display }} {{ data.vehicle.model }} <span class="muted">{{ data.vehicle.version }}</span></h3>
        <div class="row small" style="margin-bottom: 10px">
          <Tag :value="VEHICLE_STATUS[data.vehicle.status]?.label" :severity="VEHICLE_STATUS[data.vehicle.status]?.severity" />
          <span>{{ data.vehicle.company_name }}</span>
          <span>· Ano {{ data.vehicle.year_model || '—' }} · {{ data.vehicle.km != null ? `${fmtInt(data.vehicle.km)} km` : 'km não informado' }}</span>
          <span>· Preço atual: <strong>{{ fmtBRL(data.vehicle.price, data.vehicle.price_on_request) }}</strong></span>
          <a v-if="data.vehicle.url" :href="data.vehicle.url" target="_blank" rel="noopener">abrir anúncio</a>
        </div>
        <div class="row small muted">
          Primeira observação {{ fmtDateTime(data.vehicle.first_seen_at) }} · última {{ fmtDateTime(data.vehicle.last_seen_at) }}
          · {{ data.vehicle.observed_days }} dia(s) observado · chave {{ data.vehicle.key_type === 'source_id' ? 'ID da origem' : data.vehicle.key_type === 'url' ? 'URL do anúncio' : 'atributos (menos estável)' }}
        </div>
        <h3>Preço observado</h3>
        <EChart v-if="data.price_history.some((p) => p.price != null)" :option="option" height="240px" />
        <p v-else class="muted small">Preço sob consulta ou não informado em todas as coletas.</p>
        <h3>Presença nas coletas ({{ data.observations_count }})</h3>
        <DataTable :value="[...data.presence].reverse()" size="small" scrollable scroll-height="220px">
          <Column header="Data"><template #body="{ data: o }">{{ fmtDateTime(o.date) }}</template></Column>
          <Column header="Situação"><template #body="{ data: o }">{{ KIND[o.kind] || o.kind }}</template></Column>
        </DataTable>
        <p v-for="n in data.notes" :key="n" class="muted small" style="margin: 6px 0 0">{{ n }}</p>
        <div v-if="data.linked_posts?.length" class="small" style="margin-top: 10px">
          <strong>Publicações associadas manualmente:</strong>
          <div v-for="l in data.linked_posts" :key="l.id"><a :href="l.post_url" target="_blank" rel="noopener">{{ l.post_url }}</a> — {{ fmtDate(l.created_at) }}</div>
        </div>
      </template>
    </StateBlock>
  </Dialog>
</template>
