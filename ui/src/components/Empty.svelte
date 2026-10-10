<script lang="ts">
  import type { Snippet } from "svelte";
  import { Check, Search } from "@lucide/svelte";
  let { title, text = "", done = false, icon = undefined, children = undefined }:
    { title: string; text?: string; done?: boolean; icon?: any; children?: Snippet } = $props();
  const Icon = $derived(icon || (done ? Check : Search));
</script>

<div class="empty">
  <div class="ic" class:done><Icon size={22} strokeWidth={done ? 2.6 : 2} /></div>
  <b>{title}</b>
  {#if text}<p>{text}</p>{/if}
  {#if children}<div class="extra">{@render children()}</div>{/if}
</div>

<style>
  .empty { padding: 56px 20px; text-align: center; color: var(--muted); animation: rise 0.5s var(--ease-out) both; }
  .ic { width: 52px; height: 52px; border-radius: 50%; margin: 0 auto 14px; display: grid; place-items: center;
    background: var(--surface-2); border: 1px solid var(--line); color: var(--muted); }
  .ic.done { background: var(--good-soft); color: var(--good); border-color: color-mix(in srgb, var(--good) 30%, transparent);
    animation: pop 0.6s var(--spring) 0.1s both; }
  b { display: block; color: var(--text); font-size: 15px; font-weight: 650; margin-bottom: 4px; }
  p { margin: 0 auto; max-width: 420px; font-size: 13px; }
  .extra { margin-top: 16px; display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; }
</style>
