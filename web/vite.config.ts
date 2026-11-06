import react from "@vitejs/plugin-react";
import basicSsl from "@vitejs/plugin-basic-ssl";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), basicSsl()],
  // Secure cookies require HTTPS. Self-signed dev certs stay in node_modules/.vite.
  server: {
    host: "localhost",
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
        xfwd: true,
      },
    },
  },
  build: { target: "es2022" },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    unstubGlobals: true,
  },
});
