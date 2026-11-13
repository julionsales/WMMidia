<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import Tabs from 'primevue/tabs'
import TabList from 'primevue/tablist'
import Tab from 'primevue/tab'
import TabPanels from 'primevue/tabpanels'
import TabPanel from 'primevue/tabpanel'
import { api, errorMessage } from '@/api/client'
import { useCatalogStore } from '@/stores/catalog'
import { fmtDate, fmtDateTime, fmtInt, fmtPct, relative, SOURCE_LABEL } from '@/utils/format'
import StateBlock from '@/components/StateBlock.vue'
import KpiCard from '@/components/KpiCard.vue'
import PeriodSelect from '@/components/PeriodSelect.vue'
import GrowthCell from '@/components/GrowthCell.vue'
import RunStatusTag from '@/components/RunStatusTag.vue'
import CollectButtons from '@/components/CollectButtons.vue'
import CompanyFormDialog from '@/components/CompanyFormDialog.vue'
import InstagramPanel from '@/components/InstagramPanel.vue'
import InventoryPanel from '@/components/InventoryPanel.vue'
import ComparePanel from '@/components/ComparePanel.vue'
import BriefingPanel from '@/components/BriefingPanel.vue'
import RunsTable from '@/components/RunsTable.vue'

const props = defineProps({ id: { type: String, required: true }, tab: { type: String, default: 'resumo' } })
const router = useRouter()
const catalog = useCatalogStore()
const company = ref(null)
const loading = ref(true)
const error = ref('')
const editOpen = ref(false)
const TABS = ['resumo', 'instagram', 'estoque', 'comparativo', 'briefing', 'coletas']
const current = computed({
  get: () => (TABS.includes(props.tab) ? props.tab : 'resumo'),
  set: (value) => router.replace(`/empresas/${props.id}/${value}`),
})
const overview = computed(() => company.value?.overview || {})
const compareIds = computed(() => [props.id, ...(company.value?.competitor_ids || [])])

async function load() {
  loading.value = true
  error.value = ''
  try {
    company.value = (await api.get(`/companies/${props.id}`, { params: { days: catalog.periodDays } })).data
  } catch (e) {
    error.value = e.response?.status === 404 ? 'Empresa não encontrada.' : errorMessage(e)
  } finally {
    loading.value = false
  }
}
watch(() => catalog.periodDays, load)
onMounted(load)
</script>

