import { defineConfig } from "vite";
// import react from "@vitejs/plugin-react"; // uncomment if you're using it

export default defineConfig({
  // plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
  },
  preview: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    // allow your exact TS host + any *.ts.net just in case
    allowedHosts: ["friday-server.tailc203b0.ts.net", /\.ts\.net$/],
  },
});

