import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import { createVuetify } from 'vuetify'

export default createVuetify({
  theme: {
    defaultTheme: 'nepseDark',
    themes: {
      nepseDark: {
        dark: true,
        colors: {
          background: '#0f1420',
          surface: '#171e2e',
          primary: '#3b82f6',
          secondary: '#8b5cf6',
          success: '#22c55e',
          error: '#ef4444',
          warning: '#f59e0b',
          info: '#06b6d4',
        },
      },
    },
  },
  defaults: {
    VCard: { rounded: 'lg', elevation: 0, border: true },
    VTextField: { variant: 'outlined', density: 'comfortable', hideDetails: 'auto' },
    VSelect: { variant: 'outlined', density: 'comfortable', hideDetails: 'auto' },
    VBtn: { rounded: 'lg' },
  },
})
