<script lang="ts">
  // Indicador: conta até o valor quando aparece; "pulsa" quando o número muda numa atualização.
  let { label, value, sub = "", alert = false, onclick = undefined, active = false, index = 0 }:
    { label: string; value: string | number; sub?: string; alert?: boolean; onclick?: () => void; active?: boolean; index?: number } = $props();
  let shown = $state("");
  let pop = $state(false);
  let first = true;
  let last = "";

  $effect(() => {
    const v = String(value);
    const m = /^(\d+)(%?)$/.exec(v);
    if (first && m && Number(m[1]) > 1 && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
      first = false;
      const end = Number(m[1]), t0 = performance.now();
      const step = (now: number) => {
        const k = Math.min(1, (now - t0) / 560), e = 1 - Math.pow(1 - k, 3);
        shown = Math.round(end * e) + m[2];
        if (k < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    } else {
      if (!first && last && last !== v) { pop = false; requestAnimationFrame(() => (pop = true)); }
      shown = v;
    }
    first = false;
    last = v;
  });
</script>

<svelte:element this={onclick ? "button" : "div"} class="kpi" class:alert class:active class:clickable={!!onclick} {onclick}
  style="--i:{index}" role={onclick ? "button" : undefined}>
  <div class="l">{label}</div>
  <div class="v" class:pop>{shown}</div>
  {#if sub}<div class="s">{sub}</div>{/if}
</svelte:element>

<style>
  .kpi { text-align: left; font: inherit; color: inherit; background: var(--surface); border: 1px solid var(--line); border-radius: var(--r);
    padding: 11px 14px 12px; min-width: 0; position: relative; overflow: hidden; box-shadow: var(--shadow-1);
    transition: transform var(--t) var(--ease), border-color var(--t) var(--ease), box-shadow var(--t) var(--ease);
    animation: rise 0.45s var(--ease-out) both; animation-delay: calc(var(--i) * 35ms); }
  .kpi:hover { border-color: var(--line-2); transform: translateY(-1px); }
  .clickable { cursor: pointer; }
  .active { border-color: var(--accent-line); box-shadow: 0 0 0 1px var(--accent-line); }
  .alert::before { content: ""; position: absolute; inset: 0 auto 0 0; width: 3px; background: var(--bad); }
  .l { font-size: 11.5px; color: var(--text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 500; }
  .v { font-size: 22px; font-weight: 680; letter-spacing: -0.03em; font-variant-numeric: tabular-nums; line-height: 1.3; display: inline-block; }
  .alert .v { color: var(--bad); }
  .pop { animation: pop 0.45s var(--ease-out); }
  .s { font-size: 11px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
