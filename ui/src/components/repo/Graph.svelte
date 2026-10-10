<script lang="ts">
  // Graph de commits estilo GitKraken: faixas coloridas em SVG com curvas suaves, nó com o avatar do autor,
  // etiquetas de branch/tag e linha "WIP" quando há alterações não commitadas.
  import { Cloud, GitBranch, Monitor, Tag } from "@lucide/svelte";
  import { ago, colorFor, initials, shortSha } from "../../lib/format";
  import { layout, parseRefs } from "../../lib/graph";
  import type { Commit } from "../../lib/types";

  let { commits, head = null, selected = null, wip = 0, onselect, oncontext = undefined, highlight = null }:
    { commits: Commit[]; head?: string | null; selected?: string | null; wip?: number; onselect: (sha: string | "wip") => void;
      oncontext?: (c: Commit, e: MouseEvent) => void; highlight?: string | null } = $props();

  const ROW = 36, LANE = 16, PAD = 14;
  const g = $derived(layout(commits));
  const lanesW = $derived(Math.min(g.maxLanes, 12) * LANE + PAD);
  const x = (i: number) => PAD / 2 + i * LANE + LANE / 2;
  const mid = ROW / 2;

  function seg(from: number, to: number, y0: number, y1: number) {
    const x0 = x(from), x1 = x(to);
    if (x0 === x1) return `M${x0} ${y0} L${x1} ${y1}`;
    const h = y1 - y0;
    return `M${x0} ${y0} C${x0} ${y0 + h * 0.6} ${x1} ${y1 - h * 0.6} ${x1} ${y1}`;
  }
</script>

