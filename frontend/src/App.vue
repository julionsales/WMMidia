<script setup>
import { ref } from 'vue'

const email = ref('')
const senha = ref('')
const mensagem = ref('')

async function login() {
  mensagem.value = 'Entrando...'
  try {
    const response = await fetch('http://localhost:8000/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.value, senha: senha.value })
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'Erro ao entrar')
    localStorage.setItem('access_token', data.access_token)
    mensagem.value = 'Login realizado com sucesso.'
  } catch (error) {
    mensagem.value = error.message
  }
}
</script>

<template>
  <main class="page">
    <section class="card">
      <h1>VEIF & VEALS</h1>
      <p>Login</p>
      <input v-model="email" type="email" placeholder="E-mail" />
      <input v-model="senha" type="password" placeholder="Senha" @keyup.enter="login" />
      <button @click="login">ENTRAR</button>
      <small v-if="mensagem">{{ mensagem }}</small>
    </section>
  </main>
</template>
