import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  preview: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    // Allow the exact tailnet host and any *.ts.net just in case:
    allowedHosts: ['friday-server.tailc203b0.ts.net', /\.ts\.net$/],
  },
  server: {
    port: 5173,
    host: '0.0.0.0'
  },
  build: {
    outDir: 'dist'
  }
})
