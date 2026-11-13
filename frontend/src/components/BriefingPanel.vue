<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useToast } from 'primevue/usetoast'
import { api, download, errorMessage } from '@/api/client'
import { fmtDate, fmtDateTime } from '@/utils/format'
import StateBlock from '@/components/StateBlock.vue'
import BriefingContent from '@/components/BriefingContent.vue'

const props = defineProps({ companyId: { type: String, required: true } })
const toast = useToast()
const list = reactive({ items: [], loading: true, error: '' })
const form = reactive({ period_days: 30, title: '' })
const generating = ref(false)
const current = ref(null)
const loadingCurrent = ref(false)

async function loadList() {
  list.loading = true
  list.error = ''
  try {
    list.items = (await api.get(`/companies/${props.companyId}/briefings`, { params: { size: 50 } })).data.items
    if (!current.value && list.items.length) open(list.items[0].id)
  } catch (e) {
    list.error = errorMessage(e)
  } finally {
    list.loading = false
  }
}

async function open(id) {
  loadingCurrent.value = true
  try {
    current.value = (await api.get(`/briefings/${id}`)).data
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Erro ao abrir briefing', detail: errorMessage(e), life: 5000 })
  } finally {
    loadingCurrent.value = false
  }
}

async function generate() {
  generating.value = true
  try {
    const { data } = await api.post(`/companies/${props.companyId}/briefings`, { period_days: form.period_days, title: form.title || null })
    toast.add({ severity: 'success', summary: `Briefing v${data.version} gerado`, life: 3000 })
    current.value = data
    form.title = ''
    loadList()
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Não foi possível gerar', detail: errorMessage(e), life: 6000 })
  } finally {
    generating.value = false
  }
}

onMounted(loadList)
</script>

<template>
  <div class="stack" style="gap: 16px">
    <div class="panel">
      <div class="toolbar">
        <div class="field"><label for="b-days">Período (dias)</label>
          <InputNumber input-id="b-days" v-model="form.period_days" :min="7" :max="365" show-buttons input-style="width: 90px" /></div>
        <div class="field" style="flex: 1; min-width: 220px"><label for="b-title">Título (opcional)</label>
          <InputText id="b-title" v-model="form.title" placeholder="Ex.: Reunião mensal de novembro" /></div>
        <Button label="Gerar nova versão" icon="pi pi-file-plus" :loading="generating" style="align-self: flex-end" @click="generate" />
      </div>
      <p class="muted small" style="margin: 8px 0 0">As sugestões usam regras transparentes (sem IA paga) e cada uma informa o dado que a motivou.</p>
    </div>
    <div class="grid" style="grid-template-columns: minmax(220px, 280px) 1fr; align-items: start">
      <div class="panel">
        <h3>Versões salvas</h3>
        <StateBlock :loading="list.loading" :error="list.error" @retry="loadList" :empty="!list.items.length" empty-text="Nenhum briefing gerado ainda.">
          <div class="stack">
            <button v-for="b in list.items" :key="b.id" class="version" :class="{ selected: current?.id === b.id }" @click="open(b.id)">
              <strong>v{{ b.version }}</strong> · {{ fmtDateTime(b.created_at) }}
              <div class="muted small">{{ b.title }}</div>
              <div class="muted small">{{ fmtDate(b.period.start) }} a {{ fmtDate(b.period.end) }}</div>
            </button>
          </div>
        </StateBlock>
      </div>
      <div>
        <StateBlock :loading="loadingCurrent" :empty="!current" empty-text="Gere ou selecione uma versão para visualizar.">
          <template v-if="current">
            <div class="toolbar" style="margin-bottom: 10px">
              <Button label="Baixar DOCX" icon="pi pi-file-word" size="small" @click="download(`/briefings/${current.id}/docx`)" />
              <Button label="Baixar JSON (dados usados)" icon="pi pi-code" size="small" outlined @click="download(`/briefings/${current.id}/json`)" />
              <RouterLink :to="`/briefings/${current.id}`" class="small">abrir em página própria</RouterLink>
            </div>
            <BriefingContent :briefing="current" />
          </template>
        </StateBlock>
      </div>
    </div>
  </div>
</template>

<style scoped>
.version { text-align: left; border: 1px solid var(--app-border); background: #fff; border-radius: 8px; padding: 8px 10px; cursor: pointer; font: inherit; }
.version.selected { border-color: var(--app-accent); background: #f0fdfa; }
@media (max-width: 960px) { .grid { grid-template-columns: 1fr !important; } }
</style>
