import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyRequest) => {
            if (!proxyRequest.hasHeader("origin")) {
              proxyRequest.setHeader("Origin", "http://localhost:5173");
            }
          });
        },
      },
    },
  },
});
