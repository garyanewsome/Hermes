import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const BACKEND = 'http://localhost:8001';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../static',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/chat': BACKEND,
      '/models': BACKEND,
      '/conversations': BACKEND,
      '/tasks': BACKEND,
      '/habits': BACKEND,
      '/health': BACKEND,
    },
  },
});
