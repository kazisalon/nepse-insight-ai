<script setup lang="ts">
import { ref } from 'vue'
import TradingControls from './components/TradingControls.vue'
import TradingStats from './components/TradingStats.vue'
import TradingChart from './components/TradingChart.vue'
import TradingHistory from './components/TradingHistory.vue'
import { runBacktest, trainStrategy } from './services/tradingEngine'
import type { ChartSeries, PerformanceData, StrategyParams, TradeRecord, TradingConfig } from './types'

type NoticeColor = 'success' | 'error' | 'warning' | 'info'

const isLoading = ref(false)
const progress = ref(0)
const strategy = ref<StrategyParams | null>(null)
const trainedKey = ref('')
const activeSymbol = ref('')
const chartData = ref<ChartSeries | null>(null)
const performanceData = ref<PerformanceData | null>(null)
const tradingHistory = ref<TradeRecord[]>([])
const notice = ref<{ show: boolean; text: string; color: NoticeColor }>({ show: false, text: '', color: 'success' })

const keyOf = (config: TradingConfig) => `${config.symbol}|${config.startDate}|${config.endDate}|${config.initialBalance}`

function notify(text: string, color: NoticeColor) {
  notice.value = { show: true, text, color }
}

async function handleTraining(config: TradingConfig) {
  isLoading.value = true
  progress.value = 0
  try {
    const params = await trainStrategy(config, (value) => (progress.value = value))
    strategy.value = params
    trainedKey.value = keyOf(config)
    notify(
      `Model trained for ${config.symbol}: buy RSI ≤ ${params.buyBelow.toFixed(0)}, sell RSI ≥ ${params.sellAbove.toFixed(0)}`,
      'success',
    )
  } catch (error) {
    notify(error instanceof Error ? error.message : 'Training failed', 'error')
  } finally {
    isLoading.value = false
  }
}

async function handleBacktest(config: TradingConfig) {
  if (!strategy.value) return
  if (trainedKey.value !== keyOf(config)) {
    notify('Settings changed since training. Train the model again first.', 'warning')
    return
  }
  isLoading.value = true
  progress.value = 100
  try {
    const result = await runBacktest(config, strategy.value)
    chartData.value = result.chart
    performanceData.value = result.performance
    tradingHistory.value = result.history
    activeSymbol.value = config.symbol
    notify('Backtest completed', 'info')
  } catch (error) {
    notify(error instanceof Error ? error.message : 'Backtest failed', 'error')
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <v-app>
    <v-app-bar flat border="b" color="surface">
      <template #prepend>
        <v-avatar color="primary" variant="tonal" rounded="lg" class="ml-2">
          <v-icon icon="mdi-robot-outline" />
        </v-avatar>
      </template>
      <v-app-bar-title>
        <span class="font-weight-bold">NEPSE Insight</span>
        <span class="text-primary font-weight-bold"> AI</span>
      </v-app-bar-title>
      <template #append>
        <v-chip
          :color="strategy ? 'success' : 'grey'"
          variant="tonal"
          size="small"
          :prepend-icon="strategy ? 'mdi-check-circle' : 'mdi-circle-outline'"
          class="mr-2"
        >
          {{ strategy ? 'Model ready' : 'Not trained' }}
        </v-chip>
      </template>
    </v-app-bar>

    <v-main>
      <v-container fluid class="pa-4 pa-md-6">
        <v-row>
          <v-col cols="12" md="4" lg="3">
            <trading-controls
              :is-loading="isLoading"
              :is-trained="!!strategy"
              :progress="progress"
              @start-training="handleTraining"
              @start-backtest="handleBacktest"
            />
            <trading-stats :performance-data="performanceData" class="mt-4" />
          </v-col>
          <v-col cols="12" md="8" lg="9">
            <trading-chart :chart-data="chartData" :is-loading="isLoading" :symbol="activeSymbol" />
          </v-col>
        </v-row>
        <v-row>
          <v-col cols="12">
            <trading-history :trading-history="tradingHistory" />
          </v-col>
        </v-row>
      </v-container>
    </v-main>

    <v-snackbar v-model="notice.show" :color="notice.color" timeout="3500" location="bottom right">
      {{ notice.text }}
    </v-snackbar>
  </v-app>
</template>
