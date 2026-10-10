<script lang="ts">
  // Desenha o menu aberto (botão "⋯" ou clique direito) por cima de tudo, em coordenadas de tela: nunca fica por baixo
  // de painel nem é recortado por rolagem. Fecha com clique fora, Esc, rolagem, redimensionar ou ao escolher um item.
  // Setas ↑/↓ navegam, Enter escolhe. Enquanto aberto, segura a atualização automática (a lista não muda por baixo).
  import { tick, untrack } from "svelte";
  import type { MenuItem } from "./Menu.svelte";
  import { store } from "../lib/store.svelte";
  import { ui } from "../lib/ui.svelte";

  let el: HTMLDivElement | undefined = $state();
  let pos = $state({ x: 0, y: 0, origin: "top left", ready: false });

  $effect(() => {
    const m = ui.menu;
    if (!m) return;
    untrack(() => { store.hold++; pos = { ...pos, ready: false }; });
    tick().then(() => {
      if (!el || ui.menu !== m) return;
      const w = el.offsetWidth, h = el.offsetHeight, pad = 8, vw = window.innerWidth, vh = window.innerHeight;
      const point = m.anchor.left === m.anchor.right && m.anchor.top === m.anchor.bottom;
      let x = m.align === "right" && !point ? m.anchor.right - w : m.anchor.left;
      let y = m.anchor.bottom + (point ? 2 : 6);
      const up = y + h > vh - pad && m.anchor.top - h - 6 > pad;
      if (up) y = m.anchor.top - h - (point ? 2 : 6);
      x = Math.max(pad, Math.min(x, vw - w - pad));
      y = Math.max(pad, Math.min(y, vh - h - pad));
      pos = { x, y, origin: `${up ? "bottom" : "top"} ${m.align === "right" && !point ? "right" : "left"}`, ready: true };
      el.querySelector<HTMLElement>(".it:not(:disabled)")?.focus({ preventScroll: true });
    });
    const close = () => ui.closeMenu();
    const onDown = (e: MouseEvent) => { if (!el?.contains(e.target as Node)) close(); };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") return close();
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      e.preventDefault();
      const its = [...(el?.querySelectorAll<HTMLElement>(".it:not(:disabled)") || [])];
      const i = its.indexOf(document.activeElement as HTMLElement);
      its[(i + (e.key === "ArrowDown" ? 1 : -1) + its.length) % its.length]?.focus();
    };
    const onScroll = (e: Event) => { if (!el?.contains(e.target as Node)) close(); };
    document.addEventListener("mousedown", onDown, true);
    document.addEventListener("contextmenu", onDown, true);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", close);
    window.addEventListener("blur", close);
    return () => {
      untrack(() => store.hold--);
      document.removeEventListener("mousedown", onDown, true);
      document.removeEventListener("contextmenu", onDown, true);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", close);
      window.removeEventListener("blur", close);
    };
  });

  function run(it: MenuItem) {
    if (it.disabled) return;
    ui.closeMenu();
    it.onclick?.();
  }
</script>

{#if ui.menu}
  {#key ui.menu}
    <div class="items" class:ready={pos.ready} bind:this={el} role="menu" tabindex="-1" style="left:{pos.x}px;top:{pos.y}px;transform-origin:{pos.origin}"
      oncontextmenu={(e) => e.preventDefault()}>
      {#each ui.menu.items as it, i (i)}
        {#if it.separator}<hr />
        {:else if it.heading}<div class="heading">{it.heading}</div>
        {:else if it.href}
          <a class="it" class:danger={it.danger} href={it.href} target="_blank" rel="noopener" onclick={() => ui.closeMenu()} role="menuitem">
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
  {/key}
{/if}

<style>
  .items { position: fixed; z-index: 200; min-width: 230px; max-width: 380px; max-height: min(70vh, 560px); overflow: auto; padding: 5px; border-radius: 11px;
    background: var(--elevated); border: 1px solid var(--line-2); box-shadow: var(--shadow-3); visibility: hidden; }
  .items.ready { visibility: visible; animation: menu-in 0.16s var(--ease-out); }
  @keyframes menu-in { from { opacity: 0; transform: scale(0.96); } }
  .it { display: flex; align-items: center; gap: 10px; width: 100%; border: 0; background: none; color: var(--text); font: 500 13px/1.2 var(--font);
    padding: 8px 10px; border-radius: 7px; cursor: pointer; text-align: left; outline: none; transition: background var(--t-fast), padding var(--t-fast) var(--ease); }
  .it:hover:not(:disabled), .it:focus-visible:not(:disabled), .it:focus:not(:disabled) { background: var(--surface-3); padding-left: 12px; }
  .it:disabled { opacity: 0.45; cursor: not-allowed; }
  .it :global(svg) { color: var(--text-2); flex-shrink: 0; }
  .lbl { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ext { color: var(--muted); font-size: 11px; }
  .hint { font-size: 11px; color: var(--muted); }
  .danger { color: var(--bad); }
  .danger :global(svg) { color: var(--bad); }
  hr { border: 0; border-top: 1px solid var(--line); margin: 4px 2px; }
  .heading { font: 650 10.5px/1 var(--font); text-transform: uppercase; letter-spacing: 0.07em; color: var(--muted); padding: 9px 10px 5px; }
</style>
