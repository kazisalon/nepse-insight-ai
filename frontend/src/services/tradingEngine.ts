import type {
  ChartSeries,
  PerformanceData,
  PricePoint,
  StrategyParams,
  TradeAction,
  TradeRecord,
  TradingConfig,
} from '../types'

const RSI_PERIOD = 14

function hashSeed(value: string): number {
  let hash = 2166136261
  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

function createRandom(seed: number): () => number {
  let state = seed || 1
  return () => {
    state = (state + 0x6d2b79f5) | 0
    let t = Math.imul(state ^ (state >>> 15), 1 | state)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function gaussian(random: () => number): number {
  const u = Math.max(random(), 1e-12)
  const v = random()
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v)
}

function tradingDays(startDate: string, endDate: string): string[] {
  const days: string[] = []
  const cursor = new Date(`${startDate}T00:00:00Z`)
  const end = new Date(`${endDate}T00:00:00Z`)
  while (cursor <= end) {
    const day = cursor.getUTCDay()
    if (day !== 5 && day !== 6) days.push(cursor.toISOString().slice(0, 10))
    cursor.setUTCDate(cursor.getUTCDate() + 1)
  }
  return days
}

export function generatePriceSeries(config: TradingConfig): PricePoint[] {
  const random = createRandom(hashSeed(config.symbol.toUpperCase()))
  const days = tradingDays(config.startDate, config.endDate)
  const drift = 0.0003 + (random() - 0.5) * 0.0008
  const volatility = 0.012 + random() * 0.014
  let price = 200 + random() * 800
  return days.map((date) => {
    price *= Math.exp(drift - (volatility * volatility) / 2 + volatility * gaussian(random))
    return { date, close: Number(price.toFixed(2)) }
  })
}

function computeRsi(prices: number[]): number[] {
  return prices.map((_, index) => {
    const window = prices.slice(Math.max(0, index - RSI_PERIOD), index + 1)
    let gains = 0
    let losses = 0
    for (let i = 1; i < window.length; i++) {
      const delta = window[i] - window[i - 1]
      if (delta > 0) gains += delta
      else losses -= delta
    }
    const count = Math.max(window.length - 1, 1)
    const rs = gains / count / (losses / count + 1e-10)
    return 100 - 100 / (1 + rs)
  })
}

function decide(rsi: number, params: StrategyParams): TradeAction {
  if (rsi <= params.buyBelow) return 'Buy'
  if (rsi >= params.sellAbove) return 'Sell'
  return 'Hold'
}

function simulate(
  series: PricePoint[],
  rsi: number[],
  params: StrategyParams,
  initialBalance: number,
): TradeRecord[] {
  let balance = initialBalance
  let holdings = 0
  const records: TradeRecord[] = []
  for (let step = 1; step < series.length; step++) {
    const price = series[step].close
    let action = decide(rsi[step - 1], params)
    if (action === 'Buy' && balance >= price) {
      holdings += 1
      balance -= price
    } else if (action === 'Sell' && holdings > 0) {
      holdings -= 1
      balance += price
    } else {
      action = 'Hold'
    }
    records.push({
      date: series[step].date,
      action,
      price,
      portfolioValue: balance + holdings * price,
      holdings,
      balance,
    })
  }
  return records
}

const yieldToUi = () => new Promise<void>((resolve) => setTimeout(resolve, 0))

export async function trainStrategy(
  config: TradingConfig,
  onProgress: (percent: number) => void,
): Promise<StrategyParams> {
  const series = generatePriceSeries(config)
  if (series.length < RSI_PERIOD + 2) {
    throw new Error('Date range is too short. Select at least one month of data.')
  }
  const rsi = computeRsi(series.map((point) => point.close))
  const resolution = Math.min(Math.max(Math.round(config.timesteps / 1000), 4), 40)
  const buyLevels = Array.from({ length: resolution }, (_, i) => 10 + (35 * i) / (resolution - 1))
  const sellLevels = Array.from({ length: resolution }, (_, i) => 55 + (35 * i) / (resolution - 1))

  let best: StrategyParams = { buyBelow: 30, sellAbove: 70 }
  let bestValue = -Infinity
  for (let i = 0; i < buyLevels.length; i++) {
    for (const sellAbove of sellLevels) {
      const params = { buyBelow: buyLevels[i], sellAbove }
      const records = simulate(series, rsi, params, config.initialBalance)
      const finalValue = records[records.length - 1].portfolioValue
      if (finalValue > bestValue) {
        bestValue = finalValue
        best = params
      }
    }
    onProgress(Math.round(((i + 1) / buyLevels.length) * 100))
    await yieldToUi()
  }
  return best
}

export interface BacktestResult {
  history: TradeRecord[]
  performance: PerformanceData
  chart: ChartSeries
}

export async function runBacktest(
  config: TradingConfig,
  params: StrategyParams,
): Promise<BacktestResult> {
  await yieldToUi()
  const series = generatePriceSeries(config)
  const rsi = computeRsi(series.map((point) => point.close))
  const history = simulate(series, rsi, params, config.initialBalance)

  const firstPrice = series[0].close
  const benchmarkUnits = config.initialBalance / firstPrice
  const finalBalance = history[history.length - 1].portfolioValue
  const lastPrice = series[series.length - 1].close

  let peak = config.initialBalance
  let maxDrawdown = 0
  for (const record of history) {
    peak = Math.max(peak, record.portfolioValue)
    maxDrawdown = Math.max(maxDrawdown, (peak - record.portfolioValue) / peak)
  }

  const lots: number[] = []
  let wins = 0
  let closed = 0
  for (const record of history) {
    if (record.action === 'Buy') lots.push(record.price)
    if (record.action === 'Sell' && lots.length) {
      const cost = lots.shift() as number
      closed += 1
      if (record.price > cost) wins += 1
    }
  }

  return {
    history,
    performance: {
      initialBalance: config.initialBalance,
      finalBalance,
      totalReturn: ((finalBalance - config.initialBalance) / config.initialBalance) * 100,
      buyAndHoldReturn: ((lastPrice - firstPrice) / firstPrice) * 100,
      maxDrawdown: maxDrawdown * 100,
      totalTrades: history.filter((record) => record.action !== 'Hold').length,
      winRate: closed ? (wins / closed) * 100 : 0,
    },
    chart: {
      labels: history.map((record) => record.date),
      portfolio: history.map((record) => Number(record.portfolioValue.toFixed(2))),
      benchmark: history.map((record) => Number((benchmarkUnits * record.price).toFixed(2))),
    },
  }
}
