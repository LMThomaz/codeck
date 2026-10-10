import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// A tela é servida pelo backend (backend/static); em desenvolvimento, `npm run dev` repassa /api para ele.
export default defineConfig({
  plugins: [svelte()],
  base: "./",
  build: { outDir: "../backend/static", emptyOutDir: true, target: "safari16", chunkSizeWarningLimit: 900 },
  server: {
    port: 47823,
    proxy: { "/api": { target: `http://127.0.0.1:${process.env.COMMITDECK_PORT || 47822}`, changeOrigin: false } },
  },
});
