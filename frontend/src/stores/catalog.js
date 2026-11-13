import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/api/client'

// Período global de análise e listas de apoio (empresas, parsers).
export const useCatalogStore = defineStore('catalog', () => {
  const periodDays = ref(30)
  const companies = ref([])
  const parsers = ref([])
  const loaded = ref(false)

  async function loadCompanies(force = false) {
    if (loaded.value && !force) return companies.value
    const { data } = await api.get('/companies/options')
    companies.value = data
    loaded.value = true
    return data
  }

  async function loadParsers() {
    if (parsers.value.length) return parsers.value
    const { data } = await api.get('/companies/parsers')
    parsers.value = data
    return data
  }

  return { periodDays, companies, parsers, loadCompanies, loadParsers }
})

export const PERIOD_OPTIONS = [
  { label: '7 dias', value: 7 },
  { label: '30 dias', value: 30 },
  { label: '90 dias', value: 90 },
  { label: '180 dias', value: 180 },
]
