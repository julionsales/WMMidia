<script setup>
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { api, errorMessage } from '@/api/client'
import { useCatalogStore } from '@/stores/catalog'
import { ERROR_LABEL, fmtDateTime, relative, RUN_STATUS, SOURCE_LABEL } from '@/utils/format'
import StateBlock from '@/components/StateBlock.vue'
import RunStatusTag from '@/components/RunStatusTag.vue'

const props = defineProps({ companyId: { type: String, default: '' } })
const catalog = useCatalogStore()
const state = reactive({ items: [], total: 0, schedule: [], loading: false, error: '' })
const filters = reactive({ company_id: props.companyId || null, source: null, status: null, partial: null })
const paging = reactive({ page: 1, size: 25 })
const detail = ref(null)
const sourceOptions = [{ label: 'Estoque', value: 'inventory' }, { label: 'Instagram', value: 'instagram' }]
const statusOptions = Object.entries(RUN_STATUS).map(([value, meta]) => ({ value, label: meta.label }))
let timer

async function load(silent = false) {
  if (!silent) state.loading = true
  state.error = ''
  try {
    const params = { ...filters, ...paging }
    Object.keys(params).forEach((k) => { if (params[k] === null || params[k] === '') delete params[k] })
    const { data } = await api.get('/runs', { params })
    Object.assign(state, { items: data.items, total: data.total, schedule: data.schedule })
  } catch (e) {
    state.error = errorMessage(e)
  } finally {
    state.loading = false
  }
}

function onPage(e) { paging.page = e.page + 1; paging.size = e.rows; load() }
function applyFilters() { paging.page = 1; load() }

onMounted(() => {
  if (!props.companyId) catalog.loadCompanies()
  load()
  // Atualiza enquanto houver execuções ativas.
  timer = setInterval(() => {
    if (state.items.some((r) => ['queued', 'running', 'retrying'].includes(r.status))) load(true)
  }, 5000)
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <div class="stack" style="gap: 14px">
    <div class="toolbar">
      <Select v-if="!companyId" v-model="filters.company_id" :options="catalog.companies" option-label="name" option-value="id"
              placeholder="Todas as empresas" show-clear filter @change="applyFilters" />
      <Select v-model="filters.source" :options="sourceOptions" option-label="label" option-value="value" placeholder="Fonte" show-clear @change="applyFilters" />
      <Select v-model="filters.status" :options="statusOptions" option-label="label" option-value="value" placeholder="Status" show-clear @change="applyFilters" />
      <Select v-model="filters.partial" :options="[{ l: 'Somente parciais', v: true }, { l: 'Somente completas', v: false }]"
              option-label="l" option-value="v" placeholder="Resultado" show-clear @change="applyFilters" />
      <span class="spacer" />
      <Button icon="pi pi-refresh" text v-tooltip.top="'Atualizar'" @click="load()" />
    </div>
    <StateBlock :error="state.error" @retry="load">
      <DataTable :value="state.items" lazy paginator :rows="paging.size" :total-records="state.total" :loading="state.loading"
                 :first="(paging.page - 1) * paging.size" :rows-per-page-options="[25, 50, 100]" size="small" scrollable data-key="id"
                 selection-mode="single" @row-select="detail = $event.data">
        <template #empty><span class="muted">Nenhuma execução registrada.</span></template>
        <Column v-if="!companyId" header="Empresa" field="company_name" />
        <Column header="Fonte"><template #body="{ data }">{{ SOURCE_LABEL[data.source] }}</template></Column>
        <Column header="Execução"><template #body="{ data }"><span class="mono" v-tooltip.top="data.id">…{{ data.id.slice(-8) }}</span>
          <div class="muted small">{{ data.trigger }}{{ data.requested_by && data.trigger === 'manual' ? ` · ${data.requested_by}` : '' }}</div></template></Column>
        <Column header="Início"><template #body="{ data }"><span class="nowrap small">{{ fmtDateTime(data.started_at || data.created_at) }}</span></template></Column>
        <Column header="Término"><template #body="{ data }"><span class="nowrap small">{{ fmtDateTime(data.finished_at) }}</span>
          <div v-if="data.duration_seconds != null" class="muted small">{{ data.duration_seconds }} s</div></template></Column>
        <Column header="Status"><template #body="{ data }"><RunStatusTag :status="data.status" />
          <div v-if="data.attempts > 1" class="muted small">{{ data.attempts }} tentativas</div></template></Column>
        <Column header="Registros" field="records" class="right" />
        <Column header="Parcial"><template #body="{ data }"><Tag v-if="data.partial" value="Parcial" severity="warn" /><span v-else class="muted small">não</span></template></Column>
        <Column header="Mensagem" style="min-width: 240px"><template #body="{ data }">
          <span v-if="data.error_code" class="small"><strong>{{ ERROR_LABEL[data.error_code] || data.error_code }}</strong>. </span>
          <span class="small">{{ data.error_summary || data.last_error || '' }}</span>
          <div v-if="data.next_attempt_at" class="muted small">Nova tentativa {{ relative(data.next_attempt_at) }}</div></template></Column>
      </DataTable>
    </StateBlock>
    <div class="panel">
      <h3>Próximas coletas programadas</h3>
      <StateBlock :empty="!state.schedule.length" empty-text="Nenhuma coleta agendada (frequência 0 ou empresas inativas).">
        <DataTable :value="state.schedule" size="small">
          <Column v-if="!companyId" header="Empresa" field="company_name" />
          <Column header="Fonte"><template #body="{ data }">{{ SOURCE_LABEL[data.source] }}</template></Column>
          <Column header="Próxima"><template #body="{ data }">{{ fmtDateTime(data.next_at) }} <span class="muted small">({{ relative(data.next_at) }})</span></template></Column>
          <Column header="Frequência"><template #body="{ data }">a cada {{ data.frequency_hours }} h</template></Column>
        </DataTable>
        <p class="muted small" style="margin: 6px 0 0">Calculada a partir da última execução. O agendador verifica a cada minuto e não duplica execuções.</p>
      </StateBlock>
    </div>
    <Dialog :visible="Boolean(detail)" modal header="Detalhes da execução" :style="{ width: '640px' }" :breakpoints="{ '700px': '96vw' }"
            @update:visible="(v) => { if (!v) detail = null }">
      <template v-if="detail">
        <div class="stack small">
          <div><strong>ID:</strong> <span class="mono">{{ detail.id }}</span></div>
          <div><strong>Empresa:</strong> {{ detail.company_name }} · <strong>Fonte:</strong> {{ SOURCE_LABEL[detail.source] }}</div>
          <div><strong>Status:</strong> <RunStatusTag :status="detail.status" /> {{ detail.partial ? '(parcial)' : '' }}</div>
          <div><strong>Criada:</strong> {{ fmtDateTime(detail.created_at) }} · <strong>Término:</strong> {{ fmtDateTime(detail.finished_at) }}</div>
          <div v-if="detail.error_summary"><strong>Mensagem:</strong> {{ detail.error_summary }}</div>
          <template v-if="detail.details && Object.keys(detail.details).length">
            <strong>Resumo técnico</strong>
            <pre class="mono" style="background: #f6f8fa; padding: 10px; border-radius: 6px; overflow: auto; max-height: 260px">{{ JSON.stringify(detail.details, null, 2) }}</pre>
          </template>
          <p class="muted">Detalhes técnicos completos ficam nos logs do servidor (sem segredos): <code>docker compose logs worker</code>.</p>
        </div>
      </template>
    </Dialog>
  </div>
</template>
