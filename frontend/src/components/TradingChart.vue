<script setup lang="ts">
import { computed } from 'vue'
import { Line } from 'vue-chartjs'
import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
  type ChartData,
  type ChartOptions,
} from 'chart.js'
import type { ChartSeries } from '../types'
import { formatCurrency } from '../utils/format'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend, Filler)

const props = defineProps<{
  chartData: ChartSeries | null
  isLoading: boolean
  symbol: string
}>()

const data = computed<ChartData<'line'>>(() => ({
  labels: props.chartData?.labels ?? [],
  datasets: [
    {
      label: 'Strategy',
      data: props.chartData?.portfolio ?? [],
      borderColor: '#3b82f6',
      backgroundColor: 'rgba(59, 130, 246, 0.12)',
      fill: true,
      borderWidth: 2,
      pointRadius: 0,
      tension: 0.25,
    },
    {
      label: 'Buy & Hold',
      data: props.chartData?.benchmark ?? [],
      borderColor: '#94a3b8',
      borderDash: [6, 4],
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.25,
    },
  ],
}))

const options: ChartOptions<'line'> = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: 'index', intersect: false },
  plugins: {
    legend: { labels: { color: '#cbd5e1', usePointStyle: true, boxHeight: 6 } },
    tooltip: {
      callbacks: {
        label: (context) => `${context.dataset.label}: ${formatCurrency(Number(context.parsed.y))}`,
      },
    },
  },
  scales: {
    x: {
      ticks: { color: '#94a3b8', maxTicksLimit: 8, maxRotation: 0 },
      grid: { color: 'rgba(148, 163, 184, 0.08)' },
    },
    y: {
      ticks: { color: '#94a3b8', callback: (value) => formatCurrency(Number(value)) },
      grid: { color: 'rgba(148, 163, 184, 0.08)' },
    },
  },
}
</script>

<template>
  <v-card class="h-100">
    <v-card-item>
      <v-card-title class="d-flex align-center">
        <v-icon icon="mdi-chart-areaspline" class="mr-2" color="primary" />
        Portfolio Value
        <v-chip v-if="props.symbol" size="small" color="primary" variant="tonal" class="ml-3">
          {{ props.symbol }}
        </v-chip>
      </v-card-title>
    </v-card-item>
    <v-card-text>
      <div class="chart-container">
        <div v-if="props.isLoading" class="state">
          <v-progress-circular indeterminate color="primary" size="48" />
        </div>
        <Line v-else-if="props.chartData" :data="data" :options="options" />
        <div v-else class="state text-medium-emphasis">
          <v-icon icon="mdi-chart-line-variant" size="48" class="mb-2" />
          <div>Train the model, then run a backtest to plot results</div>
        </div>
      </div>
    </v-card-text>
  </v-card>
</template>

<style scoped>
.chart-container {
  position: relative;
  height: 420px;
}

.state {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}
</style>
