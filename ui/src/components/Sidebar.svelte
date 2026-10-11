<script lang="ts">
  import { BarChart3, Gauge, Code2, RefreshCw, CircleDot, FolderGit2, GitPullRequest, Hammer, History, Inbox, Pin, Rocket, Search, Settings, Zap } from "@lucide/svelte";
  import { BRAND } from "../lib/brand";
  import { post } from "../lib/api";
  import { repos } from "../lib/repos.svelte";
  import { work } from "../lib/work.svelte";
  import AgentIcon from "./work/AgentIcon.svelte";
  import { go, router } from "../lib/router.svelte";
  import { store } from "../lib/store.svelte";
  import { ui } from "../lib/ui.svelte";
  import { time } from "../lib/format";
  import Mark from "./Mark.svelte";
  import CollectionsTree from "./repo/CollectionsTree.svelte";
  import ProviderIcon from "./ProviderIcon.svelte";
  import Switch from "./Switch.svelte";

  const s = $derived(store.s);
  const running = $derived(s ? s.builds.filter(b => b.status !== "completed").length : 0);
  const nav = $derived([
    { group: "Trabalho" },
    { id: "work", label: "Projetos", icon: Code2, count: work.needsYou || undefined, hot: true, live: work.agents.some(a => a.session?.status === "working") },
    { id: "ai", label: "Uso de IA", icon: Gauge },
    { group: "Visão geral" },
    { id: "inbox", label: "Fila", icon: Inbox, count: store.inbox.length + (s?.deploys.length || 0), hot: true },
    { id: "prs", label: "Pull requests", icon: GitPullRequest, count: s ? s.myPrs.length + store.open.length : undefined },
    { id: "builds", label: "Builds e Actions", icon: Hammer, count: running || undefined, live: running > 0 },
    { id: "deploys", label: "Deploys", icon: Rocket, count: s?.deploys.length, hot: true },
    { id: "issues", label: "Issues e tarefas", icon: CircleDot, count: s?.issues.length },
    { group: "Código" },
    { id: "repos", label: "Repositórios", icon: FolderGit2, count: repos.local.length || undefined },
    { group: "Configurar" },
    { id: "automation", label: "Automação", icon: Zap },
    { id: "analytics", label: "Análise", icon: BarChart3 },
    { id: "history", label: "Histórico", icon: History },
    { id: "settings", label: "Contas e ajustes", icon: Settings },
  ] as any[]);

  let navEl: HTMLElement | undefined = $state();
  let ind = $state({ y: 0, h: 0, ready: false });
  $effect(() => {
    void router.view; void router.param; void repos.pinned.length; void repos.catalogs.length; void repos.tags.length; void repos.favorites.length;
    requestAnimationFrame(place);
  });
  function place() {
    const on = navEl?.querySelector<HTMLElement>(".item.on");
    ind = on ? { y: on.offsetTop, h: on.offsetHeight, ready: true } : { ...ind, ready: false };
  }
  // grupo do catálogo abrindo/fechando muda a altura da árvore: o marcador do item ativo acompanha
  let treeEl: HTMLElement | undefined = $state();
  $effect(() => {
    if (!treeEl) return;
    const ro = new ResizeObserver(() => place());
    ro.observe(treeEl);
    return () => ro.disconnect();
  });
  // "Repositórios" só fica marcado na lista de locais; favoritos, tags e catálogos marcam o próprio subitem
  const isOn = (id: string) => (router.view === id && !(id === "repos" && router.param)) || (id === "repos" && router.view === "repo" && !repos.pinned.some(r => r.id === router.param));
  const paused = $derived(!!s?.rules.settings.paused);
  async function toggleAuto(on: boolean) {
    try {
      await post("rules", { ...s!.rules, settings: { ...s!.rules.settings, paused: !on } });
      ui.toast(on ? "Automação ligada" : "Automação pausada — nada é aprovado sozinho");
      store.load();
    } catch (e) { ui.error(e); }
  }
  const syncText = $derived(store.error ? "backend fora do ar" : store.offline ? "sem conexão" : s?.polling ? `lendo ${s.polling}…` : store.refreshing ? "pedindo leitura…"
    : s?.lastPoll ? `lido às ${time(s.lastPoll)}` : "primeira leitura…");
  async function manualRefresh() {
    const ok = await store.refresh();
    ui.toast(ok ? "Tudo atualizado" : "A leitura está demorando — os dados chegam assim que ela terminar", ok ? "ok" : "info");
  }
  const sourceErrors = $derived(s ? { ...s.errors, ...s.buildErrors, ...s.deployErrors } : {});
