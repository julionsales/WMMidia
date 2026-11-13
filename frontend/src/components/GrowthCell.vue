<script setup>
// Crescimento sempre com as datas reais dos snapshots, ou "histórico insuficiente".
import { fmtDate, fmtPct, fmtSignedInt } from '@/utils/format'
defineProps({ growth: { type: Object, default: null }, compact: Boolean })
</script>

<template>
  <span v-if="!growth || growth.status !== 'ok'" class="muted small" v-tooltip.top="'Necessárias ao menos duas coletas no período'">
    Histórico insuficiente
  </span>
  <span v-else class="stack" style="gap: 2px">
    <span :style="{ color: growth.absolute < 0 ? '#b91c1c' : '#047857', fontWeight: 600 }">
      {{ fmtSignedInt(growth.absolute) }} ({{ fmtPct(growth.percent) }})
    </span>
    <span v-if="!compact" class="muted small nowrap">{{ fmtDate(growth.start.date) }} → {{ fmtDate(growth.end.date) }}</span>
    <span v-else class="muted small nowrap" v-tooltip.top="`Snapshots de ${fmtDate(growth.start.date)} e ${fmtDate(growth.end.date)}`">
      {{ growth.span_days }} dias
    </span>
  </span>
</template>
