import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true, title: 'Entrar' } },
  { path: '/', name: 'overview', component: () => import('@/views/OverviewView.vue'), meta: { title: 'Visão geral' } },
  { path: '/empresas', name: 'companies', component: () => import('@/views/CompaniesView.vue'), meta: { title: 'Empresas' } },
  {
    path: '/empresas/:id/:tab?',
    name: 'company',
    component: () => import('@/views/CompanyDetailView.vue'),
    props: true,
    meta: { title: 'Empresa' },
  },
  { path: '/instagram', name: 'instagram', component: () => import('@/views/InstagramView.vue'), meta: { title: 'Instagram' } },
  { path: '/estoque', name: 'inventory', component: () => import('@/views/InventoryView.vue'), meta: { title: 'Estoque' } },
  { path: '/comparativo', name: 'compare', component: () => import('@/views/CompareView.vue'), meta: { title: 'Comparativo' } },
  { path: '/coletas', name: 'runs', component: () => import('@/views/RunsView.vue'), meta: { title: 'Coletas e logs' } },
  { path: '/briefings/:id', name: 'briefing', component: () => import('@/views/BriefingView.vue'), props: true, meta: { title: 'Briefing' } },
  { path: '/:pathMatch(.*)*', name: 'notfound', component: () => import('@/views/NotFoundView.vue'), meta: { title: 'Não encontrado' } },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isAuthenticated) return { name: 'login', query: { next: to.fullPath } }
  if (to.name === 'login' && auth.isAuthenticated) return { name: 'overview' }
  return true
})

router.afterEach((to) => {
  document.title = `${to.meta.title || 'Painel'} · Monitor Automotivo`
})

export default router
