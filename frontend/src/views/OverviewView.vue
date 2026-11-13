<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, errorMessage } from '@/api/client'
import { useCatalogStore } from '@/stores/catalog'
import { fmtDate, fmtDateTime, fmtInt, fmtPct, relative, SOURCE_LABEL } from '@/utils/format'
import KpiCard from '@/components/KpiCard.vue'
import StateBlock from '@/components/StateBlock.vue'
import PeriodSelect from '@/components/PeriodSelect.vue'
import RunStatusTag from '@/components/RunStatusTag.vue'
import GrowthCell from '@/components/GrowthCell.vue'
import CollectButtons from '@/components/CollectButtons.vue'

const router = useRouter()
const catalog = useCatalogStore()
const summary = ref(null)
const summaryError = ref('')
const loadingSummary = ref(true)

const table = reactive({ items: [], total: 0, loading: false, error: '', period: null })
const query = reactive({ page: 1, size: 10, search: '', sort: 'name', order: 'asc', active: true, stale_only: false })
const activeOptions = [
  { label: 'Ativas', value: true },
  { label: 'Inativas', value: false },
  { label: 'Todas', value: null },
]

async function loadSummary() {
  loadingSummary.value = true
  summaryError.value = ''
  try {
    summary.value = (await api.get('/dashboard/overview', { params: { days: 7 } })).data
  } catch (e) {
    summaryError.value = errorMessage(e)
  } finally {
    loadingSummary.value = false
  }
}

async function loadTable() {
  table.loading = true
  table.error = ''
  try {
    const params = { ...query, days: catalog.periodDays }
    if (params.active === null) delete params.active
    if (!params.search) delete params.search
    const { data } = await api.get('/dashboard/companies', { params })
    Object.assign(table, { items: data.items, total: data.total, period: data.period })
  } catch (e) {
    table.error = errorMessage(e)
  } finally {
    table.loading = false
  }
}

let searchTimer
watch(() => query.search, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { query.page = 1; loadTable() }, 350)
})
watch(() => [query.active, query.stale_only, catalog.periodDays], () => { query.page = 1; loadTable() })

function onPage(e) {
  query.page = e.page + 1
  query.size = e.rows
  loadTable()
}
function onSort(e) {
  query.sort = e.sortField || 'name'
  query.order = e.sortOrder === -1 ? 'desc' : 'asc'
  loadTable()
}
function runsOk(source) {
  return summary.value?.runs?.[source]?.success || 0
}
function runsBad(source) {
  const r = summary.value?.runs?.[source] || {}
  return (r.failed || 0) + (r.abandoned || 0)
}
function lastCollection(row) {
  const dates = [row.inventory_last_success_at, row.instagram_last_success_at].filter(Boolean).sort()
  return dates.length ? dates[dates.length - 1] : null
}

onMounted(() => { loadSummary(); loadTable() })
</script>

