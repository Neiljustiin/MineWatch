import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev: `npm run dev` proxies API + imagery to the FastAPI server on :8000.
// Prod: `npm run build` -> dist/ is served by FastAPI itself (one port).
const API = process.env.MINEWATCH_API || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  build: { outDir: 'dist', assetsDir: 'static', sourcemap: false },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: { '/api': API, '/assets': API },
  },
});
