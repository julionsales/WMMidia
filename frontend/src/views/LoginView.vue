<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Password from 'primevue/password'
import { errorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const email = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(email.value.trim(), password.value)
    const next = typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : '/'
    router.replace(next)
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <form class="panel login" @submit.prevent="submit">
      <div class="row" style="gap: 12px">
        <i class="pi pi-car" style="font-size: 1.6rem; color: var(--app-accent)" />
        <div>
          <h1 style="margin: 0; font-size: 1.3rem">Monitor Automotivo</h1>
          <span class="muted small">Acesso administrativo</span>
        </div>
      </div>
      <div class="field">
        <label for="email">E-mail</label>
        <InputText id="email" v-model="email" type="email" autocomplete="username" required autofocus />
      </div>
      <div class="field">
        <label for="password">Senha</label>
        <Password v-model="password" input-id="password" :feedback="false" toggle-mask autocomplete="current-password"
                  :input-props="{ required: true }" fluid />
      </div>
      <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
      <Button type="submit" label="Entrar" icon="pi pi-sign-in" :loading="loading" />
      <p class="muted small" style="margin: 0">
        O primeiro administrador é criado no servidor com <code>python -m app.cli.create_admin</code> (veja o README).
      </p>
    </form>
  </div>
</template>

<style scoped>
.login-wrap { min-height: 100vh; display: grid; place-items: center; padding: 16px; background: linear-gradient(160deg, #0f2a2e, #134e4a); }
.login { width: 100%; max-width: 380px; display: flex; flex-direction: column; gap: 16px; padding: 28px; }
</style>
