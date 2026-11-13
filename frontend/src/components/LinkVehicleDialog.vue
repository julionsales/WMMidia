<script setup>
// Associação MANUAL publicação ↔ anúncio. O sistema nunca associa automaticamente.
import { computed, ref, watch } from 'vue'
import { useToast } from 'primevue/usetoast'
import { api, errorMessage } from '@/api/client'
import { fmtBRL, fmtDateTime, truncate } from '@/utils/format'

const props = defineProps({ post: { type: Object, default: null }, companyId: { type: String, required: true } })
const emit = defineEmits(['close', 'saved'])
const toast = useToast()
const search = ref('')
const vehicles = ref([])
const selected = ref(null)
const note = ref('')
const saving = ref(false)
const visible = computed({ get: () => Boolean(props.post), set: (v) => { if (!v) emit('close') } })

async function find() {
  const { data } = await api.get('/inventory/vehicles', {
    params: { company_id: props.companyId, search: search.value || undefined, status: 'todos', size: 50 },
  })
  vehicles.value = data.items.map((v) => ({ ...v, label: `${v.brand_display} ${v.model} ${v.version || ''} — ${fmtBRL(v.price, v.price_on_request)}` }))
}
watch(() => props.post, (p) => { if (p) { selected.value = null; note.value = ''; search.value = ''; find() } })
let timer
watch(search, () => { clearTimeout(timer); timer = setTimeout(find, 300) })

async function unlink(link) {
  try {
    await api.delete(`/instagram/links/${link.id}`)
    toast.add({ severity: 'success', summary: 'Associação removida', life: 2500 })
    emit('saved')
    emit('close')
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Erro', detail: errorMessage(e), life: 5000 })
  }
}

async function save() {
  saving.value = true
  try {
    await api.post('/instagram/links', { post_id: props.post.id, vehicle_id: selected.value, note: note.value || null })
    toast.add({ severity: 'success', summary: 'Publicação associada ao anúncio', life: 3000 })
    emit('saved')
    emit('close')
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Não foi possível associar', detail: errorMessage(e), life: 5000 })
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog v-model:visible="visible" modal header="Associar publicação a um anúncio" :style="{ width: '620px' }" :breakpoints="{ '700px': '96vw' }">
    <template v-if="post">
      <p class="small" style="margin-top: 0"><strong>{{ fmtDateTime(post.taken_at) }}</strong> — {{ truncate(post.caption, 160) }}</p>
      <div v-if="post.vehicle_links?.length" class="stack small" style="margin-bottom: 12px">
        <strong>Associações atuais</strong>
        <div v-for="l in post.vehicle_links" :key="l.id" class="row">
          {{ l.vehicle_title }} <span class="muted">por {{ l.created_by }}</span>
          <Button icon="pi pi-times" text rounded size="small" severity="danger" v-tooltip.top="'Remover'" @click="unlink(l)" />
        </div>
      </div>
      <div class="field">
        <label for="lv-s">Buscar anúncio da empresa</label>
        <InputText id="lv-s" v-model="search" placeholder="Modelo ou versão" />
      </div>
      <div class="field" style="margin-top: 10px">
        <label for="lv-v">Anúncio</label>
        <Select input-id="lv-v" v-model="selected" :options="vehicles" option-label="label" option-value="id" placeholder="Selecione" filter />
      </div>
      <div class="field" style="margin-top: 10px">
        <label for="lv-n">Evidência / observação</label>
        <Textarea id="lv-n" v-model="note" rows="2" placeholder="Ex.: legenda cita o veículo e a placa final 1234" />
      </div>
    </template>
    <template #footer>
      <Button label="Cancelar" text @click="emit('close')" />
      <Button label="Associar" icon="pi pi-link" :disabled="!selected" :loading="saving" @click="save" />
    </template>
  </Dialog>
</template>
