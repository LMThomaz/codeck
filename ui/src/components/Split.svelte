<script lang="ts">
  // Lista + painel de detalhes lado a lado, cada um rolando por dentro. Em janela estreita o painel vira gaveta.
  import type { Snippet } from "svelte";
  import Drawer from "./Drawer.svelte";

  let { list, pane = undefined, paneKey = null, onclose = () => {}, paneWidth = "minmax(400px, 38%)", paneTitle = "Detalhes" }:
    { list: Snippet; pane?: Snippet; paneKey?: string | null; onclose?: () => void; paneWidth?: string; paneTitle?: string } = $props();
  let w = $state(window.innerWidth);
  const wide = $derived(w >= 1180);
</script>

<svelte:window bind:innerWidth={w} />

<div class="split" class:with={wide && pane && paneKey} style="--pane:{paneWidth}">
  <div class="card scroll list-card">{@render list()}</div>
  {#if wide && pane && paneKey}
    {#key paneKey}<aside class="card scroll pane">{@render pane()}</aside>{/key}
  {/if}
</div>
{#if !wide && pane && paneKey}
  <Drawer title={paneTitle} onclose={onclose} width={560}>{@render pane()}</Drawer>
{/if}

<style>
  .split { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr); gap: 14px; }
  .split.with { grid-template-columns: minmax(0, 1fr) var(--pane); }
  .scroll { min-height: 0; overflow: auto; overscroll-behavior: contain; }
  .pane { animation: pane-in 0.32s var(--ease-out) both; }
  @keyframes pane-in { from { opacity: 0; transform: translateX(12px); } }
</style>
