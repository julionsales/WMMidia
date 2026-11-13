<script setup>
// Exibe um briefing salvo (dados congelados). Fatos e hipóteses ficam visualmente separados.
import { computed } from 'vue'
import { FORMAT_LABEL, fmtBRL, fmtDate, fmtDateTime, fmtInt, fmtNum, fmtPct, truncate } from '@/utils/format'
import GrowthCell from '@/components/GrowthCell.vue'

const props = defineProps({ briefing: { type: Object, required: true } })
const facts = computed(() => props.briefing.facts)
const content = computed(() => props.briefing.content)
const inv = computed(() => facts.value.inventory || {})
const ig = computed(() => facts.value.instagram || {})
const posts = computed(() => ig.value.posts_summary || {})
</script>

<template>
  <div class="stack" style="gap: 14px">
    <div class="row small muted">
      <strong>{{ briefing.title }}</strong> · v{{ briefing.version }} · gerado em {{ fmtDateTime(briefing.created_at) }} por {{ briefing.created_by }}
      · período {{ facts.period.start_label }} a {{ facts.period.end_label }}
    </div>
    <div class="notice info small"><i class="pi pi-lock" /> Conteúdo congelado na geração: novas coletas não alteram esta versão.</div>

    <section class="panel">
      <h2>1. Resumo do estoque <Tag value="fatos observados" severity="success" /></h2>
      <div class="row small">
        <span><strong>{{ fmtInt(inv.active_count) }}</strong> ativos</span>
        <span>· {{ fmtInt(inv.observed_total) }} já observados</span>
        <span>· {{ fmtInt(inv.new_in_period) }} novos no período</span>
        <span>· {{ fmtInt(inv.missing_in_period) }} não encontrados (não indica venda)</span>
      </div>
      <div class="grid two" style="margin-top: 10px">
        <DataTable :value="(inv.by_brand || []).slice(0, 10)" size="small">
          <Column field="brand" header="Marca" /><Column field="count" header="Qtd." class="right" />
        </DataTable>
        <DataTable :value="(inv.by_model || []).slice(0, 10)" size="small">
          <Column header="Modelo"><template #body="{ data }">{{ data.brand }} {{ data.model }}</template></Column>
          <Column field="count" header="Qtd." class="right" /><Column field="content_category" header="Categoria" />
        </DataTable>
      </div>
    </section>

    <section class="panel">
      <h2>2. Anúncios com maior tempo observado e alterações de preço</h2>
      <div class="grid two">
        <DataTable :value="inv.longest_observed || []" size="small">
          <Column header="Veículo"><template #body="{ data }">{{ data.brand }} {{ data.model }}</template></Column>
          <Column header="Desde"><template #body="{ data }">{{ fmtDate(data.first_seen_at) }}</template></Column>
          <Column field="observed_days" header="Dias" class="right" />
        </DataTable>
        <DataTable :value="(inv.price_changes || []).slice(0, 10)" size="small">
          <template #empty><span class="muted small">Nenhuma alteração observada.</span></template>
          <Column header="Veículo"><template #body="{ data }">{{ data.brand }} {{ data.model }}</template></Column>
          <Column header="Antes → depois"><template #body="{ data }">{{ fmtBRL(data.previous_price) }} → {{ fmtBRL(data.price) }}</template></Column>
          <Column header="Data"><template #body="{ data }">{{ fmtDate(data.observed_at) }}</template></Column>
        </DataTable>
      </div>
    </section>

    <section class="panel">
      <h2>3. Instagram <Tag value="fatos observados" severity="success" /></h2>
      <p v-if="['sem_perfil', 'sem_dados'].includes(ig.status)" class="muted">{{ ig.message }}</p>
      <template v-else>
        <div class="row small">
          <span>@{{ ig.username }} · {{ fmtInt(ig.latest?.followers) }} seguidores ({{ fmtDateTime(ig.latest?.collected_at) }})</span>
          <span>· crescimento: <GrowthCell :growth="ig.growth" /></span>
        </div>
        <div class="row small">
          <span>{{ posts.count_is_lower_bound ? '≥ ' : '' }}{{ fmtInt(posts.count) }} publicações ({{ fmtNum(posts.per_week) }}/semana)</span>
          <span>· interação est. mediana {{ fmtPct(posts.interaction?.median, 3) }} (n={{ posts.interaction?.n ?? 0 }})</span>
        </div>
        <div v-for="w in ig.warnings" :key="w" class="notice small" style="margin-top: 6px"><i class="pi pi-exclamation-circle" /> {{ w }}</div>
        <h3 style="margin-top: 12px">Publicações com maior interação visível</h3>
        <DataTable :value="ig.top_posts || []" size="small">
          <template #empty><span class="muted small">Sem publicações com métricas visíveis.</span></template>
          <Column header="Data"><template #body="{ data }">{{ fmtDate(data.taken_at) }}</template></Column>
          <Column header="Formato"><template #body="{ data }">{{ FORMAT_LABEL[data.format] || data.format }}</template></Column>
          <Column header="Legenda"><template #body="{ data }"><span class="small">{{ truncate(data.caption, 80) }}</span></template></Column>
          <Column header="Interações" class="right"><template #body="{ data }">{{ fmtInt(data.visible_interactions) }}</template></Column>
          <Column header="Link"><template #body="{ data }"><a :href="data.url" target="_blank" rel="noopener"><i class="pi pi-external-link" /></a></template></Column>
        </DataTable>
      </template>
    </section>

    <section v-if="(facts.comparison?.rows || []).length > 1" class="panel">
      <h2>4. Comparação com concorrentes</h2>
      <DataTable :value="facts.comparison.rows" size="small" scrollable>
        <Column field="name" header="Empresa" />
        <Column header="Seguidores" class="right"><template #body="{ data }">{{ fmtInt(data.followers) }}</template></Column>
        <Column header="Crescimento"><template #body="{ data }"><GrowthCell :growth="data.growth" /></template></Column>
        <Column header="Posts/semana" class="right"><template #body="{ data }">{{ fmtNum(data.posts?.per_week) }}</template></Column>
        <Column header="Interação est." class="right"><template #body="{ data }">{{ fmtPct(data.interaction?.median, 3) }} (n={{ data.interaction?.n ?? 0 }})</template></Column>
        <Column header="Veículos" class="right"><template #body="{ data }">{{ fmtInt(data.inventory?.active_count) }}</template></Column>
      </DataTable>
    </section>

    <section class="panel">
      <h2>5. Sugestões de pautas <Tag value="baseadas em fatos" severity="success" /></h2>
      <p v-if="!content.suggestions.length" class="muted small">Dados insuficientes para sugerir pautas automaticamente.</p>
      <div v-for="s in content.suggestions" :key="s.pauta" class="fact">
        <strong>{{ s.pauta }}</strong><div class="small muted">Dado que motivou: {{ s.motivo }}</div>
      </div>
    </section>

    <section class="panel">
      <h2>6. Hipóteses de testes de conteúdo <Tag value="hipóteses" severity="warn" /></h2>
      <div v-for="h in content.hypotheses" :key="h.hipotese" class="hypothesis">
        <strong>{{ h.hipotese }}</strong>
        <div class="small">Teste: {{ h.teste }}</div>
        <div class="small">Como medir: {{ h.metrica }}</div>
        <div class="small muted">Dado que motivou: {{ h.motivo }}</div>
      </div>
    </section>

    <section class="panel">
      <h2>7. Perguntas para a reunião</h2>
      <ol class="small" style="margin: 0; padding-left: 20px">
        <li v-for="q in content.questions" :key="q.pergunta">{{ q.pergunta }} <span class="muted">({{ q.motivo }})</span></li>
      </ol>
    </section>

    <section class="panel small">
      <h2>8. Dados necessários para avaliar resultado comercial</h2>
      <ul style="margin: 0; padding-left: 18px"><li v-for="d in content.data_needed" :key="d">{{ d }}</li></ul>
      <h2 style="margin-top: 14px">9. Fontes e limitações</h2>
      <ul style="margin: 0; padding-left: 18px">
        <li v-for="s in content.sources" :key="s.name">{{ s.name }}: {{ s.detail || '—' }} (última coleta bem-sucedida {{ fmtDateTime(s.last_success_at) }})</li>
        <li v-for="l in content.limitations" :key="l">{{ l }}</li>
      </ul>
    </section>
  </div>
</template>
