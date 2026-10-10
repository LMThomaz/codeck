<script lang="ts">
  // Controle segmentado com o fundo do item ativo deslizando entre as opções.
  let { options, value = $bindable(), onchange = undefined, size = "md" }:
    { options: { value: string; label: string; count?: number | string; icon?: any }[]; value: string; onchange?: (v: string) => void; size?: "sm" | "md" } = $props();
  let el: HTMLDivElement | undefined = $state();
  let ind = $state({ x: 0, w: 0, ready: false });

  $effect(() => {
    void value; void options.length;
    requestAnimationFrame(() => {
      const b = el?.querySelector<HTMLButtonElement>("button.on");
      if (b) ind = { x: b.offsetLeft, w: b.offsetWidth, ready: true };
    });
  });
</script>

<div class="seg {size}" bind:this={el} role="tablist">
  <span class="ind" class:ready={ind.ready} style="transform:translateX({ind.x}px);width:{ind.w}px"></span>
  {#each options as o (o.value)}
    <button class:on={o.value === value} role="tab" aria-selected={o.value === value}
      onclick={() => { if (o.value !== value) { value = o.value; onchange?.(o.value); } }}>
      {#if o.icon}<o.icon size={13} />{/if}
      {o.label}{#if o.count !== undefined}<span class="n">{o.count}</span>{/if}
    </button>
  {/each}
</div>

<style>
  .seg { position: relative; display: inline-flex; padding: 3px; gap: 2px; border-radius: 10px; background: var(--bg-2); border: 1px solid var(--line); flex-shrink: 0; }
  .ind { position: absolute; top: 3px; bottom: 3px; left: 0; border-radius: 7px; background: var(--surface-3); box-shadow: var(--shadow-1), 0 0 0 1px var(--line-2);
    opacity: 0; transition: transform 0.36s var(--ease-out), width 0.36s var(--ease-out), opacity 0.2s; }
  .ind.ready { opacity: 1; }
  button { position: relative; z-index: 1; border: 0; background: none; color: var(--text-2); font: 550 12.5px/1 var(--font); height: 26px; padding: 0 11px;
    border-radius: 7px; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; transition: color var(--t) var(--ease); }
  button:hover { color: var(--text); }
  button.on { color: var(--text); }
  .sm button { height: 22px; padding: 0 9px; font-size: 12px; }
  .n { font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums; }
  button.on .n { color: var(--accent); }
</style>
