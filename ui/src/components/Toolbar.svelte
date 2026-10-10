<script lang="ts">
  import { Search } from "@lucide/svelte";
  import type { Snippet } from "svelte";
  let { query = $bindable(""), placeholder = "Buscar…", children = undefined, left = undefined }:
    { query?: string; placeholder?: string; children?: Snippet; left?: Snippet } = $props();
</script>

<div class="toolbar">
  {#if left}{@render left()}{/if}
  <label class="search"><Search size={14} /><input bind:value={query} {placeholder} /></label>
  {#if children}{@render children()}{/if}
</div>

<style>
  .toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; flex: none; }
  .search { flex: 1 1 240px; display: flex; align-items: center; gap: 8px; height: 32px; padding: 0 11px; border-radius: 9px; border: 1px solid var(--line-2);
    background: var(--bg-2); color: var(--muted); transition: border-color var(--t), box-shadow var(--t); }
  .search:focus-within { border-color: var(--accent); box-shadow: var(--ring); }
  .search input { flex: 1; min-width: 0; border: 0; outline: none; background: none; color: var(--text); font: 13px var(--font); }
</style>
