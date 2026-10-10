<script lang="ts">
  // Área de trabalho (v3): projetos abertos em abas; em cada um, o checkout principal e as tarefas (worktrees) à
  // esquerda com os arquivos; no centro, abas de agentes, terminais e arquivos; à direita, o agente e os limites.
  // ⌘P abre arquivo · ⌘⇧F busca no projeto · ⌘T novo terminal · ⌘W fecha a aba · ⌘1…9 troca de projeto.
  import { Bot, ChevronDown, Code2, FolderGit2, FolderOpen, GitBranch, AppWindow, Columns2, GitCompareArrows, LayoutGrid, PanelRight, Settings2, Plus, Search, SquareTerminal, X } from "@lucide/svelte";
  import { untrack } from "svelte";
  import { post } from "../lib/api";
  import { pickFolder, send } from "../lib/native";
  import { setOpener } from "../lib/lsp";
  import { repos } from "../lib/repos.svelte";
  import { go, router } from "../lib/router.svelte";
  import { ui } from "../lib/ui.svelte";
  import type { Project, Task, TermInfo } from "../lib/work.svelte";
  import { STATUS, work } from "../lib/work.svelte";
  import Empty from "../components/Empty.svelte";
  import Menu from "../components/Menu.svelte";
  import ProviderIcon from "../components/ProviderIcon.svelte";
  import AgentIcon from "../components/work/AgentIcon.svelte";
  import AgentPanel from "../components/work/AgentPanel.svelte";
  import Editor, { dirty, forget, keyOf } from "../components/work/Editor.svelte";
  import FileTree from "../components/work/FileTree.svelte";
  import NewTask from "../components/work/NewTask.svelte";
  import Terminal, { drop } from "../components/work/Terminal.svelte";
  import Board from "../components/work/Board.svelte";
  import Compare from "../components/work/Compare.svelte";
  import ProjectSettings from "../components/work/ProjectSettings.svelte";
  import Review from "../components/work/Review.svelte";
  import RepoDetail from "./RepoDetail.svelte";

  type FileTab = { k: "file"; key: string; path: string; scope: string | null; line?: number };
  type View = { scope: string | null; files: FileTab[]; order: string[]; active: string | null; left: "files" | "search"; right: boolean; split?: string | null };
  const LS = "commitdeck.work.views";
  let views = $state<Record<string, View>>(readViews());
  function readViews() { try { return JSON.parse(localStorage.getItem(LS) || "{}"); } catch { return {}; } }
  $effect(() => { const v = JSON.stringify(views); try { localStorage.setItem(LS, v); } catch { /* sem armazenamento */ } });

  $effect(() => { if (!repos.loaded) repos.load(false); });

  // projeto pela rota (/work/<id>) ou o ativo; /work/board é o quadro de todas as tarefas
  const board = $derived(router.parts[1] === "board");
  // janela própria de um projeto (#/solo/<id>): sem barra lateral nem abas de projeto
  const solo = $derived(router.view === "solo");
  const pid = $derived(board ? null : router.parts[1] || work.active);
  const p = $derived(work.projects.find(x => x.id === pid) || null);
  $effect(() => {
    if (!work.loaded) return;
    if (board || solo || router.view === "repo") return;   // #/repo/<id>: quem decide o projeto é o work.openRepo
    if (router.parts[1] && !work.projects.some(x => x.id === router.parts[1])) untrack(() => work.open(router.parts[1]).catch(e => ui.error(e)));
    else if (p && work.active !== p.id) untrack(() => work.activate(p.id));
  });
  const v = $derived.by(() => {
    if (!p) return null;
    if (!views[p.id]) untrack(() => (views[p.id] = { scope: null, files: [], order: [], active: null, left: "files", right: true }));
    return views[p.id] || null;
  });
  const task = $derived(p && v?.scope ? p.tasks.find(t => t.id === v.scope) || null : null);
  const scopeTerms = $derived<TermInfo[]>(p ? (task ? task.terms : p.terms) : []);

  type Tab = { key: string; kind: "term" | "file" | "review" | "git"; term?: TermInfo; file?: FileTab };
  const tabs = $derived.by<Tab[]>(() => {
    if (!p || !v) return [];
    const list: Tab[] = [
      // repositório = projeto: a aba Git (grafo, branches, alterações, commit, sync) fica sempre no começo — numa tarefa,
      // é o Git do worktree dela
      { key: "g:" + (v.scope || "main"), kind: "git" as const },
      // tarefa: a aba "Revisão" fica sempre no começo (o que mudou desde a base, para revisar e comentar)
      ...(task ? [{ key: "r:" + task.id, kind: "review" as const }] : []),
      ...scopeTerms.map(t => ({ key: "t:" + t.id, kind: "term" as const, term: t })),
      ...v.files.filter(f => f.scope === (v.scope || null)).map(f => ({ key: f.key, kind: "file" as const, file: f })),
    ];
    const pos = (k: string) => { if (k.startsWith("g:")) return -2; if (k.startsWith("r:")) return -1; const i = v.order.indexOf(k); return i < 0 ? 1e6 : i; };
    return list.sort((a, b) => pos(a.key) - pos(b.key));
  });
  // sem aba escolhida: o 1º terminal/arquivo; se não houver, a tela inicial (abrir agente, terminal, nova tarefa)
  const activeTab = $derived(tabs.find(t => t.key === v?.active) || tabs.find(t => t.kind === "term" || t.kind === "file") || null);
  const splitTab = $derived(v?.split && v.split !== activeTab?.key ? tabs.find(t => t.key === v!.split) || null : null);
  const activeTerm = $derived(activeTab?.kind === "term" ? activeTab.term! : (scopeTerms.find(t => t.kind === "agent") || null));

  function focusTab(key: string) {
    if (!v) return;
    v.active = key;
    if (!v.order.includes(key)) v.order = [...v.order, key];
  }
  function setScope(scope: string | null) { if (v) { v.scope = scope; v.active = null; } }

  // ------------------------------------------------------------ ações
  let newTask = $state<{ preset?: any } | null>(null);
  $effect(() => {
    const fr = work.focusRequest;
    if (fr && p && v && fr.projectId === p.id) untrack(() => { v!.scope = fr.scope; v!.active = (fr.tab === "git" ? "g:" : "r:") + (fr.scope || "main"); work.focusRequest = null; });
  });
  let comparing = $state<string | null>(null);
  let settingsOpen = $state(false);
  $effect(() => {
    const pt = work.pendingTask;
    if (pt && p && pt.projectId === p.id) untrack(() => { setScope(null); newTask = { preset: pt.preset }; work.pendingTask = null; });
  });
  async function newTerm(command?: string, title?: string) {
    if (!p) return;
    try { const t = await post<TermInfo>("ws/shell", { repoId: p.id, taskId: v?.scope, title, command }); await work.load(); focusTab("t:" + t.id); }
    catch (e) { ui.error(e); }
  }
  async function newAgent(accountId: string, resume?: string) {
    if (!p) return;
    const prog = ui.progress(resume ? "Retomando a conversa…" : "Abrindo o agente…");
    try { const t = await post<TermInfo>("ws/agent", { repoId: p.id, taskId: v?.scope, accountId, resume }); await work.load(); focusTab("t:" + t.id); prog.done(resume ? "Conversa retomada" : "Agente aberto"); }
    catch (e) { prog.fail(e); }
  }
  const resumable = $derived((task ? task.resumable : p?.resumable) || []);
  const ago = (iso: string) => { const m = Math.round((Date.now() - new Date(iso).getTime()) / 6e4); return m < 60 ? `${m} min` : m < 1440 ? `${Math.round(m / 60)} h` : `${Math.round(m / 1440)} d`; };
  async function closeTab(t: Tab) {
    if (!v) return;
    if (t.kind === "term") {
      const s = work.session(t.term);
      if (t.term!.alive && (t.term!.kind === "agent" || Date.now() / 1000 - t.term!.lastOutput < 5) &&
          !(await ui.ask({ title: `Encerrar ${t.term!.title}?`, message: s?.status === "working" ? "O agente está trabalhando agora." : "O processo deste terminal será encerrado.", confirm: "Encerrar", danger: true }))) return;
      await post("terms/close", { id: t.term!.id }).catch(e => ui.error(e));
      drop(t.term!.id);
      await work.load();
    } else {
      if (dirty[t.key] && !(await ui.ask({ title: `${t.file!.path.split("/").pop()} tem alterações não salvas`, message: "Fechar e perder as alterações?", confirm: "Fechar sem salvar", danger: true }))) return;
      v.files = v.files.filter(f => f.key !== t.key);
      forget(t.key);
    }
    v.order = v.order.filter(k => k !== t.key);
    if (v.active === t.key) v.active = null;
  }
  setOpener((rel, line) => openFile(rel, line));
  function openFile(path: string, line?: number) {
    if (!p || !v) return;
    const key = keyOf(p.id, v.scope, path);
    const ex = v.files.find(f => f.key === key);
    if (ex) ex.line = line;
    else v.files = [...v.files, { k: "file", key, path, scope: v.scope || null, line }];
    focusTab(key);
  }
  /** Projeto numa janela própria (outro monitor) — janela nativa do app. */
  function popOut(x: Project) {
    send({ type: "openWindow", hash: "/solo/" + x.id, title: `${x.name} — Commitdeck` });
  }
  async function openProjectMenu() { /* menu montado em projectItems */ }
  const projectItems = $derived([
    { heading: "Abrir projeto" },
    ...repos.local.filter(r => r.exists && !work.projects.some(x => x.id === r.id)).slice(0, 40)
      .map(r => ({ label: r.name, icon: FolderGit2, onclick: async () => { const id = await work.open(r.id); go("/work/" + id, "soft"); } })),
    { separator: true },
    { label: "Abrir pasta…", icon: FolderOpen, onclick: async () => { const f = await pickFolder("Pasta do projeto (repositório Git)"); if (f) { try { const id = await work.open(undefined, f); go("/work/" + id, "soft"); } catch (e) { ui.error(e); } } } },
  ]);
  void openProjectMenu;
  const agentItems = $derived([
    { heading: "Abrir agente" + (task ? " na tarefa" : "") },
    ...work.ai.filter(a => a.installed).map(a => ({ label: `${a.label} · ${a.name}`, icon: Bot, onclick: () => newAgent(a.id) })),
    ...(work.ai.some(a => a.installed) ? [] : [{ label: "Nenhuma CLI de IA instalada", disabled: true }]),
  ]);
  const taskTone = (t: Task) => {
    const ss = t.terms.filter(x => x.kind === "agent").map(x => work.session(x)?.status);
    return ss.includes("needs-you") ? "warn" : ss.includes("working") ? "accent" : ss.includes("done") ? "good" : t.terms.some(x => x.alive) ? "muted" : "off";
  };

  // ------------------------------------------------------------ atalhos
  function onKey(e: KeyboardEvent) {
    if (router.view !== "work" || !p || !v) return;
    const mod = e.metaKey || e.ctrlKey;
    if (!mod) return;
    const k = e.key.toLowerCase();
    if (k === "p" && !e.shiftKey) { e.preventDefault(); v.left = "files"; setTimeout(() => document.querySelector<HTMLInputElement>(".work .ft input")?.focus(), 30); }
    else if (k === "f" && e.shiftKey) { e.preventDefault(); v.left = "search"; setTimeout(() => document.querySelector<HTMLInputElement>(".work .ft input")?.focus(), 30); }
    else if (k === "t" && !e.shiftKey) { e.preventDefault(); newTerm(); }
    else if (k === "w" && activeTab && (activeTab.kind === "term" || activeTab.kind === "file")) { e.preventDefault(); closeTab(activeTab); }
    else if (/^[1-9]$/.test(k) && work.projects[+k - 1]) { e.preventDefault(); go("/work/" + work.projects[+k - 1].id, "soft"); }
  }
