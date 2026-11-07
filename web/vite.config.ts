import react from "@vitejs/plugin-react";
import basicSsl from "@vitejs/plugin-basic-ssl";
import { defineConfig } from "vitest/config";
import { resolveApiProxyTarget } from "./config/api-proxy.ts";

const apiProxy = {
  "/api": {
    target: resolveApiProxyTarget(process.env.ST143_API_PROXY_TARGET),
    changeOrigin: false,
    xfwd: true,
  },
};

export default defineConfig({
  plugins: [react(), basicSsl()],
  // Secure cookies require HTTPS. Self-signed dev certs stay in node_modules/.vite.
  server: {
    host: "localhost",
    proxy: apiProxy,
  },
  preview: {
    host: "localhost",
    proxy: apiProxy,
  },
  build: { target: "es2022" },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "config/**/*.test.ts"],
    unstubGlobals: true,
  },
});
