<script setup>
// Estados padronizados: carregando, erro, sem dados e histórico insuficiente.
defineProps({
  loading: Boolean,
  error: { type: String, default: '' },
  empty: Boolean,
  emptyText: { type: String, default: 'Nenhum dado disponível.' },
  insufficient: Boolean,
  insufficientText: { type: String, default: 'Histórico insuficiente: são necessárias ao menos duas coletas no período.' },
})
defineEmits(['retry'])
</script>

<template>
  <div v-if="loading" class="stack" aria-busy="true">
    <Skeleton height="1.4rem" width="40%" />
    <Skeleton height="6rem" />
  </div>
  <Message v-else-if="error" severity="error" :closable="false">
    <div class="row">
      <span>{{ error }}</span>
      <Button label="Tentar novamente" size="small" text icon="pi pi-refresh" @click="$emit('retry')" />
    </div>
  </Message>
  <div v-else-if="empty" class="muted small row"><i class="pi pi-inbox" /> {{ emptyText }}</div>
  <div v-else-if="insufficient" class="notice"><i class="pi pi-clock" /> {{ insufficientText }}</div>
  <slot v-else />
</template>
