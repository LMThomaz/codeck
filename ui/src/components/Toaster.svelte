<script lang="ts">
  import { CheckCircle2, Info, XCircle } from "@lucide/svelte";
  import { ui } from "../lib/ui.svelte";
  const icons = { ok: CheckCircle2, error: XCircle, info: Info };
</script>

<div class="toasts" aria-live="polite">
  {#each ui.toasts as t (t.id)}
    {@const Icon = icons[t.kind]}
    <div class="toast {t.kind}">
      <Icon size={16} />
      <span>{t.text}</span>
      {#if t.action}<button class="btn sm ghost" onclick={() => t.action?.run()}>{t.action.label}</button>{/if}
    </div>
  {/each}
</div>

<style>
  .toasts { position: fixed; left: 50%; bottom: 22px; transform: translateX(-50%); z-index: 90; display: grid; gap: 8px; justify-items: center; pointer-events: none; }
  .toast { pointer-events: auto; display: flex; align-items: center; gap: 10px; padding: 10px 14px; border-radius: 12px; background: var(--elevated);
    border: 1px solid var(--line-2); box-shadow: var(--shadow-3); font-size: 13px; max-width: min(560px, 92vw); animation: toast-in 0.34s var(--spring) both; }
  @keyframes toast-in { from { opacity: 0; transform: translateY(14px) scale(0.97); } }
  .ok :global(svg) { color: var(--good); flex-shrink: 0; }
  .error :global(svg) { color: var(--bad); flex-shrink: 0; }
  .info :global(svg) { color: var(--info); flex-shrink: 0; }
  .error { border-color: color-mix(in srgb, var(--bad) 40%, transparent); }
</style>
