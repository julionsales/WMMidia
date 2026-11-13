<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], default: '—' },
  hint: { type: String, default: '' },
  icon: { type: String, default: '' },
  tone: { type: String, default: 'default' },
})
</script>

<template>
  <div class="panel kpi" :class="`tone-${tone}`">
    <div class="row muted small"><i v-if="icon" :class="icon" /> {{ label }}</div>
    <div class="kpi-value">{{ value }}</div>
    <div v-if="hint || $slots.default" class="muted small"><slot>{{ hint }}</slot></div>
  </div>
</template>

<style scoped>
.kpi { display: flex; flex-direction: column; gap: 6px; }
.kpi-value { font-size: 1.55rem; font-weight: 700; line-height: 1.1; }
.tone-warn { border-color: var(--app-warn-border); }
.tone-danger { border-color: #f1a7a7; }
</style>