<template>
  <StateBlock :loading="loading && !company" :error="error" @retry="load">
    <template v-if="company">
      <div class="panel">
        <div class="panel-head">
          <div>
            <h2 style="font-size: 1.25rem">{{ company.name }}
              <Tag v-if="company.is_demo" value="DEMO — dados fictícios" severity="contrast" />
              <Tag :value="company.active ? 'Ativa' : 'Inativa'" :severity="company.active ? 'success' : 'secondary'" />
            </h2>
            <div class="muted small">
              {{ company.segment || 'Segmento não informado' }} · {{ [company.city, company.state].filter(Boolean).join(' / ') || 'Local não informado' }}
              <template v-if="company.website"> · <a :href="company.website" target="_blank" rel="noopener">site</a></template>
              <template v-if="company.instagram_username"> · <a :href="`https://www.instagram.com/${company.instagram_username}/`" target="_blank" rel="noopener">@{{ company.instagram_username }}</a></template>
            </div>
          </div>
          <div class="toolbar">
            <PeriodSelect v-model="catalog.periodDays" />
            <CollectButtons :company="company" @queued="load" />
            <Button label="Editar" icon="pi pi-pencil" outlined size="small" @click="editOpen = true" />
          </div>
        </div>
        <Tabs v-model:value="current" scrollable>
          <TabList>
            <Tab value="resumo">Resumo</Tab>
            <Tab value="instagram">Instagram</Tab>
            <Tab value="estoque">Estoque</Tab>
            <Tab value="comparativo">Comparativo</Tab>
            <Tab value="briefing">Briefing</Tab>
            <Tab value="coletas">Coletas e logs</Tab>
          </TabList>
          <TabPanels style="padding: 16px 0 0">
            <TabPanel value="resumo">
              <div class="stack" style="gap: 16px">
                <div class="grid kpis">
                  <KpiCard label="Seguidores" icon="pi pi-users" :value="overview.followers != null ? fmtInt(overview.followers) : 'sem dado'"
                           :hint="overview.followers_at ? `coleta de ${fmtDateTime(overview.followers_at)}` : 'nenhuma coleta válida'" />
                  <KpiCard label="Crescimento no período" icon="pi pi-chart-line"
                           :value="overview.growth?.status === 'ok' ? fmtPct(overview.growth.percent) : '—'">
                    <GrowthCell :growth="overview.growth" />
                  </KpiCard>
                  <KpiCard label="Publicações no período" icon="pi pi-images"
                           :value="overview.posts_in_period != null ? `${overview.posts_partial_sample ? '≥ ' : ''}${overview.posts_in_period}` : 'sem dado'"
                           :hint="overview.posts_partial_sample ? 'amostra parcial' : ''" />
                  <KpiCard label="Interação pública est. (mediana)" icon="pi pi-heart"
                           :value="overview.interaction_median != null ? fmtPct(overview.interaction_median) : 'sem dado'"
                           :hint="overview.interaction_n ? `n = ${overview.interaction_n} publicações` : ''" />
                  <KpiCard label="Veículos ativos" icon="pi pi-car" :value="overview.vehicles_active ?? 'sem dado'"
                           :hint="overview.inventory_last_success_at ? `coleta ${relative(overview.inventory_last_success_at)}` : 'sem coleta'" />
                </div>
                <div v-if="overview.stale?.length" class="notice"><i class="pi pi-clock" />
                  Dados desatualizados: {{ overview.stale.join(', ') }}. A última coleta bem-sucedida passou de 2× a frequência configurada.
                </div>
                <div class="grid two">
                  <div class="panel">
                    <h3>Coletas</h3>
                    <div v-for="src in ['inventory', 'instagram']" :key="src" class="row small" style="padding: 4px 0">
                      <strong style="width: 90px">{{ SOURCE_LABEL[src] }}</strong>
                      <RunStatusTag :status="overview.last_runs?.[src]?.status" />
                      <span class="muted">{{ overview.last_runs?.[src] ? fmtDateTime(overview.last_runs[src].created_at) : 'nunca executada' }}</span>
                      <span class="muted">· próxima: {{ overview.next_runs?.[src] ? fmtDateTime(overview.next_runs[src]) : 'somente manual' }}</span>
                    </div>
                  </div>
                  <div class="panel">
                    <h3>Concorrentes configurados</h3>
                    <div v-if="company.competitors?.length" class="row">
                      <RouterLink v-for="c in company.competitors" :key="c.id" :to="`/empresas/${c.id}`"><Tag :value="c.name" /></RouterLink>
                    </div>
                    <span v-else class="muted small">Nenhum. Edite a empresa para escolher concorrentes.</span>
                  </div>
                </div>
                <div v-if="company.notes" class="panel"><h3>Observações</h3><p class="small" style="white-space: pre-wrap; margin: 0">{{ company.notes }}</p></div>
                <p class="muted small">Período: {{ fmtDate(company.period.start) }} a {{ fmtDate(company.period.end) }}.</p>
              </div>
            </TabPanel>
            <TabPanel value="instagram">
              <InstagramPanel v-if="current === 'instagram'" :company-id="id" :days="catalog.periodDays" :username="company.instagram_username" />
            </TabPanel>
            <TabPanel value="estoque">
              <InventoryPanel v-if="current === 'estoque'" :company-id="id" :days="catalog.periodDays" />
            </TabPanel>
            <TabPanel value="comparativo">
              <ComparePanel v-if="current === 'comparativo'" :initial-ids="compareIds" :days="catalog.periodDays" />
            </TabPanel>
            <TabPanel value="briefing">
              <BriefingPanel v-if="current === 'briefing'" :company-id="id" />
            </TabPanel>
            <TabPanel value="coletas">
              <RunsTable v-if="current === 'coletas'" :company-id="id" />
            </TabPanel>
          </TabPanels>
        </Tabs>
      </div>
      <CompanyFormDialog v-model:visible="editOpen" :company="company" @saved="load" />
    </template>
  </StateBlock>
</template>
