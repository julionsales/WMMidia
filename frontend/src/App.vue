<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Toast from 'primevue/toast'
import ConfirmDialog from 'primevue/confirmdialog'
import { setUnauthorizedHandler } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const menuOpen = ref(false)

const items = [
  { to: '/', label: 'Visão geral', icon: 'pi pi-th-large', exact: true },
  { to: '/empresas', label: 'Empresas', icon: 'pi pi-building' },
  { to: '/instagram', label: 'Instagram', icon: 'pi pi-instagram' },
  { to: '/estoque', label: 'Estoque', icon: 'pi pi-car' },
  { to: '/comparativo', label: 'Comparativo', icon: 'pi pi-chart-bar' },
  { to: '/coletas', label: 'Coletas e logs', icon: 'pi pi-history' },
]

setUnauthorizedHandler(() => {
  auth.logout()
  if (route.name !== 'login') router.push({ name: 'login', query: { next: route.fullPath } })
})

if (auth.isAuthenticated) auth.fetchMe().catch(() => {})

watch(() => route.fullPath, () => { menuOpen.value = false })

function isActive(item) {
  return item.exact ? route.path === item.to : route.path.startsWith(item.to)
}

function logout() {
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <Toast position="top-right" />
  <ConfirmDialog />
  <RouterView v-if="route.meta.public" />
  <div v-else class="layout">
    <aside class="sidebar" :class="{ open: menuOpen }" aria-label="Menu principal">
      <div class="brand">
        <i class="pi pi-car" style="font-size: 1.3rem" />
        <div>Monitor Automotivo<small>Estoque · Instagram · Briefings</small></div>
      </div>
      <nav>
        <RouterLink v-for="item in items" :key="item.to" :to="item.to" :class="{ active: isActive(item) }">
          <i :class="item.icon" /> {{ item.label }}
        </RouterLink>
      </nav>
      <div class="footer">
        <div class="muted" style="color: inherit; opacity: .8">{{ auth.user?.email || '' }}</div>
        <Button label="Sair" icon="pi pi-sign-out" text size="small" style="color: inherit; padding-left: 0" @click="logout" />
      </div>
    </aside>
    <div class="main">
      <header class="topbar">
        <div class="row">
          <Button class="menu-toggle" icon="pi pi-bars" text aria-label="Abrir menu" @click="menuOpen = !menuOpen" />
          <h1>{{ route.meta.title }}</h1>
        </div>
        <span class="muted small">Horários em America/Sao_Paulo</span>
      </header>
      <main class="content">
        <RouterView :key="route.name === 'company' ? route.params.id : route.fullPath" />
      </main>
    </div>
  </div>
</template>
