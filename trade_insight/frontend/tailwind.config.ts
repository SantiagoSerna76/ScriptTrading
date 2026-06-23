import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        'chart-green': '#10b981',
        'chart-red': '#ef4444',
        'chart-blue': '#3b82f6',
      },
    },
  },
  plugins: [],
}

export default config