</script>

{#snippet paneOf(tab: Tab | null)}
          {#if tab?.kind === "term" && tab.term}
            {@const tid = tab.term.id}
            {#key tid}<Terminal id={tid} />{/key}
          {:else if tab?.kind === "git"}
            {#key (task?.repoId || p!.id)}<RepoDetail repoId={task?.repoId || p!.id} embedded />{/key}
          {:else if tab?.kind === "review" && task}
            {#key task.id}<Review project={p!} {task} onagent={(id) => focusTab("t:" + id)} />{/key}
          {:else if tab?.kind === "file" && tab.file}
            <Editor repoId={p!.id} taskId={v!.scope} path={tab.file.path} line={tab.file.line || 0} />
          {:else}
            <div class="start">
              <h3>{task ? task.title : p!.name}</h3>
              <p class="muted">{task ? `Worktree em ${task.path.replace(/^\/Users\/[^/]+/, "~")}` : "Checkout principal"}</p>
              {#if resumable.length}
                <div class="resume">
                  <span class="small muted">Retomar de onde parou</span>
                  {#each resumable as r (r.sid)}
                    <button class="btn sm" onclick={() => newAgent(r.account, r.sid)}><AgentIcon provider={r.provider} size={14} /> {r.title} <span class="tiny muted">há {ago(r.updated)}</span></button>
                  {/each}
                </div>
              {/if}
              <div class="cards">
                {#each work.ai.filter(a => a.installed).slice(0, 6) as a (a.id)}
                  <button class="cardbtn" onclick={() => newAgent(a.id)}><AgentIcon provider={a.provider} size={20} /><span><b>{a.label}</b><span class="tiny muted">{a.name}{a.email ? " · " + a.email : ""}</span></span></button>
                {/each}
                <button class="cardbtn" onclick={() => newTerm()}><SquareTerminal size={20} /><span><b>Terminal</b><span class="tiny muted">shell na pasta {task ? "da tarefa" : "do projeto"}</span></span></button>
                {#if !task}<button class="cardbtn accent" onclick={() => (newTask = {})}><Plus size={20} /><span><b>Nova tarefa</b><span class="tiny muted">branch + worktree + agente</span></span></button>{/if}
              </div>
              <p class="tiny muted keys"><span class="kbd">⌘P</span> abrir arquivo · <span class="kbd">⌘⇧F</span> buscar · <span class="kbd">⌘T</span> terminal · <span class="kbd">⌘W</span> fechar aba</p>
            </div>
          {/if}
{/snippet}

<svelte:window onkeydown={onKey} />

<div class="work">
  <!-- abas de projeto -->
  <div class="ptabs" class:hidden={solo}>
    {#each work.projects as x (x.id)}
      {@const n = work.agents.filter(a => a.project.id === x.id && a.session?.status === "needs-you").length}
      {@const busy = work.agents.some(a => a.project.id === x.id && a.session?.status === "working")}
      <div class="ptab" class:on={x.id === p?.id} role="tab" tabindex="0" aria-selected={x.id === p?.id}
        onclick={() => go("/work/" + x.id, "soft")} onkeydown={(e) => e.key === "Enter" && go("/work/" + x.id, "soft")}
        oncontextmenu={(e) => ui.contextMenu(e, [
          { label: "Abrir em janela própria", icon: AppWindow, onclick: () => popOut(x) },
          { label: "Ajustes do projeto", icon: Settings2, onclick: () => { go("/work/" + x.id, "soft"); settingsOpen = true; } },
          { separator: true },
          { label: "Fechar projeto", icon: X, onclick: () => work.close(x.id) },
        ])}>
        <ProviderIcon provider={(x.provider as any) || null} size={13} />
        <span class="ell">{x.name}</span>
        {#if n}<span class="badge warn" title="agente(s) precisando de você">{n}</span>{:else if busy}<span class="live" title="agente trabalhando"></span>{/if}
        <button class="x" title="Fechar projeto" onclick={(e) => { e.stopPropagation(); work.close(x.id); }}><X size={12} /></button>
      </div>
    {/each}
    <Menu items={projectItems} label="Abrir projeto" align="left">{#snippet trigger()}<span class="btn sm ghost addp"><Plus size={14} /> Projeto</span>{/snippet}</Menu>
    <span class="grow"></span>
    {#if work.projects.some(x => x.tasks.length)}<button class="btn sm" class:primary={board} onclick={() => go(board ? "/work" : "/work/board", "soft")}><LayoutGrid size={14} /> Quadro</button>{/if}
  </div>

  {#if board}
    <div class="boardwrap"><Board onopen={(bp, bt) => { go("/work/" + bp.id, "soft"); setTimeout(() => { const vv = views[bp.id]; if (vv) { vv.scope = bt.id; vv.active = null; } }, 60); }} /></div>
  {:else if !p || !v}
    <div class="empty">
      <Empty title={work.loaded ? "Abra um projeto" : "Carregando…"} text="Cada projeto abre numa aba: agentes de IA, terminais, arquivos e tarefas em worktree, lado a lado.">
        {#if work.loaded}<Menu items={projectItems} align="left">{#snippet trigger()}<span class="btn primary"><FolderGit2 size={14} /> Abrir projeto</span>{/snippet}</Menu>{/if}
      </Empty>
    </div>
  {:else}
    <div class="grid" class:noright={!v.right || activeTab?.kind === "git"}>
      <!-- esquerda: escopo (principal / tarefas) + arquivos -->
      <aside class="card left">
        <div class="scopes">
          <button class="sc" class:on={!v.scope} onclick={() => setScope(null)}>
            <FolderGit2 size={14} /><span class="grow ell"><b>{p.name}</b><span class="tiny muted">checkout principal</span></span>
            {#if p.terms.length}<span class="tiny muted">{p.terms.length}</span>{/if}
            <span class="gear" role="button" tabindex="0" title="Ajustes do projeto" onclick={(e) => { e.stopPropagation(); settingsOpen = true; }} onkeydown={(e) => e.key === "Enter" && (settingsOpen = true)}><Settings2 size={13} /></span>
          </button>
          <div class="sch"><span>Tarefas</span><button class="btn sm ghost" onclick={() => (newTask = {})}><Plus size={13} /> Nova</button></div>
          {#each [...new Set(p.tasks.filter(t => t.group).map(t => t.group!))].filter(g => p!.tasks.filter(t => t.group === g).length > 1) as g (g)}
            <button class="cmp" onclick={() => (comparing = g)}><GitCompareArrows size={13} /> Comparar {p.tasks.filter(t => t.group === g).length} soluções · {g}</button>
          {/each}
          {#each p.tasks as t (t.id)}
            <button class="sc task" class:on={v.scope === t.id} onclick={() => setScope(t.id)} title={t.branch}>
              <span class="dot {taskTone(t)}"></span>
              <span class="grow ell"><b>{t.title}</b><span class="tiny muted mono ell"><GitBranch size={10} /> {t.branch}</span></span>
              <span class="ags">{#each t.terms.filter(x => x.kind === "agent") as a (a.id)}<AgentIcon provider={a.meta.provider} size={13} />{/each}</span>
            </button>
          {:else}
            <div class="none">Nenhuma tarefa. “Nova” cria uma branch e um worktree — o agente trabalha lá sem mexer no seu checkout.</div>
          {/each}
        </div>
        <div class="lm">
          <button class:on={v.left === "files"} onclick={() => (v.left = "files")}><Code2 size={13} /> Arquivos</button>
          <button class:on={v.left === "search"} onclick={() => (v.left = "search")}><Search size={13} /> Busca</button>
        </div>
        <div class="tree">
          {#key p.id + (v.scope || "")}<FileTree repoId={p.id} taskId={v.scope} mode={v.left} onopen={openFile} active={activeTab?.file?.path || null} />{/key}
        </div>
      </aside>

      <!-- centro: abas -->
      <section class="card center">
        <div class="tabs">
          <div class="tl">
            {#each tabs as t (t.key)}
              {@const s = t.kind === "term" ? work.session(t.term) : null}
              <div class="tab" class:on={activeTab?.key === t.key} class:dead={t.kind === "term" && !t.term?.alive} role="tab" tabindex="0" aria-selected={activeTab?.key === t.key}
                onclick={() => focusTab(t.key)} onkeydown={(e) => e.key === "Enter" && focusTab(t.key)} onauxclick={(e) => e.button === 1 && closeTab(t)}
                oncontextmenu={(e) => ui.contextMenu(e, [
                  { label: "Abrir ao lado", icon: Columns2, onclick: () => { if (v) { if (v.active === t.key || activeTab?.key === t.key) v.active = tabs.find(x => x.key !== t.key)?.key || null; v.split = t.key; } }, disabled: tabs.length < 2 },
                  ...(v?.split ? [{ label: "Fechar a divisão", onclick: () => v && (v.split = null) }] : []),
                  ...(t.kind !== "review" ? [{ separator: true }, { label: "Fechar", icon: X, onclick: () => closeTab(t) }] : []),
                ])}>
                {#if t.kind === "term" && t.term?.kind === "agent"}<AgentIcon provider={t.term.meta.provider} size={13} />
                {:else if t.kind === "term"}<SquareTerminal size={13} />
                {:else if t.kind === "review"}<GitCompareArrows size={13} />
                {:else if t.kind === "git"}<GitBranch size={13} />
                {:else}<Code2 size={13} />{/if}
                <span class="ell">{t.kind === "term" ? t.term!.title : t.kind === "review" ? "Revisão" : t.kind === "git" ? "Git" : t.file!.path.split("/").pop()}</span>
                {#if s}<span class="sdot {STATUS[s.status]?.[1]}" class:pulse={s.status === "working"} title={STATUS[s.status]?.[0]}></span>{/if}
                {#if t.kind === "file" && dirty[t.key]}<span class="dirty" title="não salvo"></span>{/if}
                {#if t.kind !== "review" && t.kind !== "git"}<button class="x" title="Fechar (⌘W)" onclick={(e) => { e.stopPropagation(); closeTab(t); }}><X size={11} /></button>{/if}
              </div>
            {/each}
          </div>
          <div class="tact">
            <Menu items={agentItems} align="right">{#snippet trigger()}<span class="btn sm"><Bot size={14} /> Agente <ChevronDown size={12} /></span>{/snippet}</Menu>
            <button class="btn sm ghost" title="Novo terminal (⌘T)" onclick={() => newTerm()}><SquareTerminal size={14} /></button>
            <button class="btn sm ghost icon" title="Painel do agente" onclick={() => (v.right = !v.right)}><PanelRight size={15} /></button>
          </div>
        </div>
        <div class="body" class:split={!!splitTab}>
          <div class="pane">{@render paneOf(activeTab)}</div>
          {#if splitTab}<div class="pane second">
            <button class="unsplit" title="Fechar a divisão" onclick={() => v && (v.split = null)}><X size={12} /></button>
            {@render paneOf(splitTab)}</div>{/if}
        </div>
      </section>

      {#if v.right && activeTab?.kind !== "git"}
        <aside class="card right">
          <AgentPanel project={p} {task} term={activeTerm} onremoved={() => setScope(null)} onreview={() => task && focusTab("r:" + task.id)} />
        </aside>
      {/if}
    </div>
  {/if}
</div>

{#if settingsOpen && p}<ProjectSettings project={p} onclose={() => (settingsOpen = false)} />{/if}

{#if comparing && p}
  <Compare project={p} tasks={p.tasks.filter(t => t.group === comparing)} onclose={() => (comparing = null)} onview={(t) => setScope(t.id)} />
{/if}

{#if newTask && p}
  <NewTask project={p} preset={newTask.preset} onclose={() => (newTask = null)} oncreated={(ids) => { newTask = null; setScope(ids[0]); }} />
{/if}

<style>
  .work { height: 100%; display: flex; flex-direction: column; padding: 10px 14px 14px; gap: 10px; min-height: 0; }
  .ptabs { display: flex; align-items: center; gap: 4px; overflow-x: auto; flex: none; padding-bottom: 2px; }
  .ptab { display: flex; align-items: center; gap: 7px; height: 32px; padding: 0 6px 0 11px; border-radius: 9px; border: 1px solid transparent; color: var(--text-2);
    font: 500 13px var(--font); cursor: pointer; max-width: 230px; transition: background var(--t), color var(--t), border-color var(--t); flex: none; }
  .ptab:hover { background: var(--surface-2); color: var(--text); }
  .ptab.on { background: var(--surface); border-color: var(--line-2); color: var(--text); font-weight: 600; box-shadow: var(--shadow-1); }
  .ptab .x, .tab .x { display: grid; place-items: center; width: 18px; height: 18px; border: 0; border-radius: 5px; background: none; color: var(--muted); cursor: pointer; opacity: 0; transition: opacity var(--t-fast); flex: none; }
  .ptab:hover .x, .ptab.on .x, .tab:hover .x, .tab.on .x { opacity: 1; }
  .ptab .x:hover, .tab .x:hover { background: var(--surface-3); color: var(--text); }
  .badge { font: 650 10.5px/1 var(--font); padding: 3px 6px; border-radius: 99px; background: var(--warn); color: #1a1205; }
  .live { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); animation: ping 1.2s var(--ease) infinite; }
  @keyframes ping { 0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--accent) 60%, transparent); } 80%, 100% { box-shadow: 0 0 0 6px transparent; } }
  .addp { color: var(--muted); }
  .ptabs .grow { flex: 1; }
  .ptabs.hidden { display: none; }
  .boardwrap { flex: 1; min-height: 0; }
  .cmp { display: flex; align-items: center; gap: 6px; margin: 2px 4px 4px; padding: 6px 8px; border: 1px dashed var(--accent-line); border-radius: 8px;
    background: var(--accent-soft); color: var(--accent); font: 600 12px var(--font); cursor: pointer; text-align: left; }
  .empty { flex: 1; display: grid; place-items: center; }
  .grid { flex: 1; min-height: 0; display: grid; grid-template-columns: 260px minmax(0, 1fr) 300px; gap: 10px; }
  .grid.noright { grid-template-columns: 260px minmax(0, 1fr); }
  .card { min-height: 0; overflow: hidden; }
  .left { display: flex; flex-direction: column; }
  .scopes { display: flex; flex-direction: column; gap: 2px; padding: 8px; max-height: 45%; overflow: auto; flex: none; }
  .sc { display: flex; align-items: center; gap: 9px; width: 100%; padding: 6px 8px; border: 0; border-radius: 8px; background: none; color: var(--text-2);
    font: 13px var(--font); text-align: left; cursor: pointer; transition: background var(--t); animation: rise 0.25s var(--ease-out) both; }
  .sc:hover { background: var(--surface-2); }
  .sc.on { background: var(--accent-soft); color: var(--text); }
  .sc .grow { display: grid; min-width: 0; flex: 1; }
  .sc b { font-weight: 600; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .sc .tiny { display: flex; align-items: center; gap: 3px; }
  .ags { display: flex; gap: 2px; }
  .gear { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 6px; color: var(--muted); opacity: 0; transition: opacity var(--t-fast); }
  .sc:hover .gear { opacity: 1; }
  .gear:hover { background: var(--surface-3); color: var(--text); }
  .sch { display: flex; align-items: center; justify-content: space-between; padding: 10px 8px 2px; font: 650 10.5px/1 var(--font); text-transform: uppercase; letter-spacing: 0.07em; color: var(--muted); }
  .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; background: var(--line-3); }
  .dot.accent { background: var(--accent); animation: ping 1.2s var(--ease) infinite; } .dot.warn { background: var(--warn); } .dot.good { background: var(--good); } .dot.muted { background: var(--text-2); }
  .none { font-size: 12px; color: var(--muted); padding: 4px 8px 8px; }
  .lm { display: flex; gap: 2px; padding: 0 8px; border-top: 1px solid var(--line); padding-top: 8px; }
  .lm button { flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: 5px; height: 26px; border: 0; border-radius: 7px; background: none;
    color: var(--muted); font: 600 12px var(--font); cursor: pointer; }
  .lm button.on { background: var(--surface-3); color: var(--text); }
  .tree { flex: 1; min-height: 0; }
  .center { display: flex; flex-direction: column; }
  .tabs { display: flex; align-items: center; gap: 6px; border-bottom: 1px solid var(--line); padding: 4px 6px 0; flex: none; }
  .tl { flex: 1; display: flex; gap: 2px; overflow-x: auto; min-width: 0; }
  .tab { display: flex; align-items: center; gap: 7px; height: 32px; padding: 0 6px 0 10px; border-radius: 8px 8px 0 0; color: var(--muted); font: 500 12.5px var(--font);
    cursor: pointer; max-width: 220px; flex: none; position: relative; transition: background var(--t-fast), color var(--t-fast); }
  .tab:hover { background: var(--surface-2); color: var(--text-2); }
  .tab.on { background: var(--surface-2); color: var(--text); }
  .tab.on::after { content: ""; position: absolute; left: 8px; right: 8px; bottom: 0; height: 2px; border-radius: 2px; background: var(--accent); }
  .tab.dead { opacity: 0.55; }
  .sdot { width: 7px; height: 7px; border-radius: 50%; background: var(--muted); flex: none; }
  .sdot.accent { background: var(--accent); } .sdot.good { background: var(--good); } .sdot.warn { background: var(--warn); } .sdot.info { background: var(--info); }
  .pulse { animation: ping 1.2s var(--ease) infinite; }
  .dirty { width: 7px; height: 7px; border-radius: 50%; background: var(--text-2); flex: none; }
  .tact { display: flex; align-items: center; gap: 4px; padding-bottom: 4px; }
  .body { flex: 1; min-height: 0; position: relative; display: grid; grid-template-columns: minmax(0, 1fr); }
  .body.split { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .pane { position: relative; min-width: 0; min-height: 0; }
  .pane.second { border-left: 1px solid var(--line); }
  .unsplit { position: absolute; z-index: 5; top: 6px; right: 8px; display: grid; place-items: center; width: 22px; height: 22px; border: 0; border-radius: 6px;
    background: var(--surface-3); color: var(--text-2); cursor: pointer; opacity: 0.6; }
  .unsplit:hover { opacity: 1; }
  .start { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; padding: 24px; text-align: center; animation: fade 0.3s; }
  .start h3 { margin: 0; font-size: 18px; }
  .start p { margin: 0; }
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 8px; width: min(720px, 100%); margin: 18px 0 10px; }
  .cardbtn { display: flex; align-items: center; gap: 12px; padding: 14px; border-radius: 12px; border: 1px solid var(--line-2); background: var(--surface-2);
    color: var(--text); font: 13px var(--font); text-align: left; cursor: pointer; transition: border-color var(--t), transform var(--t) var(--spring); }
  .cardbtn:hover { border-color: var(--accent); transform: translateY(-2px); }
  .cardbtn span { display: grid; min-width: 0; }
  .cardbtn.accent { border-style: dashed; color: var(--accent); }
  .cardbtn :global(svg) { flex: none; }
  .keys { margin-top: 8px; }
  .resume { display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 6px; margin-top: 14px; }
  .right { overflow: hidden; }
  @media (max-width: 1100px) { .grid, .grid.noright { grid-template-columns: 220px minmax(0, 1fr); } .right { display: none; } }
</style>
