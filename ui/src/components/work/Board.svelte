<script lang="ts">
  // Quadro de tarefas de TODOS os projetos abertos, pelo estado dos agentes: o que precisa de você aparece primeiro.
  import { GitBranch } from "@lucide/svelte";
  import { go } from "../../lib/router.svelte";
  import type { Project, Task } from "../../lib/work.svelte";
  import { work } from "../../lib/work.svelte";
  import ProviderIcon from "../ProviderIcon.svelte";
  import AgentIcon from "./AgentIcon.svelte";

  let { onopen }: { onopen: (p: Project, t: Task) => void } = $props();
  const COLS = [
    { id: "needs-you", label: "Precisa de você", tone: "warn" },
    { id: "working", label: "Trabalhando", tone: "accent" },
    { id: "done", label: "Pronta para revisar", tone: "good" },
    { id: "pr", label: "PR aberta", tone: "info" },
    { id: "idle", label: "Parada", tone: "muted" },
  ];
  function col(t: Task) {
    if (t.pr) return "pr";
    const ss = t.terms.filter(x => x.kind === "agent").map(x => work.session(x)?.status);
    if (ss.includes("needs-you")) return "needs-you";
    if (ss.includes("working") || ss.includes("compacting")) return "working";
    if (ss.includes("done")) return "done";
    return "idle";
  }
  const items = $derived(work.projects.flatMap(p => p.tasks.map(t => ({ p, t, c: col(t) }))));
</script>

<div class="board">
  {#each COLS as c (c.id)}
    {@const list = items.filter(x => x.c === c.id)}
    <div class="col">
      <div class="ch"><span class="dot {c.tone}"></span>{c.label}<span class="n">{list.length}</span></div>
      <div class="cards">
        {#each list as x (x.t.id)}
          <button class="card tcard" onclick={() => onopen(x.p, x.t)}>
            <div class="top"><ProviderIcon provider={(x.p.provider as any) || null} size={12} /><span class="tiny muted ell">{x.p.name}</span>
              <span class="ags">{#each x.t.terms.filter(y => y.kind === "agent") as a (a.id)}<AgentIcon provider={a.meta.provider} size={13} />{/each}</span></div>
            <b class="ttl">{x.t.title}</b>
            <span class="tiny muted mono ell"><GitBranch size={10} /> {x.t.branch}</span>
            {#each x.t.terms.filter(y => y.kind === "agent").slice(0, 2) as a (a.id)}
              {@const s = work.session(a)}
              {#if s?.context?.used != null}<div class="ctx"><span style="width:{Math.min(100, s.context.used)}%"></span></div>{/if}
            {/each}
          </button>
        {:else}<div class="none">—</div>{/each}
      </div>
    </div>
  {/each}
</div>

<style>
  .board { height: 100%; display: grid; grid-template-columns: repeat(5, minmax(200px, 1fr)); gap: 10px; overflow-x: auto; }
  .col { display: flex; flex-direction: column; min-height: 0; background: var(--bg-2); border: 1px solid var(--line); border-radius: var(--r); }
  .ch { display: flex; align-items: center; gap: 8px; padding: 12px; font: 650 12px var(--font); color: var(--text-2); }
  .n { margin-left: auto; color: var(--muted); font-weight: 600; }
  .dot { width: 8px; height: 8px; border-radius: 50%; }
  .dot.warn { background: var(--warn); } .dot.accent { background: var(--accent); } .dot.good { background: var(--good); } .dot.info { background: var(--info); } .dot.muted { background: var(--line-3); }
  .cards { flex: 1; overflow: auto; display: grid; gap: 8px; padding: 0 8px 8px; align-content: start; }
  .tcard { display: grid; gap: 5px; padding: 11px; text-align: left; cursor: pointer; font: 13px var(--font); color: var(--text); animation: rise 0.25s var(--ease-out) both;
    transition: transform var(--t) var(--spring), border-color var(--t); }
  .tcard:hover { transform: translateY(-2px); border-color: var(--accent-line); }
  .top { display: flex; align-items: center; gap: 6px; min-width: 0; }
  .ags { margin-left: auto; display: flex; gap: 3px; }
  .ttl { font-weight: 600; line-height: 1.3; }
  .tiny { display: flex; align-items: center; gap: 4px; }
  .ctx { height: 3px; border-radius: 3px; background: var(--surface-3); overflow: hidden; }
  .ctx span { display: block; height: 100%; background: var(--accent); }
  .none { padding: 8px; color: var(--faint); font-size: 12px; }
</style>
