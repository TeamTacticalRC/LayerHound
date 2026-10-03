import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // LAYERHOUND_API points the dev server at another LayerHound, e.g. the board:
  //   LAYERHOUND_API=http://layerhound.local npm run dev
  server: { proxy: { '/api': process.env.LAYERHOUND_API || 'http://127.0.0.1:8000' } },
});
