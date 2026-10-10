<script lang="ts">
  // "Clonar em…": escolhe entre as pastas de trabalho (as de Preferências e as que já têm clones, com quantos cada uma
  // tem) ou outra pasta. O repositório vai para <pasta>/<nome>. "Lembrar" grava a escolha na conta/catálogo/tag.
  import { Check, Download, Folder, FolderPlus } from "@lucide/svelte";
  import { get } from "../../lib/api";
  import { pickFolder } from "../../lib/native";
  import { ui } from "../../lib/ui.svelte";

  type Target = { path: string; short: string; label: string; count: number; configured: boolean };
  const a = $derived(ui.cloneAsk!);
  let targets = $state<Target[]>([]);
  let chosen = $state<string | null>(null);
  let remember = $state(true);
  const home = (p: string) => p.replace(/^\/Users\/[^/]+|^C:\\Users\\[^\\]+/i, "~");

  $effect(() => {
    const cur = a.current;
    get<{ targets: Target[] }>("clone-targets").then(r => {
      targets = r.targets;
      if (cur && !targets.some(t => t.path === cur)) targets = [{ path: cur, short: home(cur), label: cur.split(/[\\/]/).pop() || cur, count: 0, configured: false }, ...targets];
      chosen = cur || targets[0]?.path || null;
      remember = !cur;
    }).catch(e => ui.error(e));
  });
  async function other() {
    const p = await pickFolder("Pasta onde clonar");
    if (!p) return;
    if (!targets.some(t => t.path === p)) targets = [{ path: p, short: home(p), label: p.split(/[\\/]/).pop() || p, count: 0, configured: false }, ...targets];
    chosen = p;
  }
  const sep = (p: string) => (p.includes("\\") ? "\\" : "/");
</script>

<div class="scrim" role="presentation" onclick={() => a.resolve(null)} onkeydown={(e) => e.key === "Escape" && a.resolve(null)}>
  <div class="dlg card" role="dialog" aria-modal="true" aria-label={a.title} tabindex="-1" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
    <h3>{a.title}</h3>
    <p class="small muted">{a.names.length === 1 ? "Escolha a pasta — o repositório vai para uma subpasta com o nome dele." : `${a.names.length} repositórios, cada um numa subpasta com o próprio nome.`}</p>
    <div class="list">
      {#each targets as t (t.path)}
        <button class="opt" class:on={chosen === t.path} onclick={() => (chosen = t.path)}>
          <span class="radio">{#if chosen === t.path}<Check size={11} strokeWidth={3} />{/if}</span>
          <Folder size={15} />
          <span class="grow"><b>{t.label}</b><span class="small muted mono ell">{t.short}</span></span>
          <span class="tiny muted">{t.count ? `${t.count} repo${t.count > 1 ? "s" : ""}` : t.configured ? "pasta de trabalho" : ""}</span>
        </button>
      {:else}
        <div class="small muted">Nenhuma pasta conhecida ainda — escolha uma.</div>
      {/each}
      <button class="opt add" onclick={other}><FolderPlus size={15} /> Outra pasta…</button>
    </div>
    {#if chosen}<div class="dest small">Vai para <span class="mono">{home(chosen)}{sep(chosen)}{a.names.length === 1 ? a.names[0] : "<nome>"}</span></div>{/if}
    <div class="foot">
      {#if a.rememberLabel}<label class="rem"><input type="checkbox" bind:checked={remember} /> Usar sempre para {a.rememberLabel}</label>{/if}
      <span class="spacer"></span>
      <button class="btn" onclick={() => a.resolve(null)}>Cancelar</button>
      <button class="btn primary" disabled={!chosen} onclick={() => a.resolve({ base: chosen!, remember: !!a.rememberLabel && remember })}><Download size={14} /> Clonar</button>
    </div>
  </div>
</div>

<style>
  .scrim { position: fixed; inset: 0; z-index: 150; display: grid; place-items: center; background: rgba(5, 7, 12, 0.55); backdrop-filter: blur(3px); animation: fade 0.18s; }
  .dlg { width: min(560px, 92vw); max-height: 86vh; display: flex; flex-direction: column; gap: 10px; padding: 20px; box-shadow: var(--shadow-3); animation: pop 0.32s var(--spring); }
  h3 { margin: 0; font-size: 16px; }
  p { margin: 0; }
  .list { display: grid; gap: 4px; overflow: auto; min-height: 0; }
  .opt { display: flex; align-items: center; gap: 10px; width: 100%; padding: 9px 11px; border-radius: 10px; border: 1px solid var(--line); background: var(--surface-2);
    color: var(--text-2); font: 13px var(--font); text-align: left; cursor: pointer; transition: border-color var(--t), background var(--t); }
  .opt:hover { border-color: var(--line-3); }
  .opt.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .opt .grow { display: grid; min-width: 0; flex: 1; }
  .opt b { color: var(--text); font-weight: 600; }
  .radio { width: 16px; height: 16px; border-radius: 50%; border: 1.5px solid var(--line-3); display: grid; place-items: center; flex: none; color: #fff; }
  .on .radio { background: var(--accent); border-color: var(--accent); }
  .opt.add { border-style: dashed; color: var(--accent); background: none; }
  .dest { padding: 8px 10px; border-radius: 8px; background: var(--bg-2); color: var(--text-2); overflow-wrap: anywhere; }
  .foot { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
  .rem { display: flex; align-items: center; gap: 7px; font-size: 12.5px; color: var(--text-2); cursor: pointer; }
  .spacer { flex: 1; }
</style>
