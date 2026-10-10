<script lang="ts">
  import { colorFor, initials } from "../lib/format";
  let { name = "", src = null, size = 28, ring = false }: { name?: string; src?: string | null; size?: number; ring?: boolean } = $props();
  let failed = $state(false);
</script>

{#if src && !failed}
  <img class="av" class:ring {src} alt={name} title={name} width={size} height={size} onerror={() => (failed = true)} />
{:else}
  <span class="av ini" class:ring title={name} style="width:{size}px;height:{size}px;font-size:{Math.round(size * 0.38)}px;background:{colorFor(name)}">{initials(name)}</span>
{/if}

<style>
  .av { border-radius: 50%; flex-shrink: 0; object-fit: cover; display: inline-grid; place-items: center; }
  .ini { color: #fff; font-weight: 700; letter-spacing: 0.02em; text-shadow: 0 1px 1px rgba(0, 0, 0, 0.2); }
  .ring { box-shadow: 0 0 0 2px var(--surface); }
</style>
