/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        neon: {
          blue: '#00f0ff',
          purple: '#8000ff',
          pink: '#ff007f',
        }
      },
      fontFamily: {
        'mono': ['Monaco', 'Menlo', 'Ubuntu Mono', 'monospace'],
      },
      boxShadow: {
        'neon-blue': '0 0 20px #00f0ff, 0 0 40px #00f0ff, 0 0 60px #00f0ff',
        'neon-purple': '0 0 20px #8000ff, 0 0 40px #8000ff, 0 0 60px #8000ff',
        'neon-pink': '0 0 20px #ff007f, 0 0 40px #ff007f, 0 0 60px #ff007f',
      }
    },
  },
  plugins: [],
}