import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/**
 * The dev server proxies `/api` to the backend so the browser sees a single
 * origin and cookies/CORS stay out of the way. In production nginx does the
 * same thing against the `backend` service.
 */
const apiTarget = process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8010";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
});
