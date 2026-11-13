<script setup>
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { DataZoomComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'

use([CanvasRenderer, BarChart, LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent])

defineProps({ option: { type: Object, required: true }, height: { type: String, default: '300px' } })
</script>

<template>
  <VChart class="chart" :style="{ height }" :option="option" autoresize />
</template>
