<script setup lang="ts">
import { reactive, ref } from 'vue'
import type { TradingConfig } from '../types'

const props = defineProps<{
  isLoading: boolean
  isTrained: boolean
  progress: number
}>()

const emit = defineEmits<{
  (event: 'start-training', config: TradingConfig): void
  (event: 'start-backtest', config: TradingConfig): void
}>()

const symbols = ['NABIL', 'NICA', 'NTC', 'HDL', 'UPPER', 'CHCL', 'SHL', 'GBIME', 'EBL', 'NRIC']
const timestepOptions = [5000, 10000, 20000, 40000]

const form = ref()
const config = reactive<TradingConfig>({
  symbol: 'NABIL',
  startDate: '2022-01-01',
  endDate: '2023-12-31',
  initialBalance: 10000,
  timesteps: 10000,
})

const rules = {
  required: (value: unknown) => (value !== null && value !== '' && value !== undefined) || 'Required',
  positive: (value: number) => Number(value) > 0 || 'Must be greater than zero',
  dateOrder: () => config.startDate < config.endDate || 'End date must be after start date',
}

async function submit(event: 'start-training' | 'start-backtest') {
  const { valid } = await form.value.validate()
  if (!valid) return
  const payload: TradingConfig = {
    ...config,
    symbol: config.symbol.toUpperCase(),
    initialBalance: Number(config.initialBalance),
  }
  if (event === 'start-training') emit('start-training', payload)
  else emit('start-backtest', payload)
}
</script>

<template>
  <v-card>
    <v-card-item>
      <v-card-title class="d-flex align-center">
        <v-icon icon="mdi-tune-variant" class="mr-2" color="primary" />
        Strategy Setup
      </v-card-title>
      <v-card-subtitle>Configure the symbol, period and training budget</v-card-subtitle>
    </v-card-item>
    <v-card-text>
      <v-form ref="form" :disabled="props.isLoading" @submit.prevent>
        <v-combobox
          v-model="config.symbol"
          :items="symbols"
          label="Symbol"
          prepend-inner-icon="mdi-chart-line"
          variant="outlined"
          density="comfortable"
          hide-details="auto"
          :rules="[rules.required]"
          class="mb-4"
        />
        <v-row dense class="mb-2">
          <v-col cols="6">
            <v-text-field v-model="config.startDate" type="date" label="Start date" :rules="[rules.required]" />
          </v-col>
          <v-col cols="6">
            <v-text-field
              v-model="config.endDate"
              type="date"
              label="End date"
              :rules="[rules.required, rules.dateOrder]"
            />
          </v-col>
        </v-row>
        <v-text-field
          v-model.number="config.initialBalance"
          type="number"
          label="Initial balance"
          prefix="Rs."
          :rules="[rules.required, rules.positive]"
          class="mb-4"
        />
        <v-select v-model="config.timesteps" :items="timestepOptions" label="Training timesteps" class="mb-4" />
      </v-form>

      <v-progress-linear
        v-if="props.isLoading"
        :model-value="props.progress"
        color="primary"
        height="6"
        rounded
        class="mb-4"
      />

      <div class="d-flex ga-3">
        <v-btn
          color="primary"
          variant="flat"
          prepend-icon="mdi-brain"
          class="flex-grow-1"
          :loading="props.isLoading"
          @click="submit('start-training')"
        >
          Train
        </v-btn>
        <v-btn
          color="secondary"
          variant="tonal"
          prepend-icon="mdi-play-circle-outline"
          class="flex-grow-1"
          :disabled="!props.isTrained || props.isLoading"
          @click="submit('start-backtest')"
        >
          Backtest
        </v-btn>
      </div>
    </v-card-text>
  </v-card>
</template>
