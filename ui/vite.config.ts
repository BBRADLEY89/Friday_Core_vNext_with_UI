import { defineConfig } from "vite";
export default defineConfig({
  server: { host: "0.0.0.0", port: 5173 },
  preview: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    allowedHosts: ["friday-server.tailc203b0.ts.net", /\.ts\.net$/],
  },
});
