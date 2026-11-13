<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import { api, errorMessage } from '@/api/client'
import { fmtDateTime } from '@/utils/format'
import StateBlock from '@/components/StateBlock.vue'
import CompanyFormDialog from '@/components/CompanyFormDialog.vue'
import CollectButtons from '@/components/CollectButtons.vue'

const router = useRouter()
const confirm = useConfirm()
const toast = useToast()
const state = reactive({ items: [], total: 0, loading: false, error: '' })
const query = reactive({ page: 1, size: 20, search: '', active: null, sort: 'name', order: 'asc' })
const dialog = ref(false)
const editing = ref(null)
const activeOptions = [
  { label: 'Todas', value: null },
  { label: 'Ativas', value: true },
  { label: 'Inativas', value: false },
]

async function load() {
  state.loading = true
  state.error = ''
  try {
    const params = { ...query }
    if (params.active === null) delete params.active
    if (!params.search) delete params.search
    const { data } = await api.get('/companies', { params })
    state.items = data.items
    state.total = data.total
  } catch (e) {
    state.error = errorMessage(e)
  } finally {
    state.loading = false
  }
}

let timer
watch(() => query.search, () => { clearTimeout(timer); timer = setTimeout(() => { query.page = 1; load() }, 350) })
watch(() => query.active, () => { query.page = 1; load() })

function openNew() { editing.value = null; dialog.value = true }
function openEdit(company) { editing.value = company; dialog.value = true }

function toggleActive(company) {
  const action = company.active ? 'deactivate' : 'activate'
  confirm.require({
    header: company.active ? 'Desativar empresa' : 'Reativar empresa',
    message: company.active
      ? `Desativar "${company.name}"? As coletas agendadas param, mas o histórico é mantido.`
      : `Reativar "${company.name}"? As coletas agendadas voltam a ocorrer.`,
    acceptLabel: company.active ? 'Desativar' : 'Reativar',
    rejectLabel: 'Cancelar',
    accept: async () => {
      try {
        await api.post(`/companies/${company.id}/${action}`)
        toast.add({ severity: 'success', summary: 'Situação atualizada', life: 2500 })
        load()
      } catch (e) {
        toast.add({ severity: 'error', summary: 'Erro', detail: errorMessage(e), life: 5000 })
      }
    },
  })
}

function onPage(e) { query.page = e.page + 1; query.size = e.rows; load() }
function onSort(e) { query.sort = e.sortField || 'name'; query.order = e.sortOrder === -1 ? 'desc' : 'asc'; load() }

onMounted(load)
</script>

<template>
  <div class="panel">
    <div class="panel-head">
      <h2><i class="pi pi-building" /> Empresas cadastradas</h2>
      <Button label="Nova empresa" icon="pi pi-plus" @click="openNew" />
    </div>
    <div class="toolbar" style="margin-bottom: 10px">
      <IconField>
        <InputIcon class="pi pi-search" />
        <InputText v-model="query.search" placeholder="Buscar" />
      </IconField>
      <Select v-model="query.active" :options="activeOptions" option-label="label" option-value="value" />
    </div>
    <StateBlock :error="state.error" @retry="load">
      <DataTable :value="state.items" lazy paginator :rows="query.size" :total-records="state.total" :loading="state.loading"
                 :first="(query.page - 1) * query.size" :rows-per-page-options="[10, 20, 50]" data-key="id" size="small"
                 :sort-field="query.sort" :sort-order="query.order === 'asc' ? 1 : -1" scrollable @page="onPage" @sort="onSort">
        <template #empty><span class="muted">Nenhuma empresa cadastrada ainda.</span></template>
        <Column field="name" header="Nome" sortable>
          <template #body="{ data }">
            <RouterLink :to="`/empresas/${data.id}`"><strong>{{ data.name }}</strong></RouterLink>
            <Tag v-if="data.is_demo" value="DEMO" severity="contrast" style="margin-left: 6px" />
            <div class="muted small">{{ data.segment }} {{ [data.city, data.state].filter(Boolean).join(' / ') }}</div>
          </template>
        </Column>
        <Column header="Estoque">
          <template #body="{ data }">
            <a v-if="data.inventory_url" :href="data.inventory_url" target="_blank" rel="noopener" class="small">{{ data.inventory_url }}</a>
            <span v-else class="muted small">sem URL</span>
            <div class="muted small">Parser: {{ data.inventory_parser }} · a cada {{ data.inventory_frequency_hours || '—' }} h</div>
          </template>
        </Column>
        <Column header="Instagram">
          <template #body="{ data }">
            <span v-if="data.instagram_username">@{{ data.instagram_username }}</span>
            <span v-else class="muted small">—</span>
            <div class="muted small">a cada {{ data.instagram_frequency_hours || '—' }} h</div>
          </template>
        </Column>
        <Column field="updated_at" header="Atualizada em" sortable>
          <template #body="{ data }"><span class="small">{{ fmtDateTime(data.updated_at) }}</span></template>
        </Column>
        <Column header="Status">
          <template #body="{ data }"><Tag :value="data.active ? 'Ativa' : 'Inativa'" :severity="data.active ? 'success' : 'secondary'" /></template>
        </Column>
        <Column header="Ações" style="min-width: 300px">
          <template #body="{ data }">
            <div class="row" style="gap: 2px">
              <Button icon="pi pi-pencil" text rounded v-tooltip.top="'Editar'" @click="openEdit(data)" />
              <CollectButtons :company="data" compact />
              <Button icon="pi pi-chart-line" text rounded v-tooltip.top="'Dashboard'" @click="router.push(`/empresas/${data.id}`)" />
              <Button icon="pi pi-history" text rounded v-tooltip.top="'Histórico de execuções'" @click="router.push(`/empresas/${data.id}/coletas`)" />
              <Button icon="pi pi-file-word" text rounded v-tooltip.top="'Gerar briefing'" @click="router.push(`/empresas/${data.id}/briefing`)" />
              <Button :icon="data.active ? 'pi pi-ban' : 'pi pi-replay'" text rounded :severity="data.active ? 'danger' : 'success'"
                      v-tooltip.top="data.active ? 'Desativar' : 'Reativar'" @click="toggleActive(data)" />
            </div>
          </template>
        </Column>
      </DataTable>
    </StateBlock>
  </div>
  <CompanyFormDialog v-model:visible="dialog" :company="editing" @saved="load" />
</template>
