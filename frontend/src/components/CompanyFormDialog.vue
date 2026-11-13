<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useToast } from 'primevue/usetoast'
import { api, errorMessage } from '@/api/client'
import { useCatalogStore } from '@/stores/catalog'

const props = defineProps({ company: { type: Object, default: null } })
const visible = defineModel('visible', { type: Boolean, default: false })
const emit = defineEmits(['saved'])
const toast = useToast()
const catalog = useCatalogStore()
const saving = ref(false)
const errors = ref([])

const UFS = 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split(' ')
const blank = () => ({
  name: '', website: '', inventory_url: '', inventory_parser: 'auto', instagram: '', segment: '', city: '', state: null,
  notes: '', active: true, inventory_frequency_hours: 24, instagram_frequency_hours: 24, competitor_ids: [],
  min_model_stock: 3, load_more: false,
})
const form = reactive(blank())
const isEdit = computed(() => Boolean(props.company?.id))
const competitorOptions = computed(() => catalog.companies.filter((c) => c.id !== props.company?.id))

watch(visible, async (open) => {
  if (!open) return
  errors.value = []
  await Promise.all([catalog.loadParsers(), catalog.loadCompanies(true)])
  Object.assign(form, blank())
  if (props.company) {
    const c = props.company
    Object.assign(form, {
      name: c.name, website: c.website || '', inventory_url: c.inventory_url || '', inventory_parser: c.inventory_parser || 'auto',
      instagram: c.instagram_username || '', segment: c.segment || '', city: c.city || '', state: c.state || null,
      notes: c.notes || '', active: c.active, inventory_frequency_hours: c.inventory_frequency_hours ?? 24,
      instagram_frequency_hours: c.instagram_frequency_hours ?? 24, competitor_ids: [...(c.competitor_ids || [])],
      min_model_stock: c.min_model_stock ?? 3, load_more: Boolean(c.load_more),
    })
  }
})

function fieldError(name) {
  return errors.value.filter((e) => e.campo === name).map((e) => e.mensagem).join(' ')
}

async function save() {
  saving.value = true
  errors.value = []
  try {
    const payload = { ...form }
    for (const key of ['website', 'inventory_url', 'instagram', 'segment', 'city', 'notes']) if (!payload[key]) payload[key] = null
    const { data } = isEdit.value
      ? await api.put(`/companies/${props.company.id}`, payload)
      : await api.post('/companies', payload)
    toast.add({ severity: 'success', summary: isEdit.value ? 'Empresa atualizada' : 'Empresa cadastrada', detail: data.name, life: 3000 })
    catalog.loadCompanies(true)
    visible.value = false
    emit('saved', data)
  } catch (e) {
    errors.value = e.response?.data?.errors || []
    toast.add({ severity: 'error', summary: 'Verifique os dados', detail: errorMessage(e), life: 6000 })
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog v-model:visible="visible" modal :header="isEdit ? 'Editar empresa' : 'Nova empresa'" :style="{ width: '860px' }"
          :breakpoints="{ '900px': '96vw' }">
    <form class="form-grid" @submit.prevent="save">
      <div class="field">
        <label for="f-name">Nome *</label>
        <InputText id="f-name" v-model="form.name" :invalid="!!fieldError('name')" />
        <small class="p-error">{{ fieldError('name') }}</small>
      </div>
      <div class="field">
        <label for="f-site">Site</label>
        <InputText id="f-site" v-model="form.website" placeholder="https://" :invalid="!!fieldError('website')" />
        <small class="p-error">{{ fieldError('website') }}</small>
      </div>
      <div class="field full">
        <label for="f-inv">URL do estoque</label>
        <InputText id="f-inv" v-model="form.inventory_url" placeholder="https://loja.com.br/estoque" :invalid="!!fieldError('inventory_url')" />
        <small>Endereços internos, IPs privados e credenciais na URL são bloqueados; redirecionamentos também são verificados.</small>
        <small class="p-error">{{ fieldError('inventory_url') }}</small>
      </div>
      <div class="field">
        <label for="f-parser">Parser de estoque</label>
        <Select input-id="f-parser" v-model="form.inventory_parser" :options="catalog.parsers" option-label="label" option-value="key" />
      </div>
      <div class="field">
        <label for="f-ig">Instagram (username ou URL)</label>
        <InputText id="f-ig" v-model="form.instagram" placeholder="@perfil" :invalid="!!fieldError('instagram')" />
        <small class="p-error">{{ fieldError('instagram') }}</small>
      </div>
      <div class="field">
        <label for="f-seg">Segmento</label>
        <InputText id="f-seg" v-model="form.segment" placeholder="Seminovos premium" />
      </div>
      <div class="field">
        <label for="f-city">Cidade</label>
        <InputText id="f-city" v-model="form.city" />
      </div>
      <div class="field">
        <label for="f-uf">Estado</label>
        <Select input-id="f-uf" v-model="form.state" :options="UFS" show-clear placeholder="UF" />
      </div>
      <div class="field">
        <label for="f-finv">Frequência de coleta do estoque (horas)</label>
        <InputNumber input-id="f-finv" v-model="form.inventory_frequency_hours" :min="0" :max="720" show-buttons />
        <small>0 = somente manual</small>
      </div>
      <div class="field">
        <label for="f-fig">Frequência de coleta do Instagram (horas)</label>
        <InputNumber input-id="f-fig" v-model="form.instagram_frequency_hours" :min="0" :max="720" show-buttons />
        <small>0 = somente manual. O servidor aplica um intervalo mínimo para respeitar limites do Instagram.</small>
      </div>
      <div class="field">
        <label for="f-min">Mínimo para "giro de estoque"</label>
        <InputNumber input-id="f-min" v-model="form.min_model_stock" :min="1" :max="50" show-buttons />
        <small>Unidades do mesmo modelo para sugerir pauta de giro.</small>
      </div>
      <div class="field">
        <label>Opções</label>
        <div class="row small"><ToggleSwitch v-model="form.active" input-id="f-active" /><label for="f-active">Empresa ativa</label></div>
        <div class="row small"><ToggleSwitch v-model="form.load_more" input-id="f-lm" /><label for="f-lm">Clicar em "carregar mais" (parser com navegador)</label></div>
      </div>
      <div class="field full">
        <label for="f-comp">Concorrentes para comparação</label>
        <MultiSelect input-id="f-comp" v-model="form.competitor_ids" :options="competitorOptions" option-label="name" option-value="id"
                     filter display="chip" placeholder="Selecione" :selection-limit="20" />
      </div>
      <div class="field full">
        <label for="f-notes">Observações</label>
        <Textarea id="f-notes" v-model="form.notes" rows="3" auto-resize />
      </div>
    </form>
    <template #footer>
      <Button label="Cancelar" text @click="visible = false" />
      <Button label="Salvar" icon="pi pi-check" :loading="saving" @click="save" />
    </template>
  </Dialog>
</template>
