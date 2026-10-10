<script lang="ts">
  // Alerta fixo enquanto não há internet: o app continua mostrando o que já tinha lido e reconecta sozinho.
  import { WifiOff } from "@lucide/svelte";
  import { time } from "../lib/format";
  import { store } from "../lib/store.svelte";
  import { ui } from "../lib/ui.svelte";

  let was = false;
  $effect(() => {
    const off = store.offline;
    if (was && !off) ui.toast("Conexão restabelecida — dados atualizados");
    was = off;
  });
  async function retry() {
    await store.refresh();
    if (store.offline) ui.toast("Ainda sem conexão", "info");   // reconectou: o $effect acima já avisa
  }
</script>

{#if store.offline}
  <div class="off" role="status" aria-live="polite">
    <span class="ic"><WifiOff size={15} /></span>
    <span class="txt"><b>Sem conexão com a internet.</b> Mostrando o que já estava carregado{store.s?.lastPoll ? ` (lido às ${time(store.s.lastPoll)})` : ""}. Reconecta sozinho quando a rede voltar.</span>
    <button class="btn sm" disabled={store.refreshing} onclick={retry}>{store.refreshing ? "Tentando…" : "Tentar agora"}</button>
  </div>
{/if}

<style>
  .off { display: flex; align-items: center; gap: 10px; flex: none; margin: 10px 24px 0; padding: 9px 10px 9px 12px; border-radius: 11px;
    background: color-mix(in srgb, var(--warn) 13%, var(--bg)); border: 1px solid color-mix(in srgb, var(--warn) 38%, transparent); color: var(--text);
    font-size: 13px; animation: drop 0.4s var(--spring); }
  .ic { display: grid; place-items: center; width: 26px; height: 26px; border-radius: 8px; background: var(--warn-soft); color: var(--warn); flex: none;
    animation: breathe 2s var(--ease) infinite; }
  .txt { flex: 1; min-width: 0; color: var(--text-2); }
  .txt b { color: var(--text); font-weight: 600; }
  @keyframes drop { from { opacity: 0; transform: translateY(-10px); } }
  @keyframes breathe { 50% { opacity: 0.45; } }
</style>