<div class="graph" style="--lanes:{lanesW}px">
  {#if wip}
    <button class="row wip" class:sel={selected === "wip"} onclick={() => onselect("wip")}>
      <svg width={lanesW} height={ROW} class="lanes">
        {#if commits.length}<path d={`M${x(g.rows[0]?.lane ?? 0)} ${mid} L${x(g.rows[0]?.lane ?? 0)} ${ROW}`} class="dash" />{/if}
        <circle cx={x(g.rows[0]?.lane ?? 0)} cy={mid} r="7" class="wipdot" />
      </svg>
      <div class="msg"><span class="wiptag">WIP</span><span class="subject">{wip} alteração(ões) não commitada(s)</span></div>
      <div class="who"></div><div class="when"></div><div class="sha"></div>
    </button>
  {/if}
  {#each commits as c, i (c.sha)}
    {@const r = g.rows[i]}
    {@const refs = parseRefs(c.refs)}
    <button class="row" class:sel={selected === c.sha} class:head={c.sha === head} class:dim={highlight && !c.refs.some(x => x.includes(highlight!))}
      data-sha={c.sha} onclick={() => onselect(c.sha)} oncontextmenu={(e) => { if (oncontext) { e.preventDefault(); oncontext(c, e); } }}>
      <svg width={lanesW} height={ROW} class="lanes" aria-hidden="true">
        {#each r.top as s, k (k)}<path d={seg(s.from, s.to, 0, mid)} stroke={s.color} />{/each}
        {#each r.bottom as s, k (k)}<path d={seg(s.from, s.to, mid, ROW)} stroke={s.color} />{/each}
        {#if r.merge}
          <circle cx={x(r.lane)} cy={mid} r="5" fill="var(--surface)" stroke={r.color} stroke-width="2.5" />
        {:else}
          <circle cx={x(r.lane)} cy={mid} r="9.5" fill={colorFor(c.author)} stroke={r.color} stroke-width="2.5" />
          <text x={x(r.lane)} y={mid + 3} text-anchor="middle" class="ini">{initials(c.author)}</text>
        {/if}
        {#if c.sha === head}<circle cx={x(r.lane)} cy={mid} r="13" fill="none" stroke={r.color} stroke-width="1.5" opacity="0.45" />{/if}
      </svg>
      <div class="msg">
        {#each refs as ref (ref.kind + ref.name)}
          <span class="ref {ref.kind}" class:current={ref.current} style="--c:{r.color}" title={ref.name}>
            {#if ref.kind === "tag"}<Tag size={10} />{:else if ref.kind === "remote"}<Cloud size={10} />{:else if ref.kind === "head"}<Monitor size={10} />{:else}<GitBranch size={10} />{/if}
            {ref.name}{#if ref.synced}<Cloud size={10} class="syn" />{/if}
          </span>
        {/each}
        <span class="subject">{c.subject}</span>
      </div>
      <div class="who"><span class="av" style="background:{colorFor(c.author)}">{initials(c.author)}</span><span class="ell">{c.author}</span></div>
      <div class="when">{ago(c.date)}</div>
      <div class="sha">{shortSha(c.sha)}</div>
    </button>
  {/each}
</div>

<style>
  .graph { display: flex; flex-direction: column; min-width: 0; container-type: inline-size; }
  .row { display: grid; grid-template-columns: var(--lanes) minmax(0, 1fr) 132px 50px 62px; align-items: center; gap: 10px; height: 36px; padding: 0 12px 0 4px;
    border: 0; background: none; color: var(--text); font: 13px var(--font); text-align: left; cursor: pointer; position: relative;
    transition: background var(--t-fast); }
  .row:hover { background: color-mix(in srgb, var(--surface-2) 75%, transparent); }
  .row.sel { background: var(--accent-soft); }
  .row.sel::before { content: ""; position: absolute; left: 0; top: 6px; bottom: 6px; width: 3px; border-radius: 0 3px 3px 0; background: var(--accent); }
  .row.dim { opacity: 0.35; }
  .lanes { flex-shrink: 0; overflow: visible; }
  .lanes path { fill: none; stroke-width: 2.2; stroke-linecap: round; }
  .lanes .dash { stroke: var(--muted); stroke-dasharray: 3 3; }
  .wipdot { fill: var(--surface); stroke: var(--muted); stroke-width: 2; stroke-dasharray: 3 2; }
  .ini { font: 700 7.5px var(--font); fill: #fff; pointer-events: none; }
  .msg { display: flex; align-items: center; gap: 6px; min-width: 0; overflow: hidden; }
  .subject { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text); }
  .head .subject { font-weight: 600; }
  .ref { display: inline-flex; align-items: center; gap: 4px; height: 20px; padding: 0 7px; border-radius: 6px; font: 600 11px/1 var(--font); white-space: nowrap; flex-shrink: 0;
    max-width: 150px; overflow: hidden; text-overflow: ellipsis; background: color-mix(in srgb, var(--c) 16%, transparent); color: var(--c);
    border: 1px solid color-mix(in srgb, var(--c) 40%, transparent); }
  .ref.current { background: var(--c); color: #0b0d12; border-color: transparent; }
  .ref.remote { background: transparent; color: var(--text-2); border-color: var(--line-2); }
  .ref.tag { background: var(--warn-soft); color: var(--warn); border-color: color-mix(in srgb, var(--warn) 35%, transparent); }
  .ref :global(.syn) { opacity: 0.7; }
  .wiptag { font: 700 10.5px/1 var(--font); letter-spacing: 0.05em; padding: 4px 7px; border-radius: 6px; background: var(--warn-soft); color: var(--warn); }
  .wip .subject { color: var(--text-2); font-style: italic; }
  .who { display: flex; align-items: center; gap: 7px; min-width: 0; font-size: 12px; color: var(--text-2); }
  .av { width: 18px; height: 18px; border-radius: 50%; display: inline-grid; place-items: center; font: 700 8px var(--font); color: #fff; flex-shrink: 0; }
  .when { font-size: 12px; color: var(--muted); text-align: right; white-space: nowrap; }
  .sha { font: 11.5px var(--mono); color: var(--muted); text-align: right; }
  /* coluna de autor só quando sobra espaço: o nó já mostra quem fez o commit */
  @container (max-width: 820px) { .row { grid-template-columns: var(--lanes) minmax(0, 1fr) 50px 62px; } .who { display: none; } }
  @container (max-width: 560px) { .row { grid-template-columns: var(--lanes) minmax(0, 1fr) 50px; } .sha { display: none; } }
</style>
