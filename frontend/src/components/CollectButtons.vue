<script setup>
import { ref } from 'vue'
import { useToast } from 'primevue/usetoast'
import { api, errorMessage } from '@/api/client'

const props = defineProps({ company: { type: Object, required: true }, compact: Boolean })
const emit = defineEmits(['queued'])
const toast = useToast()
const busy = ref('')

async function collect(source) {
  busy.value = source
  try {
    const { data } = await api.post(`/companies/${props.company.id}/collect/${source}`)
    toast.add({
      severity: data.created ? 'success' : 'info',
      summary: data.created ? 'Coleta enfileirada' : 'Coleta já em andamento',
      detail: `${data.message}. Execução ${data.run_id.slice(-6)}.`,
      life: 4000,
    })
    emit('queued', data)
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Não foi possível solicitar', detail: errorMessage(e), life: 5000 })
  } finally {
    busy.value = ''
  }
}
</script>

<template>
  <Button :icon="'pi pi-car'" :label="compact ? undefined : 'Coletar estoque'" :text="compact" :rounded="compact"
          :outlined="!compact" size="small" :loading="busy === 'inventory'"
          :disabled="!company.active || !company.inventory_url"
          v-tooltip.top="'Coletar estoque agora'" @click="collect('inventory')" />
  <Button :icon="'pi pi-instagram'" :label="compact ? undefined : 'Coletar Instagram'" :text="compact" :rounded="compact"
          :outlined="!compact" size="small" :loading="busy === 'instagram'"
          :disabled="!company.active || !company.instagram_username"
          v-tooltip.top="'Coletar Instagram agora'" @click="collect('instagram')" />
</template>
