import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, getToken, setToken } from '@/api/client'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(getToken())
  const user = ref(null)
  const isAuthenticated = computed(() => Boolean(token.value))

  async function login(email, password) {
    const { data } = await api.post('/auth/login', { email, password })
    token.value = data.access_token
    setToken(data.access_token)
    user.value = data.user
  }

  async function fetchMe() {
    if (!token.value) return null
    const { data } = await api.get('/auth/me')
    user.value = data
    return data
  }

  function logout() {
    token.value = null
    user.value = null
    setToken(null)
  }

  return { token, user, isAuthenticated, login, fetchMe, logout }
})
