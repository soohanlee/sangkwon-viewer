import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api 요청은 FastAPI(기본 8000)로 프록시
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5190,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
