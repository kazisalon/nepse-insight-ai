const currency = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export const formatCurrency = (value: number) => `Rs. ${currency.format(value)}`

export const formatPercent = (value: number) => `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
