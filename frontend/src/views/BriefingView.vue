<script setup>
import { onMounted, ref } from 'vue'
import { api, download, errorMessage } from '@/api/client'
import StateBlock from '@/components/StateBlock.vue'
import BriefingContent from '@/components/BriefingContent.vue'

const props = defineProps({ id: { type: String, required: true } })
const briefing = ref(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    briefing.value = (await api.get(`/briefings/${props.id}`)).data
  } catch (e) {
    error.value = e.response?.status === 404 ? 'Briefing não encontrado.' : errorMessage(e)
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>

<template>
  <StateBlock :loading="loading" :error="error" @retry="load">
    <template v-if="briefing">
      <div class="toolbar">
        <RouterLink :to="`/empresas/${briefing.company_id}/briefing`"><i class="pi pi-arrow-left" /> {{ briefing.facts.company.name }}</RouterLink>
        <span class="spacer" />
        <Button label="Baixar DOCX" icon="pi pi-file-word" size="small" @click="download(`/briefings/${briefing.id}/docx`)" />
        <Button label="JSON" icon="pi pi-code" size="small" outlined @click="download(`/briefings/${briefing.id}/json`)" />
      </div>
      <BriefingContent :briefing="briefing" />
    </template>
  </StateBlock>
</template>
