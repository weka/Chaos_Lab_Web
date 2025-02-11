// client/vite.config.js
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Proxy any requests that start with /api to the Flask server
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
        // Uncomment the next line if your Flask API doesn't expect the /api prefix:
        // rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
});

