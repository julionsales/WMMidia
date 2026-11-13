<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api, download, errorMessage } from '@/api/client'
import {
  ERROR_LABEL, FORMAT_LABEL, fmtDate, fmtDateTime, fmtInt, fmtNum, fmtPct, relative, truncate,
} from '@/utils/format'
import StateBlock from '@/components/StateBlock.vue'
import KpiCard from '@/components/KpiCard.vue'
import EChart from '@/components/EChart.vue'
import GrowthCell from '@/components/GrowthCell.vue'
import ManualSnapshotDialog from '@/components/ManualSnapshotDialog.vue'
import LinkVehicleDialog from '@/components/LinkVehicleDialog.vue'

const props = defineProps({ companyId: { type: String, required: true }, days: { type: Number, default: 30 }, username: { type: String, default: '' } })
const data = ref(null)
const loading = ref(true)
const error = ref('')
const posts = reactive({ items: [], total: 0, page: 1, size: 10, sort: 'taken_at', loading: false, error: '' })
const manualOpen = ref(false)
const linkPost = ref(null)

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = (await api.get(`/instagram/companies/${props.companyId}/dashboard`, { params: { days: props.days } })).data
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
  loadPosts()
}

async function loadPosts() {
  posts.loading = true
  posts.error = ''
  try {
    const { data: page } = await api.get(`/instagram/companies/${props.companyId}/posts`, {
      params: { days: props.days, page: posts.page, size: posts.size, sort: posts.sort },
    })
    posts.items = page.items
    posts.total = page.total
  } catch (e) {
    posts.error = errorMessage(e)
  } finally {
    posts.loading = false
  }
}

watch(() => props.days, () => { posts.page = 1; load() })
onMounted(load)

const summary = computed(() => data.value?.posts_summary || {})
const followersOption = computed(() => ({
  tooltip: { trigger: 'axis', valueFormatter: (v) => fmtInt(v) },
  grid: { left: 60, right: 20, top: 20, bottom: 40 },
  xAxis: { type: 'time' },
  yAxis: { type: 'value', scale: true, axisLabel: { formatter: (v) => fmtInt(v) } },
  series: [{
    name: 'Seguidores', type: 'line', showSymbol: true, symbolSize: 7, connectNulls: false,
    data: (data.value?.series || []).map((p) => [p.date, p.followers]),
    lineStyle: { color: '#0f766e' }, itemStyle: { color: '#0f766e' },
  }],
}))
const weeklyOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 20, top: 20, bottom: 40 },
  xAxis: { type: 'category', data: (data.value?.posts_by_week || []).map((w) => `sem. ${fmtDate(w.week_start).slice(0, 5)}`) },
  yAxis: { type: 'value', minInterval: 1 },
  series: [{ name: 'Publicações', type: 'bar', data: (data.value?.posts_by_week || []).map((w) => w.count), itemStyle: { color: '#14b8a6' } }],
}))
const formatOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [{
    type: 'pie', radius: ['40%', '68%'], center: ['50%', '45%'],
    data: (summary.value.formats || []).map((f) => ({ name: FORMAT_LABEL[f.format] || f.format, value: f.count })),
  }],
}))

function onPage(e) { posts.page = e.page + 1; posts.size = e.rows; loadPosts() }
function exportPosts(fmt) { download(`/exports/companies/${props.companyId}/instagram-posts.${fmt}`, { days: props.days }) }
</script>