<template>
  <StateBlock :loading="loadingSummary" :error="summaryError" @retry="loadSummary">
    <div v-if="summary" class="grid kpis">
      <KpiCard label="Empresas monitoradas" icon="pi pi-building" :value="fmtInt(summary.companies.active)"
               :hint="`${summary.companies.total} cadastradas`" />
      <KpiCard label="Coletas de estoque (7 dias)" icon="pi pi-car" :value="`${runsOk('inventory')} ok`"
               :tone="runsBad('inventory') ? 'warn' : 'default'" :hint="`${runsBad('inventory')} com falha`" />
      <KpiCard label="Coletas do Instagram (7 dias)" icon="pi pi-instagram" :value="`${runsOk('instagram')} ok`"
               :tone="runsBad('instagram') ? 'warn' : 'default'" :hint="`${runsBad('instagram')} com falha`" />
      <KpiCard label="Veículos ativos observados" icon="pi pi-list" :value="fmtInt(summary.vehicles.active)"
               :hint="`${fmtInt(summary.vehicles.observed_total)} anúncios já observados`" />
      <KpiCard label="Perfis do Instagram" icon="pi pi-users" :value="`${summary.instagram.profiles_with_data}/${summary.instagram.profiles}`"
               hint="com ao menos uma coleta válida" />
    </div>
    <div v-if="summary?.recent_failures?.length" class="panel">
      <h2><i class="pi pi-exclamation-triangle" style="color: #b45309" /> Falhas recentes</h2>
      <div v-for="f in summary.recent_failures.slice(0, 5)" :key="f.id" class="row small" style="padding: 4px 0">
        <RunStatusTag :status="f.status" />
        <RouterLink :to="`/empresas/${f.company_id}/coletas`">{{ f.company }}</RouterLink>
        <span class="muted">{{ SOURCE_LABEL[f.source] }} · {{ fmtDateTime(f.created_at) }}</span>
        <span>{{ f.error_summary }}</span>
      </div>
    </div>
  </StateBlock>

  <div class="panel">
    <div class="panel-head">
      <h2><i class="pi pi-table" /> Empresas</h2>
      <div class="toolbar">
        <PeriodSelect v-model="catalog.periodDays" />
      </div>
    </div>
    <div class="toolbar" style="margin-bottom: 10px">
      <IconField>
        <InputIcon class="pi pi-search" />
        <InputText v-model="query.search" placeholder="Buscar por nome, perfil ou cidade" />
      </IconField>
      <Select v-model="query.active" :options="activeOptions" option-label="label" option-value="value" />
      <div class="row small"><ToggleSwitch v-model="query.stale_only" input-id="stale" /><label for="stale">Somente desatualizadas</label></div>
      <span class="spacer" />
      <span v-if="table.period" class="period-note"><i class="pi pi-calendar" />
        Período: {{ fmtDate(table.period.start) }} a {{ fmtDate(table.period.end) }}</span>
    </div>
    <StateBlock :error="table.error" @retry="loadTable">
      <DataTable :value="table.items" lazy paginator :rows="query.size" :total-records="table.total"
                 :first="(query.page - 1) * query.size" :loading="table.loading" :rows-per-page-options="[10, 25, 50]"
                 :sort-field="query.sort" :sort-order="query.order === 'asc' ? 1 : -1" data-key="id"
                 scrollable size="small" @page="onPage" @sort="onSort">
        <template #empty>
          <div class="muted">Nenhuma empresa encontrada. <RouterLink to="/empresas">Cadastre uma empresa</RouterLink>.</div>
        </template>
        <Column field="name" header="Empresa" sortable style="min-width: 180px">
          <template #body="{ data }">
            <RouterLink :to="`/empresas/${data.id}`"><strong>{{ data.name }}</strong></RouterLink>
            <div class="muted small">{{ [data.city, data.state].filter(Boolean).join(' / ') }}</div>
            <Tag v-if="data.is_demo" value="DEMO" severity="contrast" />
          </template>
        </Column>
        <Column header="Instagram">
          <template #body="{ data }">
            <a v-if="data.instagram_username" :href="`https://www.instagram.com/${data.instagram_username}/`" target="_blank" rel="noopener">@{{ data.instagram_username }}</a>
            <span v-else class="muted small">não cadastrado</span>
          </template>
        </Column>
        <Column field="followers" header="Seguidores" sortable class="right">
          <template #body="{ data }">
            <span v-if="data.followers !== null && data.followers !== undefined">{{ fmtInt(data.followers) }}</span>
            <span v-else class="muted small">sem dado</span>
            <div v-if="data.followers_at" class="muted small">{{ fmtDate(data.followers_at) }}</div>
          </template>
        </Column>
        <Column field="growth" header="Crescimento" sortable>
          <template #body="{ data }"><GrowthCell :growth="data.growth" compact /></template>
        </Column>
        <Column field="posts" header="Publicações" sortable class="right">
          <template #body="{ data }">
            <span v-if="data.posts_in_period !== null && data.posts_in_period !== undefined">
              {{ data.posts_partial_sample ? '≥ ' : '' }}{{ fmtInt(data.posts_in_period) }}
            </span>
            <span v-else class="muted small">sem dado</span>
          </template>
        </Column>
        <Column field="interaction" header="Interação est. (mediana)" sortable class="right">
          <template #body="{ data }">
            <span v-if="data.interaction_median !== null && data.interaction_median !== undefined"
                  v-tooltip.top="'(curtidas + comentários) / seguidores × 100'">{{ fmtPct(data.interaction_median) }}</span>
            <span v-else class="muted small">sem dado</span>
            <div v-if="data.interaction_n" class="muted small">n = {{ data.interaction_n }}</div>
          </template>
        </Column>
        <Column field="vehicles" header="Veículos" sortable class="right">
          <template #body="{ data }">{{ data.vehicles_active ?? '—' }}</template>
        </Column>
        <Column field="last_collection" header="Última coleta" sortable>
          <template #body="{ data }">
            <span class="nowrap">{{ relative(lastCollection(data)) }}</span>
            <div class="row" style="gap: 4px; margin-top: 2px">
              <RunStatusTag v-if="data.last_runs.inventory" :status="data.last_runs.inventory.status" v-tooltip.top="'Estoque'" />
              <RunStatusTag v-if="data.last_runs.instagram" :status="data.last_runs.instagram.status" v-tooltip.top="'Instagram'" />
            </div>
          </template>
        </Column>
        <Column header="Status">
          <template #body="{ data }">
            <div class="stack" style="gap: 4px">
              <Tag :value="data.active ? 'Ativa' : 'Inativa'" :severity="data.active ? 'success' : 'secondary'" />
              <Tag v-if="data.stale.length" :value="`Desatualizada: ${data.stale.join(', ')}`" severity="warn" />
            </div>
          </template>
        </Column>
        <Column header="Ações" style="min-width: 150px">
          <template #body="{ data }">
            <div class="row" style="gap: 2px">
              <Button icon="pi pi-chart-line" text rounded v-tooltip.top="'Abrir dashboard'" @click="router.push(`/empresas/${data.id}`)" />
              <CollectButtons :company="data" compact @queued="loadTable" />
            </div>
          </template>
        </Column>
      </DataTable>
    </StateBlock>
    <p class="muted small" style="margin: 8px 0 0">
      "≥" indica amostra parcial de publicações. Crescimento usa datas reais de coletas; sem duas coletas no período,
      exibe "histórico insuficiente". Dados desatualizados: última coleta bem-sucedida há mais de 2× a frequência configurada.
    </p>
  </div>
</template>
