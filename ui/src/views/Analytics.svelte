<script lang="ts">
  import { RefreshCw } from "@lucide/svelte";
  import { untrack } from "svelte";
  import { get } from "../lib/api";
  import { fmtH } from "../lib/format";
  import { go } from "../lib/router.svelte";
  import { store } from "../lib/store.svelte";
  import { soft } from "../lib/router.svelte";
  import Kpi from "../components/Kpi.svelte";
  import Page from "../components/Page.svelte";
  import Segmented from "../components/Segmented.svelte";
  import Skeleton from "../components/Skeleton.svelte";

  let days = $state("30");
  let org = $state("");
  let A = $state<any>(null);
  let tip = $state<{ x: number; y: number; text: string } | null>(null);

  async function load(force = false) {
    A = null;
    try { const r = await get("analytics", { days, org, force: force ? 1 : 0 }); soft(() => { A = r; }); }
    catch (e: any) { A = { error: e.message }; }
  }
  $effect(() => { void days; void org; untrack(() => load()); });
  const maxOf = (rows: any[], keys: string[]) => Math.max(1, ...rows.map(d => keys.reduce((s, k) => s + d[k], 0)));
  const fmtD = (iso: string) => new Date(iso + "T12:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  function showTip(e: MouseEvent, text: string) { tip = { x: e.clientX, y: e.clientY, text }; }
</script>

<Page title="Análise" sub="Como as PRs andam nas suas organizações do Azure DevOps">
  {#snippet actions()}<button class="btn sm ghost" onclick={() => load(true)}><RefreshCw size={14} /> Recarregar</button>{/snippet}
  <div class="toolbar">
    <Segmented bind:value={days} options={[{ value: "7", label: "7 dias" }, { value: "30", label: "30 dias" }, { value: "90", label: "90 dias" }]} />
    <Segmented bind:value={org} options={[{ value: "", label: "Todas" }, ...(store.s?.orgs || []).map(o => ({ value: o, label: o }))]} />
  </div>
  <div class="scroll">
    {#if !A}<Skeleton kpis={6} rows={4} avatar={false} />
    {:else if A.error}<div class="err">{A.error}</div>
    {:else}
      {#each Object.entries(A.errors || {}) as [o, e] (o)}<div class="err">{o}: {e}</div>{/each}
      <div class="kpis">
        <Kpi index={0} label="PRs concluídas" value={A.kpis.merged} sub={`em ${A.days} dias`} />
        <Kpi index={1} label="Lead time mediano" value={fmtH(A.kpis.medianLeadH)} sub="abertura → conclusão" />
        <Kpi index={2} label="Aguardando meu voto" value={A.kpis.pending} sub={A.kpis.oldestPendingH ? `mais antiga há ${fmtH(A.kpis.oldestPendingH)}` : "fila zerada"} />
        <Kpi index={3} label="Aprovações minhas" value={A.kpis.autoApprovals + A.kpis.manualApprovals} sub={`${A.kpis.autoApprovals} auto · ${A.kpis.manualApprovals} manual`} />
        <Kpi index={4} label="Meu tempo de resposta" value={fmtH(A.kpis.myMedianResponseH)} sub="mediana, votos manuais" />
        <Kpi index={5} label="Abertas com problema" value={A.kpis.conflicts + A.kpis.buildFailed} sub={`${A.kpis.conflicts} conflito · ${A.kpis.buildFailed} build ✕`} />
      </div>
      <div class="grid2">
        {#each [{ t: "Minhas aprovações por dia", keys: ["auto", "manual"], colors: ["var(--accent)", "#f0726f"], labels: ["Piloto", "Manual"] },
                { t: "PRs concluídas por dia", keys: ["merged"], colors: ["var(--accent)"], labels: ["Concluídas"] }] as ch (ch.t)}
          {@const max = maxOf(A.daily, ch.keys)}
          <div class="card">
            <div class="card-h"><h3>{ch.t}</h3><span class="spacer"></span>
              {#if ch.keys.length > 1}<div class="legend">{#each ch.labels as l, i (l)}<span><i style="background:{ch.colors[i]}"></i>{l}</span>{/each}</div>{/if}</div>
            <div class="card-b">
              <div class="cols">
                {#each A.daily as d (d.date)}
                  <div class="c" role="img" onmousemove={(e) => showTip(e, `${fmtD(d.date)}\n${ch.keys.map((k, i) => `${ch.labels[i]}: ${d[k]}`).join("\n")}`)} onmouseleave={() => (tip = null)}>
                    {#each ch.keys as k, i (k)}{#if d[k]}<div class="seg" style="height:{(100 * d[k]) / max}%;background:{ch.colors[i]}"></div>{/if}{/each}
                  </div>
                {/each}
              </div>
              <div class="xaxis"><span>{fmtD(A.daily[0].date)}</span><span>máx. {max}/dia</span><span>{fmtD(A.daily[A.daily.length - 1].date)}</span></div>
            </div>
          </div>
        {/each}
      </div>
      <div class="grid2 wide">
        <div class="card">
          <div class="card-h"><h3>Por criador</h3><span class="muted small">concluídas no período · abertas agora</span></div>
          <table>
            <thead><tr><th>Criador</th><th style="width:36%">Concluídas</th><th class="num">Abertas</th><th class="num">Lead time</th><th class="num">p/ master</th><th></th></tr></thead>
            <tbody>
              {#each A.creators as c (c.name)}
                {@const maxM = Math.max(1, ...A.creators.map((x: any) => x.merged))}
                <tr><td>{c.name}</td>
                  <td><div class="bar"><span style="width:{(85 * c.merged) / maxM}%"></span><b>{c.merged}</b></div></td>
                  <td class="num">{c.open}</td><td class="num">{fmtH(c.medianLeadH)}</td><td class="num">{c.toMaster}</td>
                  <td class="num">{#if store.s?.rules.rules.some(r => r.enabled && r.creators.some(x => c.name.toLowerCase().includes(x.toLowerCase())))}<span class="pill accent">tem regra</span>
                    {:else}<button class="btn sm ghost" onclick={() => go("/automation/new")}>+ regra</button>{/if}</td></tr>
              {/each}
            </tbody>
          </table>
        </div>
        <div class="stack">
          {#each [{ t: "Repositórios mais movimentados", rows: A.repos }, { t: "Idade das PRs abertas", rows: A.aging }, { t: "Destino das concluídas", rows: A.targets }] as h (h.t)}
            {@const max = Math.max(1, ...h.rows.map((r: any) => r.count))}
            <div class="card"><div class="card-h"><h3>{h.t}</h3></div>
              <div class="card-b hbars">{#each h.rows as r (r.name)}<div class="hb"><span class="ell">{r.name}</span><div class="track"><i style="width:{(100 * r.count) / max}%"></i></div><b>{r.count}</b></div>{/each}</div></div>
          {/each}
        </div>
      </div>
    {/if}
  </div>
</Page>

{#if tip}<div class="tip" style="left:{tip.x + 12}px;top:{tip.y + 14}px">{tip.text}</div>{/if}

<style>
  .toolbar { display: flex; gap: 8px; margin-bottom: 12px; flex: none; }
  .scroll { flex: 1; min-height: 0; overflow: auto; overscroll-behavior: contain; padding-right: 2px; }
  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; margin-bottom: 14px; }
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px; }
  .grid2.wide { grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); align-items: start; }
  @media (max-width: 1100px) { .grid2, .grid2.wide { grid-template-columns: 1fr; } }
  .stack { display: grid; gap: 14px; }
  .legend { display: flex; gap: 12px; font-size: 12px; color: var(--text-2); }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .legend i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
  .cols { display: flex; align-items: flex-end; gap: 2px; height: 170px; border-bottom: 1px solid var(--line-2); }
  .c { flex: 1; height: 100%; display: flex; flex-direction: column-reverse; gap: 2px; min-width: 2px; border-radius: 4px 4px 0 0; transition: background var(--t-fast); }
  .c:hover { background: var(--surface-2); }
  .seg { width: 100%; animation: grow 0.6s var(--ease-out) both; transform-origin: bottom; }
  .c > .seg:last-child { border-radius: 4px 4px 0 0; }
  @keyframes grow { from { transform: scaleY(0); } }
  .xaxis { display: flex; justify-content: space-between; font-size: 11px; color: var(--muted); margin-top: 6px; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; font: 650 10.5px/1 var(--font); text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); padding: 10px 14px; }
  td { padding: 8px 14px; border-top: 1px solid var(--line); font-size: 13px; }
  .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  th { white-space: nowrap; }
  .bar { display: flex; align-items: center; gap: 8px; }
  .bar span { height: 8px; border-radius: 0 4px 4px 0; background: var(--accent); animation: grow-x 0.6s var(--ease-out) both; transform-origin: left; }
  @keyframes grow-x { from { transform: scaleX(0); } }
  .hbars { display: grid; gap: 7px; }
  .hb { display: grid; grid-template-columns: minmax(80px, 38%) 1fr 36px; gap: 10px; align-items: center; font-size: 12.5px; color: var(--text-2); }
  .track { height: 9px; }
  .track i { display: block; height: 100%; background: var(--accent); border-radius: 0 4px 4px 0; min-width: 2px; animation: grow-x 0.6s var(--ease-out) both; transform-origin: left; }
  .hb b { text-align: right; color: var(--text); font-variant-numeric: tabular-nums; }
  .err { margin-bottom: 10px; padding: 9px 12px; border-radius: 10px; background: var(--bad-soft); color: var(--bad); font-size: 13px; }
  .tip { position: fixed; z-index: 70; pointer-events: none; white-space: pre; background: var(--text); color: var(--bg); font-size: 12px; padding: 6px 9px; border-radius: 7px; box-shadow: var(--shadow-2); }
</style>