<template>
  <div class="stack" style="gap: 16px">
    <div class="toolbar">
      <span v-if="data?.period" class="period-note"><i class="pi pi-calendar" /> {{ fmtDate(data.period.start) }} a {{ fmtDate(data.period.end) }}</span>
      <span class="spacer" />
      <Button label="Snapshot manual" icon="pi pi-plus" size="small" outlined :disabled="!username" @click="manualOpen = true" />
      <Button label="CSV" icon="pi pi-download" size="small" text @click="exportPosts('csv')" />
      <Button label="Excel" icon="pi pi-file-excel" size="small" text @click="exportPosts('xlsx')" />
    </div>
    <StateBlock :loading="loading" :error="error" @retry="load"
                :empty="data && ['sem_perfil', 'sem_dados'].includes(data.status)" :empty-text="data?.message">
      <template v-if="data">
        <div class="row small muted">
          <span>Última coleta bem-sucedida: <strong>{{ fmtDateTime(data.last_success_at) }}</strong> ({{ relative(data.last_success_at) }})</span>
          <span v-if="data.last_attempt?.status && data.last_attempt.status !== 'success'">
            · Última tentativa: {{ fmtDateTime(data.last_attempt.at) }} —
            <Tag :value="ERROR_LABEL[data.last_attempt.error_code] || data.last_attempt.status" severity="warn" />
          </span>
          <span>· Monitorado desde {{ fmtDate(data.profile?.monitoring_started_at) }}</span>
        </div>
        <div v-for="(w, i) in data.warnings" :key="i" class="notice"><i class="pi pi-exclamation-circle" /> {{ w }}</div>

        <div class="grid kpis">
          <KpiCard label="Seguidores" icon="pi pi-users" :value="fmtInt(data.latest?.followers)"
                   :hint="data.latest?.collected_at ? `em ${fmtDateTime(data.latest.collected_at)} (${data.latest.source})` : ''" />
          <KpiCard label="Crescimento" icon="pi pi-chart-line" :value="data.growth?.status === 'ok' ? fmtPct(data.growth.percent) : '—'">
            <GrowthCell :growth="data.growth" />
          </KpiCard>
          <KpiCard label="Publicações no período" icon="pi pi-images"
                   :value="`${summary.count_is_lower_bound ? '≥ ' : ''}${fmtInt(summary.count)}`"
                   :hint="`${fmtNum(summary.per_week)} por semana${summary.count_is_lower_bound ? ' (amostra parcial)' : ''}`" />
          <KpiCard label="Curtidas (média / mediana)" icon="pi pi-heart"
                   :value="`${fmtNum(summary.likes?.mean, 0)} / ${fmtNum(summary.likes?.median, 0)}`" :hint="`n = ${summary.likes?.n ?? 0}`" />
          <KpiCard label="Comentários (média / mediana)" icon="pi pi-comments"
                   :value="`${fmtNum(summary.comments?.mean, 1)} / ${fmtNum(summary.comments?.median, 1)}`" :hint="`n = ${summary.comments?.n ?? 0}`" />
          <KpiCard label="Interação pública est. (mediana)" icon="pi pi-percentage"
                   :value="fmtPct(summary.interaction?.median, 3)" :hint="`média ${fmtPct(summary.interaction?.mean, 3)} · n = ${summary.interaction?.n ?? 0}`" />
        </div>

        <div class="grid two">
          <div class="panel">
            <h3>Evolução dos seguidores (somente coletas reais)</h3>
            <StateBlock :empty="!data.series?.length" empty-text="Nenhuma coleta válida ainda.">
              <EChart :option="followersOption" />
              <p v-if="data.series.length < 2" class="muted small">Histórico insuficiente: o gráfico ganha forma a partir da segunda coleta.</p>
            </StateBlock>
          </div>
          <div class="panel">
            <h3>Publicações por semana</h3>
            <StateBlock :empty="!data.posts_by_week?.length" empty-text="Nenhuma publicação coletada no período.">
              <EChart :option="weeklyOption" />
            </StateBlock>
          </div>
          <div class="panel">
            <h3>Formatos publicados</h3>
            <StateBlock :empty="!summary.formats?.length" empty-text="Sem publicações no período.">
              <EChart :option="formatOption" height="260px" />
            </StateBlock>
          </div>
          <div class="panel">
            <h3>Interação estimada por formato</h3>
            <StateBlock :empty="!data.format_performance?.length" empty-text="Sem métricas visíveis no período.">
              <DataTable :value="data.format_performance" size="small">
                <Column header="Formato"><template #body="{ data: r }">{{ FORMAT_LABEL[r.format] || r.format }}</template></Column>
                <Column header="Mediana" class="right"><template #body="{ data: r }">{{ fmtPct(r.median, 3) }}</template></Column>
                <Column header="Média" class="right"><template #body="{ data: r }">{{ fmtPct(r.mean, 3) }}</template></Column>
                <Column header="n" field="n" class="right" />
              </DataTable>
              <p class="muted small">Amostras pequenas não permitem conclusões; use como hipótese.</p>
            </StateBlock>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <h3 style="margin: 0">Publicações do período</h3>
            <SelectButton v-model="posts.sort" :options="[{ l: 'Mais recentes', v: 'taken_at' }, { l: 'Mais interações', v: 'interactions' }]"
                          option-label="l" option-value="v" :allow-empty="false" @change="posts.page = 1; loadPosts()" />
          </div>
          <StateBlock :error="posts.error" @retry="loadPosts">
            <DataTable :value="posts.items" lazy paginator :rows="posts.size" :total-records="posts.total" :loading="posts.loading"
                       :first="(posts.page - 1) * posts.size" :rows-per-page-options="[10, 25, 50]" size="small" scrollable @page="onPage">
              <template #empty><span class="muted">Nenhuma publicação coletada neste período.</span></template>
              <Column header="Data"><template #body="{ data: p }"><span class="nowrap">{{ fmtDateTime(p.taken_at) }}</span>
                <Tag v-if="p.is_pinned" value="fixada" severity="secondary" /></template></Column>
              <Column header="Formato"><template #body="{ data: p }">{{ FORMAT_LABEL[p.format] || p.format }}</template></Column>
              <Column header="Legenda" style="min-width: 220px"><template #body="{ data: p }"><span class="small">{{ truncate(p.caption, 110) || '—' }}</span></template></Column>
              <Column header="Curtidas" class="right"><template #body="{ data: p }">
                <span v-if="p.likes != null">{{ fmtInt(p.likes) }}</span><span v-else class="muted small" v-tooltip.top="'Oculto ou indisponível'">indisponível</span></template></Column>
              <Column header="Comentários" class="right"><template #body="{ data: p }">
                <span v-if="p.comments != null">{{ fmtInt(p.comments) }}</span><span v-else class="muted small">indisponível</span></template></Column>
              <Column header="Interação est." class="right"><template #body="{ data: p }">
                <span v-if="p.interaction?.value != null"
                      v-tooltip.top="`${fmtInt(p.interaction.followers)} seguidores (${p.interaction.basis === 'snapshot_proximo' ? 'snapshot próximo à publicação' : 'seguidores da coleta'}, ${fmtDate(p.interaction.date)})`">
                  {{ fmtPct(p.interaction.value, 3) }}</span>
                <span v-else class="muted small">não calculada</span></template></Column>
              <Column header="Veículo associado"><template #body="{ data: p }">
                <div v-for="l in p.vehicle_links" :key="l.id" class="small">{{ l.vehicle_title }}</div>
                <Button label="Associar" icon="pi pi-link" text size="small" @click="linkPost = p" /></template></Column>
              <Column header="Link"><template #body="{ data: p }"><a :href="p.url" target="_blank" rel="noopener"><i class="pi pi-external-link" /></a></template></Column>
            </DataTable>
          </StateBlock>
        </div>

        <div class="notice info small">
          <i class="pi pi-info-circle" />
          <div>
            <strong>{{ data.formula?.name }}</strong>: {{ data.formula?.expression }}. {{ data.formula?.followers_rule }}
            {{ data.formula?.disclaimer }} Publicações sem curtidas ou comentários visíveis ficam fora do cálculo.
          </div>
        </div>
      </template>
    </StateBlock>
    <ManualSnapshotDialog v-model:visible="manualOpen" :company-id="companyId" @saved="load" />
    <LinkVehicleDialog :post="linkPost" :company-id="companyId" @close="linkPost = null" @saved="loadPosts" />
  </div>
</template>
