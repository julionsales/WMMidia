<script setup>
import { reactive, ref, watch } from 'vue'
import { useToast } from 'primevue/usetoast'
import { api, errorMessage } from '@/api/client'

const props = defineProps({ companyId: { type: String, required: true } })
const visible = defineModel('visible', { type: Boolean, default: false })
const emit = defineEmits(['saved'])
const toast = useToast()
const saving = ref(false)
const form = reactive({ collected_at: new Date(), followers: null, following: null, media_count: null, note: '' })

watch(visible, (open) => {
  if (open) Object.assign(form, { collected_at: new Date(), followers: null, following: null, media_count: null, note: '' })
})

async function save() {
  saving.value = true
  try {
    await api.post(`/instagram/companies/${props.companyId}/snapshots`, { ...form, collected_at: form.collected_at.toISOString() })
    toast.add({ severity: 'success', summary: 'Snapshot manual registrado', detail: 'Origem "manual" e responsável foram registrados.', life: 3500 })
    visible.value = false
    emit('saved')
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Não foi possível salvar', detail: errorMessage(e), life: 5000 })
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog v-model:visible="visible" modal header="Snapshot manual do Instagram" :style="{ width: '520px' }" :breakpoints="{ '600px': '96vw' }">
    <p class="muted small" style="margin-top: 0">
      Use quando a coleta automática não for possível. O registro fica identificado como "manual", com seu usuário e a fonte informada.
    </p>
    <div class="form-grid">
      <div class="field">
        <label for="ms-date">Data e hora da observação</label>
        <DatePicker input-id="ms-date" v-model="form.collected_at" show-time hour-format="24" :max-date="new Date()" date-format="dd/mm/yy" />
      </div>
      <div class="field">
        <label for="ms-f">Seguidores</label>
        <InputNumber input-id="ms-f" v-model="form.followers" :min="0" locale="pt-BR" />
      </div>
      <div class="field">
        <label for="ms-g">Seguindo</label>
        <InputNumber input-id="ms-g" v-model="form.following" :min="0" locale="pt-BR" />
      </div>
      <div class="field">
        <label for="ms-m">Publicações</label>
        <InputNumber input-id="ms-m" v-model="form.media_count" :min="0" locale="pt-BR" />
      </div>
      <div class="field full">
        <label for="ms-n">Fonte da informação *</label>
        <Textarea id="ms-n" v-model="form.note" rows="2" placeholder="Ex.: print enviado pelo cliente em 10/10" />
      </div>
    </div>
    <template #footer>
      <Button label="Cancelar" text @click="visible = false" />
      <Button label="Registrar" icon="pi pi-check" :loading="saving" :disabled="form.note.trim().length < 3" @click="save" />
    </template>
  </Dialog>
</template>
