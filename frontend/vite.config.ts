import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: 5173,
    allowedHosts: [".ts.net"], // Tailscale MagicDNS
    proxy: { "/api": "http://localhost:8000" },
  },
});
