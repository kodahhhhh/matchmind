import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath } from "node:url";
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { host: true, port: 5190, strictPort: true, fs: { allow: ["/home/ubuntu/hackathon/frontend/node_modules", "."] }, proxy: { "/api": "http://localhost:8020" } },
});
