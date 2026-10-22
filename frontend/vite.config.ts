import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // em desenvolvimento a API roda em :8000; em produção, VITE_API_URL=https://api.360cash.tech
    proxy: { "/v1": "http://localhost:8000" },
  },
  build: { sourcemap: false },
});
