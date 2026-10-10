<script lang="ts">
  // Ícones das plataformas (GitHub Octicon "mark-github" e o símbolo do Azure DevOps), em uma cor.
  let { provider, size = 14 }: { provider?: string | null; size?: number } = $props();
</script>

{#if provider === "github"}
  <svg class="pi gh" width={size} height={size} viewBox="0 0 16 16" aria-label="GitHub"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8Z"/></svg>
{:else if provider === "azure"}
  <svg class="pi az" width={size} height={size} viewBox="0 0 18 18" aria-label="Azure DevOps"><path fill="currentColor" d="M17 4v9.74l-4 3.28-6.2-2.26V17l-3.51-4.59 10.23.8V4.44zm-3.41.49L7.85 1v2.29L2.58 4.84 1 6.87v4.61l2.26 1V6.57z"/></svg>
{:else}
  <svg class="pi git" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-label="Git"><circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="9" r="2.5"/><path d="M6 8.5v7M18 11.5c0 3-3 4.5-9.5 5"/></svg>
{/if}

<style>
  .pi { flex-shrink: 0; display: inline-block; vertical-align: -2px; }
  .gh { color: var(--github); }
  .az { color: var(--azure); }
  .git { color: #f0726f; }
</style>
