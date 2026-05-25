/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        sidebar: '#0f172a',
        'sidebar-hover': '#1e293b',
      },
    },
  },
  plugins: [],
}
