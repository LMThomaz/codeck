<script lang="ts">
  // Versão nova no canal: aviso dispensável; versão obrigatória (required): bloqueia até atualizar.
  import { ArrowUpCircle } from "@lucide/svelte";
  import { post } from "../lib/api";
  import { send } from "../lib/native";
  import { store } from "../lib/store.svelte";
  import { ui } from "../lib/ui.svelte";
  let busy = $state(false);
  let dismissed = $state(false);
  const u = $derived(store.s?.update);

  async function run() {
    busy = true;
    try {
      const r = await post<{ path: string }>("update/download");
      ui.toast("Instalando a versão nova — o app reabre sozinho", "info");
      if (!send({ type: "install", path: r.path })) ui.toast("Instalação automática só no app instalado", "error");
    } catch (e) { ui.error(e); }
    busy = false;
  }
  window.checkUpdate = async (manual = false) => {
    try {
      const r = await post("update/check");
      if (manual) ui.toast(r.disabled ? "Atualização automática só no app instalado" : r.available ? `Versão ${r.version} disponível` : r.error ? "Não consegui consultar agora" : "Você está na versão mais nova", r.available ? "info" : "ok");
      store.load();
    } catch (e) { if (manual) ui.error(e); }
  };
</script>

{#if u?.available && u.required}
  <div class="block">
    <div class="card box">
      <ArrowUpCircle size={34} />
      <h2>Atualização obrigatória</h2>
      <p>A versão {u.version} (build {u.build}) é necessária para continuar.{#if u.notes} {u.notes}{/if}</p>
      <button class="btn primary lg" disabled={busy} onclick={run}>{busy ? "Baixando…" : "Atualizar agora"}</button>
    </div>
  </div>
{:else if u?.available && !dismissed}
  <div class="bar">
    <ArrowUpCircle size={16} />
    <span><b>Versão {u.version}</b> disponível{#if u.notes} — {u.notes}{/if}</span>
    <span class="spacer"></span>
    <button class="btn sm ghost" onclick={() => (dismissed = true)}>Depois</button>
    <button class="btn sm primary" disabled={busy} onclick={run}>{busy ? "Baixando…" : "Atualizar agora"}</button>
  </div>
{/if}

<style>
  .bar { display: flex; align-items: center; gap: 10px; margin: 12px 24px 0; padding: 9px 12px 9px 14px; border-radius: 12px; background: var(--accent-soft);
    border: 1px solid var(--accent-line); color: var(--text); font-size: 13px; animation: rise 0.4s var(--ease-out); }
  .bar :global(svg) { color: var(--accent); }
  .block { position: fixed; inset: 0; z-index: 95; display: grid; place-items: center; background: rgba(5, 7, 12, 0.75); backdrop-filter: blur(6px); animation: fade 0.2s both; }
  .box { width: min(440px, 90vw); padding: 28px; text-align: center; animation: pop 0.5s var(--spring) both; }
  .box :global(svg) { color: var(--accent); }
  h2 { margin: 10px 0 6px; }
  p { color: var(--text-2); margin: 0 0 18px; }
</style>
