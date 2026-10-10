import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// A tela só existe dentro do app de desktop: é compilada para backend/static e carregada pela janela nativa.
export default defineConfig({
  plugins: [svelte()],
  base: "./",
  build: { outDir: "../backend/static", emptyOutDir: true, target: "safari16", chunkSizeWarningLimit: 900 },
});
