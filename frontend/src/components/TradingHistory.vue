<script setup lang="ts">
import { computed, ref } from 'vue'
import type { TradeAction, TradeRecord } from '../types'
import { formatCurrency } from '../utils/format'

const props = defineProps<{ tradingHistory: TradeRecord[] }>()

const showHolds = ref(false)

const headers = [
  { title: 'Date', key: 'date' },
  { title: 'Action', key: 'action' },
  { title: 'Price', key: 'price', align: 'end' as const },
  { title: 'Holdings', key: 'holdings', align: 'end' as const },
  { title: 'Cash', key: 'balance', align: 'end' as const },
  { title: 'Portfolio Value', key: 'portfolioValue', align: 'end' as const },
]

const actionColor: Record<TradeAction, string> = { Buy: 'success', Sell: 'error', Hold: 'grey' }

const items = computed(() =>
  showHolds.value ? props.tradingHistory : props.tradingHistory.filter((record) => record.action !== 'Hold'),
)
</script>

<template>
  <v-card>
    <v-card-item>
      <v-card-title class="d-flex align-center flex-wrap ga-2">
        <v-icon icon="mdi-history" class="mr-2" color="primary" />
        Trade History
        <v-spacer />
        <v-switch v-model="showHolds" label="Show hold days" color="primary" density="compact" hide-details inset />
      </v-card-title>
    </v-card-item>
    <v-data-table
      :headers="headers"
      :items="items"
      :items-per-page="10"
      density="comfortable"
      no-data-text="No trades yet"
      class="bg-transparent"
    >
      <template #[`item.action`]="{ item }">
        <v-chip :color="actionColor[item.action]" size="small" variant="tonal" label>{{ item.action }}</v-chip>
      </template>
      <template #[`item.price`]="{ item }">
        <span class="font-mono">{{ formatCurrency(item.price) }}</span>
      </template>
      <template #[`item.holdings`]="{ item }">
        <span class="font-mono">{{ item.holdings }}</span>
      </template>
      <template #[`item.balance`]="{ item }">
        <span class="font-mono">{{ formatCurrency(item.balance) }}</span>
      </template>
      <template #[`item.portfolioValue`]="{ item }">
        <span class="font-mono">{{ formatCurrency(item.portfolioValue) }}</span>
      </template>
    </v-data-table>
  </v-card>
</template>
