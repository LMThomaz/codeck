<script lang="ts" module>
  export interface MenuItem {
    label?: string; icon?: any; onclick?: () => void; href?: string; danger?: boolean; disabled?: boolean; hint?: string;
    separator?: boolean; heading?: string; kbd?: string;
  }
</script>

<script lang="ts">
  // Botão que abre um menu. O menu em si é desenhado pelo MenuHost (por cima de tudo); aqui só fica o gatilho.
  // O "⋯" de uma linha também responde ao clique direito na LINHA inteira (lista, regra, branch…): mesmo menu, no cursor.
  // Menus com gatilho próprio (ex.: "Modelos", troca de branch) não pegam o clique direito de ninguém.
  import { MoreHorizontal } from "@lucide/svelte";
  import type { Snippet } from "svelte";
  import { ui } from "../lib/ui.svelte";

  let { items, label = "Mais ações", align = "right", trigger = undefined, small = true }:
    { items: MenuItem[]; label?: string; align?: "left" | "right"; trigger?: Snippet; small?: boolean } = $props();
  const me = Symbol("menu");
  const open = $derived(ui.menu?.owner === me);
  let root: HTMLElement | undefined = $state();

  const ROW = ".list-row, .rule, .row, .b, tr, [data-menu-row]";
  $effect(() => {
    if (trigger || !root) return;
    const row = root.parentElement?.closest<HTMLElement>(ROW);
    if (!row) return;
    const onCtx = (e: MouseEvent) => {
      if (e.defaultPrevented || (e.target as HTMLElement).closest("input, textarea, [contenteditable]")) return;
      ui.contextMenu(e, items);
    };
    row.addEventListener("contextmenu", onCtx);
    return () => row.removeEventListener("contextmenu", onCtx);
  });

  function toggle(e: MouseEvent) {
    e.stopPropagation();
    if (open) return ui.closeMenu();
    const r = root!.getBoundingClientRect();
    ui.openMenu({ items, anchor: { left: r.left, right: r.right, top: r.top, bottom: r.bottom }, align, owner: me });
  }
</script>

<span class="menu" class:open bind:this={root}>
  {#if trigger}
    <button class="trig-raw" onclick={toggle} aria-haspopup="menu" aria-expanded={open}>{@render trigger()}</button>
  {:else}
    <button class="btn ghost icon" class:sm={small} onclick={toggle} aria-label={label} title={label} aria-haspopup="menu" aria-expanded={open}><MoreHorizontal size={16} /></button>
  {/if}
</span>

<style>
  .menu { position: relative; display: inline-flex; }
  .trig-raw { all: unset; display: inline-flex; cursor: pointer; }
  .open .btn { background: var(--surface-3); color: var(--text); }
</style>
