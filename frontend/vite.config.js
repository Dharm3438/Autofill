import process from 'node:process'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ command, mode }) => {
  // A production build must know where the backend is: without VITE_API_URL the
  // app would call /api on the frontend's own static host and get index.html
  // back instead of data. Fail the build loudly instead.
  if (command === 'build') {
    const env = { ...loadEnv(mode, process.cwd(), 'VITE_'), ...process.env }
    if (!env.VITE_API_URL) {
      throw new Error(
        'VITE_API_URL is not set. Set it to the backend URL (e.g. https://autofill-blgf.onrender.com) ' +
        'in the Cloudflare Pages project settings, or in frontend/.env for a local build.',
      )
    }
  }

  return {
    plugins: [react(), tailwindcss()],
    // Development: with VITE_API_URL unset, the app calls /api and this
    // forwards it to the local backend.
    server: {
      proxy: {
        '/api': {
          target: 'http://localhost:8080',
          changeOrigin: true,
        },
      },
    },
  }
})
