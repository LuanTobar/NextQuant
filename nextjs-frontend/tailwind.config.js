/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        nq: {
          bg: '#0a0e17',
          card: '#111827',
          border: '#1f2937',
          accent: '#6366f1',
          green: '#10b981',
          red: '#ef4444',
          yellow: '#f59e0b',
          text: '#e5e7eb',
          muted: '#6b7280',
        },
      },
    },
  },
  plugins: [],
};
