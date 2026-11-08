export type TradeAction = 'Hold' | 'Buy' | 'Sell'

export interface TradingConfig {
  symbol: string
  startDate: string
  endDate: string
  initialBalance: number
  timesteps: number
}

export interface PricePoint {
  date: string
  close: number
}

export interface StrategyParams {
  buyBelow: number
  sellAbove: number
}

export interface TradeRecord {
  date: string
  action: TradeAction
  price: number
  portfolioValue: number
  holdings: number
  balance: number
}

export interface PerformanceData {
  initialBalance: number
  finalBalance: number
  totalReturn: number
  buyAndHoldReturn: number
  maxDrawdown: number
  totalTrades: number
  winRate: number
}

export interface ChartSeries {
  labels: string[]
  portfolio: number[]
  benchmark: number[]
}
