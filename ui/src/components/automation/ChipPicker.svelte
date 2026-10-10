<script lang="ts">
  // Escolha múltipla por chips: "qualquer" (lista vazia) + opções conhecidas + campo para digitar outra.
  import { Check, Lock } from "@lucide/svelte";
  let { value = $bindable([]), options = [], anyLabel = "Qualquer", placeholder = "Outro + Enter", locked = [] }:
    { value: string[]; options: string[]; anyLabel?: string; placeholder?: string; locked?: string[] } = $props();
  let text = $state("");
  const all = $derived([...new Set([...value, ...options])].filter(Boolean));
  const isLocked = (v: string) => locked.map(x => x.toLowerCase()).includes(v.toLowerCase());
  function toggle(v: string) { value = value.includes(v) ? value.filter(x => x !== v) : [...value, v]; }
  function add(e: KeyboardEvent) {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const v = text.trim();
    if (v && !value.includes(v)) value = [...value, v];
    text = "";
  }
</script>

<div class="chips">
  <button type="button" class="chip" class:on={!value.length} onclick={() => (value = [])}>{#if !value.length}<Check size={12} />{/if}{anyLabel}</button>
  {#each all as o (o)}
    <button type="button" class="chip" class:on={value.includes(o)} onclick={() => toggle(o)}>
      {#if value.includes(o)}<Check size={12} />{:else if isLocked(o)}<Lock size={11} />{/if}{o}
    </button>
  {/each}
</div>
<input class="input add" bind:value={text} onkeydown={add} {placeholder} />

<style>
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { display: inline-flex; align-items: center; gap: 5px; height: 28px; padding: 0 11px; border-radius: 99px; border: 1px solid var(--line-2);
    background: var(--surface-2); color: var(--text-2); font: 500 12.5px var(--font); cursor: pointer;
    transition: background var(--t), border-color var(--t), color var(--t), transform var(--t-fast) var(--ease); }
  .chip:hover { border-color: var(--line-3); color: var(--text); }
  .chip:active { transform: scale(0.96); }
  .chip.on { background: var(--accent); border-color: transparent; color: #fff; }
  .add { margin-top: 8px; height: 30px; font-size: 12.5px; }
</style>
