<script lang="ts" module>
  export interface MenuItem {
    label?: string; icon?: any; onclick?: () => void; href?: string; danger?: boolean; disabled?: boolean; hint?: string;
    separator?: boolean; heading?: string; kbd?: string;
  }
</script>

<script lang="ts">
  // Menu suspenso: abre por botão, fecha com clique fora/Esc, sobe quando não cabe embaixo e segura a atualização automática.
  import { MoreHorizontal } from "@lucide/svelte";
  import type { Snippet } from "svelte";
  import { store } from "../lib/store.svelte";

  let { items, label = "Mais ações", align = "right", trigger = undefined, small = true }:
    { items: MenuItem[]; label?: string; align?: "left" | "right"; trigger?: Snippet; small?: boolean } = $props();
  let open = $state(false);
  let up = $state(false);
  let root: HTMLDivElement | undefined = $state();

  function toggle(e: MouseEvent) {
    e.stopPropagation();
    open = !open;
    if (open) {
      store.hold++;
      const r = root!.getBoundingClientRect();
      up = window.innerHeight - r.bottom < Math.min(360, items.length * 34 + 20);
    } else store.hold--;
  }
  function close() { if (open) { open = false; store.hold--; } }
  function run(it: MenuItem) {
    if (it.disabled) return;
    close();
    it.onclick?.();
  }
  $effect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => { if (!root?.contains(e.target as Node)) close(); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onKey); };
  });
</script>

<div class="menu" bind:this={root}>
  {#if trigger}
    <button class="trig-raw" onclick={toggle} aria-haspopup="menu" aria-expanded={open}>{@render trigger()}</button>
  {:else}
    <button class="btn ghost icon" class:sm={small} onclick={toggle} aria-label={label} title={label} aria-expanded={open}><MoreHorizontal size={16} /></button>
  {/if}
  {#if open}
    <div class="items {align}" class:up role="menu">
      {#each items as it, i (i)}
        {#if it.separator}<hr />
        {:else if it.heading}<div class="heading">{it.heading}</div>
        {:else if it.href}
          <a class="it" class:danger={it.danger} href={it.href} target="_blank" rel="noopener" onclick={close} role="menuitem">
            {#if it.icon}<it.icon size={15} />{/if}<span class="lbl">{it.label}</span><span class="ext">↗</span>
          </a>
        {:else}
          <button class="it" class:danger={it.danger} disabled={it.disabled} onclick={() => run(it)} role="menuitem" title={it.hint || ""}>
            {#if it.icon}<it.icon size={15} />{/if}<span class="lbl">{it.label}</span>
            {#if it.hint && it.disabled}<span class="hint">{it.hint}</span>{/if}
            {#if it.kbd}<span class="kbd">{it.kbd}</span>{/if}
          </button>
        {/if}
      {/each}
    </div>
  {/if}
</div>

<style>
  .menu { position: relative; display: inline-flex; }
  .trig-raw { all: unset; display: inline-flex; cursor: pointer; }
  .items { position: absolute; top: calc(100% + 6px); z-index: 60; min-width: 230px; max-width: 360px; padding: 5px; border-radius: 11px;
    background: var(--elevated); border: 1px solid var(--line-2); box-shadow: var(--shadow-3); transform-origin: top right;
    animation: menu-in 0.16s var(--ease-out); }
  .items.left { left: 0; transform-origin: top left; }
  .items.right { right: 0; }
  .items.up { top: auto; bottom: calc(100% + 6px); transform-origin: bottom right; }
  @keyframes menu-in { from { opacity: 0; transform: scale(0.96) translateY(-4px); } }
  .it { display: flex; align-items: center; gap: 10px; width: 100%; border: 0; background: none; color: var(--text); font: 500 13px/1.2 var(--font);
    padding: 8px 10px; border-radius: 7px; cursor: pointer; text-align: left; transition: background var(--t-fast), padding var(--t-fast) var(--ease); }
  .it:hover:not(:disabled) { background: var(--surface-3); padding-left: 12px; }
  .it:disabled { opacity: 0.45; cursor: not-allowed; }
  .it :global(svg) { color: var(--text-2); flex-shrink: 0; }
  .lbl { flex: 1; min-width: 0; }
  .ext { color: var(--muted); font-size: 11px; }
  .hint { font-size: 11px; color: var(--muted); }
  .danger { color: var(--bad); }
  .danger :global(svg) { color: var(--bad); }
  hr { border: 0; border-top: 1px solid var(--line); margin: 4px 2px; }
  .heading { font: 650 10.5px/1 var(--font); text-transform: uppercase; letter-spacing: 0.07em; color: var(--muted); padding: 9px 10px 5px; }
</style>
