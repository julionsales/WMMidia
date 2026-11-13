import axios from 'axios'

const TOKEN_KEY = 'ma_token'

export const api = axios.create({ baseURL: '/api', timeout: 60000 })

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}
export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* armazenamento indisponível */
  }
}

let onUnauthorized = () => {}
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !error.config?.url?.includes('/auth/login')) onUnauthorized()
    return Promise.reject(error)
  },
)

export function errorMessage(error) {
  const data = error?.response?.data
  if (data?.errors?.length) return data.errors.map((e) => (e.campo ? `${e.campo}: ${e.mensagem}` : e.mensagem)).join(' · ')
  if (typeof data?.detail === 'string') return data.detail
  if (error?.code === 'ECONNABORTED') return 'Tempo de resposta esgotado'
  if (!error?.response) return 'Não foi possível conectar à API'
  return `Erro ${error.response.status}`
}

// Download autenticado (exportações e DOCX).
export async function download(url, params = {}) {
  const response = await api.get(url, { params, responseType: 'blob', paramsSerializer: { indexes: null } })
  const disposition = response.headers['content-disposition'] || ''
  const match = disposition.match(/filename="?([^"]+)"?/)
  const name = match ? match[1] : 'arquivo'
  const href = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = href
  link.download = name
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(href), 1000)
}