</script>

<aside class="side">
  <div class="brand">
    <span class="mk"><Mark size={26} /></span>
    <div class="bn"><b>{BRAND.name}</b><span>versionamento</span></div>
  </div>

  <button class="search" onclick={() => (ui.palette = true)}>
    <Search size={15} /><span>Buscar ou ir para…</span><span class="kbd">{navigator.platform.includes("Mac") ? "⌘" : "Ctrl"} K</span>
  </button>

  <nav bind:this={navEl}>
    <span class="ind" class:ready={ind.ready} style="transform:translateY({ind.y}px);height:{ind.h}px"></span>
    {#each nav as n, i (n.id || n.group || i)}
      {#if n.group}
        <div class="grp">{n.group}</div>
      {:else}
        <button class="item" class:on={isOn(n.id)} onclick={() => go("/" + n.id)}>
          <n.icon size={16} />
          <span class="lbl">{n.label}</span>
          {#if n.live}<span class="live"></span>{/if}
          {#if n.count !== undefined && n.count !== null}<span class="count" class:hot={n.hot && n.count > 0 && !isOn(n.id)}>{n.count}</span>{/if}
        </button>
        {#if n.id === "work"}
          {#each work.projects as x (x.id)}
            {@const ags = work.agents.filter(a => a.project.id === x.id)}
            <button class="item sub" class:on={router.view === "work" && (router.param === x.id || (!router.param && work.active === x.id))} onclick={() => go("/work/" + x.id)}>
              <span class="lbl">{x.name}</span>
              {#each ags.slice(0, 3) as a (a.term.id)}<span class="ag" class:busy={a.session?.status === "working"} class:need={a.session?.status === "needs-you"}><AgentIcon provider={a.term.meta.provider} size={11} /></span>{/each}
            </button>
          {/each}
        {/if}
        {#if n.id === "repos"}
          <div class="tree" bind:this={treeEl}><CollectionsTree compact /></div>
          {#each repos.pinned as r (r.id)}
            <button class="item sub" class:on={router.view === "repo" && router.param === r.id} onclick={() => go("/repo/" + r.id)}>
              <Pin size={12} /><span class="lbl">{r.name}</span>
              {#if r.status?.changes}<span class="chg" title="alterações não commitadas">{r.status.changes}</span>{/if}
            </button>
          {/each}
        {/if}
      {/if}
    {/each}
  </nav>

  <div class="foot">
    <Switch checked={!paused} onchange={toggleAuto} label={paused ? "Automação pausada" : "Automação ativa"} />
    <div class="health">
      {#each s?.orgs || [] as o (o)}
        <span class:err={sourceErrors[o]} title={sourceErrors[o] || `Azure DevOps · ${o}`}><ProviderIcon provider="azure" size={12} />{o}</span>
      {/each}
      {#each s?.githubAccounts || [] as a (a.id)}
        <span class:err={sourceErrors["gh:" + a.login]} title={sourceErrors["gh:" + a.login] || `GitHub · @${a.login}`}><ProviderIcon provider="github" size={12} />{a.login}</span>
      {/each}
    </div>
    <div class="sync" class:on={store.fetching && !store.offline} class:off={!!store.error || store.offline}>
      <span class="state">
        <span class="pulse"></span>
        {#key syncText}<span class="txt">{syncText}</span>{/key}
      </span>
      <button class="btn ghost sm icon" title={store.fetching ? "Lendo…" : "Ler tudo agora"} aria-label="Atualizar" disabled={store.refreshing} onclick={manualRefresh}>
        <RefreshCw size={14} class={store.fetching ? "spin" : ""} />
      </button>
    </div>
  </div>
</aside>

<style>
  .side { width: var(--sidebar-w); flex: none; height: 100%; display: flex; flex-direction: column; gap: 12px; padding: 16px 10px 12px;
    background: var(--bg-2); border-right: 1px solid var(--line); }
  .brand { display: flex; align-items: center; gap: 10px; padding: 2px 8px 4px; }
  .mk { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 10px; background: var(--surface); border: 1px solid var(--line-2);
    box-shadow: var(--shadow-1); transition: transform var(--t-slow) var(--spring); }
  .brand:hover .mk { transform: rotate(-8deg) scale(1.05); }
  .bn { display: grid; line-height: 1.15; }
  .bn b { font-size: 15px; letter-spacing: -0.02em; }
  .bn span { font-size: 11px; color: var(--muted); }
  .search { display: flex; align-items: center; gap: 8px; height: 32px; padding: 0 8px 0 10px; border-radius: 9px; border: 1px solid var(--line);
    background: var(--surface); color: var(--muted); font: 13px var(--font); cursor: pointer; transition: border-color var(--t), color var(--t); }
  .search:hover { border-color: var(--line-2); color: var(--text-2); }
  .search span:nth-child(2) { flex: 1; text-align: left; }
  nav { position: relative; flex: 1; overflow-y: auto; overflow-x: hidden; display: flex; flex-direction: column; gap: 1px; margin: 0 -2px; padding: 0 2px; }
  .ind { position: absolute; left: 2px; right: 2px; top: 0; border-radius: 8px; background: var(--accent-soft); opacity: 0; pointer-events: none;
    transition: transform 0.42s var(--ease-out), height 0.42s var(--ease-out), opacity 0.2s; }
  .ind::before { content: ""; position: absolute; left: -10px; top: 22%; bottom: 22%; width: 3px; border-radius: 0 3px 3px 0; background: var(--accent); }
  .ind.ready { opacity: 1; }
  .grp { font: 650 10.5px/1 var(--font); text-transform: uppercase; letter-spacing: 0.08em; color: var(--faint); padding: 14px 10px 6px; }
  .item { position: relative; z-index: 1; display: flex; align-items: center; gap: 10px; height: 32px; padding: 0 10px; border: 0; border-radius: 8px;
    background: none; color: var(--text-2); font: 500 13px var(--font); cursor: pointer; text-align: left; transition: color var(--t), background var(--t), padding var(--t) var(--ease); }
  .item:hover { color: var(--text); background: color-mix(in srgb, var(--surface-2) 60%, transparent); }
  .item:hover:not(.on) { padding-left: 12px; }
  .item.on { color: var(--text); font-weight: 600; background: none; }
  .item.on :global(svg) { color: var(--accent); }
  .item.sub { height: 27px; padding-left: 36px; font-size: 12.5px; gap: 8px; }
  .item.sub:hover:not(.on) { padding-left: 38px; }
  .tree { position: relative; z-index: 1; }
  .ag { display: inline-grid; place-items: center; border-radius: 50%; padding: 1px; }
  .ag.busy { box-shadow: 0 0 0 2px var(--accent-soft); animation: live 1.6s infinite; }
  .ag.need { box-shadow: 0 0 0 2px var(--warn); }
  .lbl { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .count { font: 650 11px/1 var(--font); font-variant-numeric: tabular-nums; padding: 3px 7px; border-radius: 99px; background: var(--surface-2); color: var(--text-2);
    border: 1px solid var(--line); transition: background var(--t), color var(--t); }
  .item.on .count { background: var(--accent); color: #fff; border-color: transparent; }
  .count.hot { background: var(--bad); color: #fff; border-color: transparent; }
  .chg { font: 650 10px/1 var(--font); color: var(--warn); }
  .live { width: 7px; height: 7px; border-radius: 50%; background: var(--warn); box-shadow: 0 0 0 0 var(--warn); animation: live 1.6s infinite; }
  @keyframes live { 0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--warn) 60%, transparent); } 70% { box-shadow: 0 0 0 6px transparent; } 100% { box-shadow: 0 0 0 0 transparent; } }
  .foot { display: grid; gap: 10px; padding: 12px 8px 0; border-top: 1px solid var(--line); }
  .health { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 11.5px; color: var(--text-2); }
  .health span { display: inline-flex; align-items: center; gap: 5px; }
  .health .err { color: var(--bad); }
  .sync { display: flex; align-items: center; gap: 6px; font-size: 11.5px; color: var(--muted); min-height: 27px; }
  .state { flex: 1; min-width: 0; display: flex; align-items: center; gap: 7px; }
  .txt { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; animation: rise 0.3s var(--ease-out); }
  .sync.on .txt { color: var(--text-2); }
  /* ponto de status: verde parado quando em dia, azul pulsando enquanto lê, vermelho se o backend caiu */
  .pulse { width: 7px; height: 7px; border-radius: 50%; flex: none; background: var(--good); transition: background var(--t); }
  .sync.on .pulse { background: var(--accent); animation: ping 1.2s var(--ease) infinite; }
  .sync.off .pulse { background: var(--bad); }
  @keyframes ping { 0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--accent) 65%, transparent); } 80%, 100% { box-shadow: 0 0 0 7px transparent; } }
  .sync .btn { margin-left: auto; }
</style>
