<script lang="ts">
  // Botão de voto que mostra a própria fase: girando enquanto envia, ✓ quando o Azure/GitHub confirmou.
  import { Check, LoaderCircle } from "@lucide/svelte";
  import type { Snippet } from "svelte";
  import { vote } from "../../lib/actions";
  import { store } from "../../lib/store.svelte";
  import type { PR } from "../../lib/types";

  let { pr, v, cls = "", leaves = false, children }: { pr: PR; v: number; cls?: string; leaves?: boolean; children: Snippet } = $props();
  const st = $derived(store.votes[pr.key]);
  const mine = $derived(st?.vote === v);
</script>

<button class="btn sm vbtn {cls}" class:busy={mine && st?.phase === "sending"} class:ok={mine && (st?.phase === "done" || st?.phase === "leaving")}
  disabled={!!st && !mine} aria-busy={mine && st?.phase === "sending"} onclick={() => vote(pr, v, leaves)}>
  <span class="ico">
    {#if mine && st?.phase === "sending"}<LoaderCircle size={13} class="spin" />
    {:else if mine && (st?.phase === "done" || st?.phase === "leaving")}<Check size={13} strokeWidth={3} />{/if}
  </span>
  <span class="lbl">{@render children()}</span>
</button>

<style>
  .vbtn { position: relative; overflow: hidden; }
  /* o ícone ocupa espaço só quando existe, abrindo com mola — o botão "respira" em vez de pular */
  .ico { display: inline-grid; place-items: center; width: 0; margin-right: -5px; opacity: 0; transform: scale(0.4);
    transition: width var(--t) var(--spring), margin var(--t) var(--spring), opacity var(--t-fast), transform var(--t) var(--spring); }
  .busy .ico, .ok .ico { width: 13px; margin-right: 0; opacity: 1; transform: none; }
  .busy { pointer-events: none; }
  /* faixa de luz atravessando enquanto envia */
  .busy::after { content: ""; position: absolute; inset: 0; background: linear-gradient(100deg, transparent 20%, rgba(255,255,255,0.22) 50%, transparent 80%);
    transform: translateX(-100%); animation: sweep 1.1s var(--ease) infinite; }
  .ok { animation: pop 0.42s var(--spring); }
  @keyframes sweep { to { transform: translateX(100%); } }
</style>
