/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx}",
    "./src/components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        chart: {
          green: "#10b981",
          red: "#ef4444",
          blue: "#3b82f6",
          yellow: "#f59e0b",
        },
      },
    },
  },
  plugins: [],
};
