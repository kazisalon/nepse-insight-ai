<script setup lang="ts">
import { computed } from 'vue'
import type { PerformanceData } from '../types'
import { formatCurrency, formatPercent } from '../utils/format'

const props = defineProps<{ performanceData: PerformanceData | null }>()

const tone = (value: number) => (value >= 0 ? 'text-success' : 'text-error')

const metrics = computed(() => {
  const data = props.performanceData
  if (!data) return []
  return [
    { label: 'Initial Balance', value: formatCurrency(data.initialBalance), icon: 'mdi-wallet-outline', tone: '' },
    { label: 'Final Value', value: formatCurrency(data.finalBalance), icon: 'mdi-cash-multiple', tone: '' },
    {
      label: 'Total Return',
      value: formatPercent(data.totalReturn),
      icon: 'mdi-trending-up',
      tone: tone(data.totalReturn),
    },
    {
      label: 'Buy & Hold',
      value: formatPercent(data.buyAndHoldReturn),
      icon: 'mdi-scale-balance',
      tone: tone(data.buyAndHoldReturn),
    },
    {
      label: 'Max Drawdown',
      value: `-${data.maxDrawdown.toFixed(2)}%`,
      icon: 'mdi-arrow-down-bold',
      tone: 'text-error',
    },
    {
      label: 'Trades / Win Rate',
      value: `${data.totalTrades} / ${data.winRate.toFixed(1)}%`,
      icon: 'mdi-swap-horizontal',
      tone: '',
    },
  ]
})
</script>

<template>
  <v-card>
    <v-card-item>
      <v-card-title class="d-flex align-center">
        <v-icon icon="mdi-finance" class="mr-2" color="primary" />
        Performance
      </v-card-title>
    </v-card-item>
    <v-card-text>
      <v-list v-if="metrics.length" density="compact" bg-color="transparent" class="pa-0">
        <v-list-item v-for="metric in metrics" :key="metric.label" :prepend-icon="metric.icon" class="px-0">
          <v-list-item-subtitle>{{ metric.label }}</v-list-item-subtitle>
          <template #append>
            <span class="font-mono font-weight-medium" :class="metric.tone">{{ metric.value }}</span>
          </template>
        </v-list-item>
      </v-list>
      <div v-else class="text-center text-medium-emphasis py-6">
        <v-icon icon="mdi-chart-box-outline" size="40" class="mb-2" />
        <div>Run a backtest to see performance metrics</div>
      </div>
    </v-card-text>
  </v-card>
</template>
