<script lang="ts">
  // "+ Projeto": escolher um repositório da sua lista para abrir como projeto, filtrando pelo nome (Enter abre o 1º).
  import { FolderGit2, FolderOpen, Plus, Search } from "@lucide/svelte";
  import { tick } from "svelte";
  import { pickFolder } from "../../lib/native";
  import { repos } from "../../lib/repos.svelte";
  import { go } from "../../lib/router.svelte";
  import { ui } from "../../lib/ui.svelte";
  import { work } from "../../lib/work.svelte";
  import ProviderIcon from "../ProviderIcon.svelte";

  let { label = "Projeto", big = false }: { label?: string; big?: boolean } = $props();
  let open = $state(false);
  let q = $state("");
  let hi = $state(0);
  let input: HTMLInputElement | undefined = $state();
  let root: HTMLDivElement | undefined = $state();
  const isWt = (p: string) => /[\\/]\.worktrees[\\/]/.test(p);
  const list = $derived.by(() => {
    const t = q.trim().toLowerCase();
    return repos.local.filter(r => r.exists && !isWt(r.path) && !work.projects.some(x => x.id === r.id)
      && (!t || r.name.toLowerCase().includes(t) || (r.slug || "").toLowerCase().includes(t)))
      .sort((a, b) => (t ? Number(!a.name.toLowerCase().startsWith(t)) - Number(!b.name.toLowerCase().startsWith(t)) : 0) || a.name.localeCompare(b.name)).slice(0, 60);
  });
  $effect(() => { void q; hi = 0; });
  // fixo na janela: a faixa de abas de projeto rola na horizontal e cortava a lista; abre para baixo e, sem espaço, para cima
  let pos = $state("");
  function place() {
    const b = root?.getBoundingClientRect();
    if (!b) return;
    const W = 380, M = 8, vw = window.innerWidth, vh = window.innerHeight;
    const left = Math.max(M, Math.min(b.left, vw - W - M));
    const below = vh - b.bottom - M * 2, above = b.top - M * 2;
    const down = below >= 260 || below >= above;
    const max = Math.max(160, Math.min(480, down ? below : above));
    pos = `left:${left}px;width:${Math.min(W, vw - M * 2)}px;max-height:${max}px;` + (down ? `top:${b.bottom + 6}px` : `bottom:${vh - b.top + 6}px`);
  }
  async function toggle() {
    open = !open;
    if (open) { q = ""; place(); if (!repos.loaded) repos.load(false); await tick(); input?.focus(); }
  }
  $effect(() => {
    if (!open) return;
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  });
  async function choose(id: string) {
    open = false;
    try { const pid = await work.open(id); go("/work/" + pid, "soft"); } catch (e) { ui.error(e); }
  }
  async function folder() {
    open = false;
    const f = await pickFolder("Pasta do projeto (repositório Git)");
    if (f) { try { const pid = await work.open(undefined, f); go("/work/" + pid, "soft"); } catch (e) { ui.error(e); } }
  }
  function key(e: KeyboardEvent) {
    if (e.key === "ArrowDown") { hi = Math.min(hi + 1, list.length - 1); e.preventDefault(); }
    else if (e.key === "ArrowUp") { hi = Math.max(hi - 1, 0); e.preventDefault(); }
    else if (e.key === "Enter" && list[hi]) { e.preventDefault(); choose(list[hi].id); }
    else if (e.key === "Escape") open = false;
  }
  $effect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => { if (!root?.contains(e.target as Node)) open = false; };
    document.addEventListener("mousedown", down, true);
    return () => document.removeEventListener("mousedown", down, true);
  });
</script>

<div class="pp" bind:this={root}>
  <button class="btn sm {big ? 'primary' : 'ghost addp'}" onclick={toggle} aria-expanded={open}>{#if big}<FolderGit2 size={14} />{:else}<Plus size={14} />{/if} {label}</button>
  {#if open}
    <div class="pop card" role="dialog" aria-label="Abrir projeto" style={pos}>
      <label class="f"><Search size={14} /><input bind:this={input} bind:value={q} placeholder="Filtrar repositórios pelo nome…" onkeydown={key} /></label>
      <div class="list">
        {#each list as r, i (r.id)}
          <button class="it" class:hi={i === hi} onmouseenter={() => (hi = i)} onclick={() => choose(r.id)}>
            <ProviderIcon provider={r.provider || null} size={13} /><span class="grow"><b class="ell">{r.name}</b><span class="tiny muted ell">{r.path.replace(/^\/Users\/[^/]+/, "~")}</span></span>
          </button>
        {:else}<div class="none">{q ? `Nada com “${q}”.` : "Todos os repositórios já estão abertos."}</div>{/each}
      </div>
      <button class="it more" onclick={folder}><FolderOpen size={14} /> Abrir outra pasta…</button>
    </div>
  {/if}
</div>

<style>
  .pp { position: relative; display: inline-flex; }
  .pop { position: fixed; z-index: 80; padding: 8px; display: flex; flex-direction: column; gap: 6px; box-shadow: var(--shadow-3);
    animation: pop-in 0.16s var(--ease-out); }
  @keyframes pop-in { from { opacity: 0; transform: scale(0.98); } }
  .f { display: flex; align-items: center; gap: 8px; height: 32px; padding: 0 10px; border-radius: 8px; border: 1px solid var(--accent-line); background: var(--bg-2); color: var(--muted); }
  .f input { flex: 1; min-width: 0; border: 0; outline: none; background: none; color: var(--text); font: 13px var(--font); }
  .f, .more { flex: none; }
  .list { display: grid; align-content: start; gap: 1px; flex: 1; min-height: 0; overflow: auto; }
  .it { display: flex; align-items: center; gap: 9px; width: 100%; padding: 6px 8px; border: 0; border-radius: 7px; background: none; color: var(--text-2);
    font: 13px var(--font); text-align: left; cursor: pointer; }
  .it.hi, .it:hover { background: var(--accent-soft); color: var(--text); }
  .it .grow { display: grid; min-width: 0; flex: 1; }
  .it b { font-weight: 600; color: var(--text); }
  .more { border-top: 1px solid var(--line); border-radius: 0 0 7px 7px; color: var(--accent); padding-top: 9px; }
  .none { padding: 10px; font-size: 12.5px; color: var(--muted); }
</style>
