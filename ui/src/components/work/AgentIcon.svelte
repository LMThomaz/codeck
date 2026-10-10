<script lang="ts">
  // Marca de cada agente de IA (glifos simples, só para identificar de relance).
  let { provider, size = 16 }: { provider: string | null | undefined; size?: number } = $props();
</script>

{#if provider === "claude"}
  <svg width={size} height={size} viewBox="0 0 24 24" aria-label="Claude"><g fill="#D97757">{#each [0, 30, 60, 90, 120, 150] as r (r)}<rect x="11" y="2.5" width="2" height="19" rx="1" transform="rotate({r} 12 12)" />{/each}</g></svg>
{:else if provider === "codex"}
  <svg width={size} height={size} viewBox="0 0 24 24" aria-label="Codex"><rect x="2" y="2" width="20" height="20" rx="6" fill="var(--text)" /><path d="M7.5 9l3 3-3 3M12.5 15.5h4" stroke="var(--bg)" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round" /></svg>
{:else if provider === "cursor"}
  <svg width={size} height={size} viewBox="0 0 24 24" aria-label="Cursor"><path d="M12 2l9 5v10l-9 5-9-5V7z" fill="var(--text-2)" /><path d="M12 2v10l9-5M12 12L3 7M12 12v10" stroke="var(--bg)" stroke-width="1.2" fill="none" /></svg>
{:else if provider === "gemini"}
  <svg width={size} height={size} viewBox="0 0 24 24" aria-label="Gemini"><defs><linearGradient id="gm" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#4f8cf7" /><stop offset="1" stop-color="#b07cff" /></linearGradient></defs><path d="M12 2c.6 5.3 4.7 9.4 10 10-5.3.6-9.4 4.7-10 10-.6-5.3-4.7-9.4-10-10 5.3-.6 9.4-4.7 10-10z" fill="url(#gm)" /></svg>
{:else}
  <svg width={size} height={size} viewBox="0 0 24 24" aria-label="Agente"><rect x="3" y="3" width="18" height="18" rx="5" fill="none" stroke="var(--text-2)" stroke-width="1.8" /><path d="M9 10l-2 2 2 2M15 10l2 2-2 2" stroke="var(--text-2)" stroke-width="1.6" fill="none" stroke-linecap="round" /></svg>
{/if}

<style>
  svg { flex: none; display: block; }
</style>
