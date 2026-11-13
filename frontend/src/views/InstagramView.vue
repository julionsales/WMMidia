<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCatalogStore } from '@/stores/catalog'
import PeriodSelect from '@/components/PeriodSelect.vue'
import InstagramPanel from '@/components/InstagramPanel.vue'
import StateBlock from '@/components/StateBlock.vue'

const catalog = useCatalogStore()
const route = useRoute()
const router = useRouter()
const companyId = ref(typeof route.query.empresa === 'string' ? route.query.empresa : null)
const loading = ref(true)
const withProfile = computed(() => catalog.companies.filter((c) => c.instagram_username))
const selected = computed(() => catalog.companies.find((c) => c.id === companyId.value))

onMounted(async () => {
  await catalog.loadCompanies()
  if (!companyId.value && withProfile.value.length) companyId.value = withProfile.value[0].id
  loading.value = false
})
watch(companyId, (id) => router.replace({ query: id ? { empresa: id } : {} }))
</script>

<template>
  <div class="panel">
    <div class="toolbar">
      <Select v-model="companyId" :options="withProfile" option-label="name" option-value="id" filter placeholder="Empresa"
              style="min-width: 260px" aria-label="Empresa" />
      <PeriodSelect v-model="catalog.periodDays" />
      <span v-if="selected" class="muted small">@{{ selected.instagram_username }}</span>
    </div>
  </div>
  <StateBlock :loading="loading" :empty="!withProfile.length" empty-text="Nenhuma empresa com perfil do Instagram cadastrado.">
    <div v-if="companyId" class="panel">
      <InstagramPanel :key="companyId" :company-id="companyId" :days="catalog.periodDays" :username="selected?.instagram_username" />
    </div>
  </StateBlock>
</template>
