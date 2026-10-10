<script lang="ts">
  // Repositórios: os locais registrados e os catálogos (repositórios de uma org/projeto, clonados ou não).
  import { Download, FolderPlus, FolderSearch, Link, Pencil, Plus, RefreshCw } from "@lucide/svelte";
  import { untrack } from "svelte";
  import { get, post } from "../lib/api";
  import { pickFolder } from "../lib/native";
  import { repos } from "../lib/repos.svelte";
  import { go, router, soft } from "../lib/router.svelte";
  import type { CatalogView } from "../lib/types";
  import { ui } from "../lib/ui.svelte";
  import Drawer from "../components/Drawer.svelte";
  import Empty from "../components/Empty.svelte";
  import Page from "../components/Page.svelte";
  import CatalogEditor from "../components/repo/CatalogEditor.svelte";
  import RepoRow from "../components/repo/RepoRow.svelte";
  import Segmented from "../components/Segmented.svelte";
  import Skeleton from "../components/Skeleton.svelte";
  import Toolbar from "../components/Toolbar.svelte";

  const catalogId = $derived(router.parts[1] === "catalog" ? router.parts[2] : null);
  let view = $state<CatalogView | null>(null);
  let loading = $state(false);
  let q = $state("");
  let filter = $state("all");
  let jobs = $state<Record<string, any>>({});
  let editing = $state<"new" | "edit" | null>(router.parts[1] === "new-catalog" ? "new" : null);
  let adding = $state(router.parts[1] === "add");
  let cloneUrl = $state("");
  let cloneDest = $state("");

  async function loadCatalog(force = false) {
    if (!catalogId) return;
    loading = !view || view.id !== catalogId;
    try { view = await get<CatalogView>("catalog", { id: catalogId, force: force ? 1 : 0 }); }
    catch (e) { ui.error(e); }
    loading = false;
  }
  $effect(() => {
    const cid = catalogId;   // só a troca de catálogo dispara a carga (o resto é lido sem rastrear)
    untrack(() => { view = null; if (cid) loadCatalog(); else repos.load(); });
  });

  const list = $derived.by(() => {
    const t = q.trim().toLowerCase();
    if (catalogId && view) {
      return view.repos.filter(r => (filter === "all" || (filter === "cloned" ? r.cloned : !r.cloned))
        && (!t || `${r.name} ${r.description} ${r.owner} ${r.language || ""}`.toLowerCase().includes(t)));
    }
    return [];
  });
  const locals = $derived(repos.local.filter(r => (filter === "all" || (filter === "dirty" ? (r.status?.changes || 0) > 0 : filter === "ahead" ? (r.status?.ahead || 0) + (r.status?.behind || 0) > 0 : true))
    && (!q || `${r.name} ${r.path} ${r.slug || ""}`.toLowerCase().includes(q.toLowerCase()))));

  function watch(key: string, job: any) {
    jobs = { ...jobs, [key]: job };
    const tick = async () => {
      try {
        const j = await get("jobs", { id: job.id });
        jobs = { ...jobs, [key]: j };
        if (j.status === "running") return setTimeout(tick, 600);
        if (j.status === "done") { ui.toast(`Clonado em ${j.dest}`); await repos.load(); await loadCatalog(); }
        else ui.toast(`Falhou ao clonar: ${j.error}`, "error");
      } catch (e) { ui.error(e); }
    };
    setTimeout(tick, 500);
  }
  async function clone(key: string) {
    if (!view?.baseDir) {
      const p = await pickFolder("Onde clonar os repositórios deste catálogo?");
      if (!p) return;
      await post("catalogs/save", { ...view, baseDir: p });
      await loadCatalog();
    }
    try { watch(key, await post("catalogs/clone", { id: catalogId, repoKey: key })); } catch (e) { ui.error(e); }
  }
  async function cloneAll() {
    const pending = view!.repos.filter(r => !r.cloned && !r.archived);
    if (!(await ui.ask({ title: `Clonar ${pending.length} repositório(s)?`, message: `Vão para ${view!.baseDir}. Eles são clonados um de cada vez.`, confirm: "Clonar todos" }))) return;
    for (const r of pending) {
      try {
        const job = await post("catalogs/clone", { id: catalogId, repoKey: r.key });
        jobs = { ...jobs, [r.key]: job };
        while (true) {
          await new Promise(res => setTimeout(res, 700));
          const j = await get("jobs", { id: job.id });
          jobs = { ...jobs, [r.key]: j };
          if (j.status !== "running") break;
        }
      } catch (e) { ui.error(e); }
    }
    await repos.load();
    await loadCatalog();
    ui.toast("Clones concluídos");
  }
  async function addFolder() {
    const p = await pickFolder("Escolha a pasta de um repositório Git");
    if (!p) return;
    try { const r = await post("repos/add", { path: p }); await repos.load(); adding = false; ui.toast(`${r.name} adicionado`); go("/repo/" + r.id); }
    catch (e) { ui.error(e); }
  }
  async function scanFolder() {
    const p = await pickFolder("Escolha uma pasta para procurar repositórios dentro dela");
    if (!p) return;
    try { const r = await post("repos/scan", { path: p, depth: 3 }); await repos.load(); adding = false; ui.toast(`${r.found} repositório(s) encontrado(s)`); }
    catch (e) { ui.error(e); }
  }
  async function cloneByUrl() {
    if (!cloneUrl.trim()) return;
    let dest = cloneDest.trim();
    if (!dest) {
      const base = await pickFolder("Pasta onde clonar");
      if (!base) return;
      dest = base.replace(/\/$/, "") + "/" + cloneUrl.trim().replace(/\.git$/, "").split(/[/:]/).pop();
    }
    try {
      const job = await post("repos/clone", { url: cloneUrl.trim(), dest });
      adding = false;
      watch(cloneUrl, job);
      ui.toast("Clonando…", "info");
    } catch (e) { ui.error(e); }
  }
  const counts = $derived(view ? { all: view.repos.length, cloned: view.repos.filter(r => r.cloned).length, notCloned: view.repos.filter(r => !r.cloned).length } : null);
</script>

<Page title={catalogId ? view?.name || "Catálogo" : "Repositórios"}
  sub={catalogId ? (view ? `${view.counts.cloned} de ${view.counts.total} clonados${view.baseDir ? " · " + view.baseDir.replace(/^\/Users\/[^/]+/, "~") : ""}` : "carregando…") : "Seus repositórios locais e catálogos de GitHub e Azure DevOps"}>
  {#snippet actions()}
    {#if catalogId && view}
      <button class="btn sm ghost" onclick={() => loadCatalog(true)} title="Ler a lista de novo"><RefreshCw size={14} /></button>
      {#if counts?.notCloned}<button class="btn sm" onclick={cloneAll}><Download size={14} /> Clonar todos ({counts.notCloned})</button>{/if}
      <button class="btn sm" onclick={() => (editing = "edit")}><Pencil size={14} /> Editar</button>
    {:else}
      <button class="btn sm" onclick={() => (adding = true)}><FolderPlus size={14} /> Adicionar local</button>
      <button class="btn sm primary" onclick={() => (editing = "new")}><Plus size={14} /> Novo catálogo</button>
    {/if}
  {/snippet}

  <div class="layout">
    <aside class="card collections">
      <div class="ch">Coleções</div>
      <button class="col-it" class:on={!catalogId} onclick={() => go("/repos", "soft")}><span class="cdot" style="background:var(--text-2)"></span><span class="grow ell">Todos os locais</span><span class="n">{repos.local.length}</span></button>
      {#each repos.catalogs as c (c.id)}
        <button class="col-it" class:on={catalogId === c.id} onclick={() => go("/repos/catalog/" + c.id, "soft")}><span class="cdot" style="background:{c.color}"></span><span class="grow ell">{c.name}</span></button>
      {/each}
      <button class="col-it add" onclick={() => (editing = "new")}><Plus size={13} /> Novo catálogo</button>
    </aside>

    <div class="main">
      <Toolbar bind:query={q} placeholder={catalogId ? "Buscar no catálogo…" : "Buscar repositório local…"}>
        {#snippet left()}
          {#if catalogId}
            <Segmented bind:value={filter} options={[{ value: "all", label: "Todos", count: counts?.all ?? "…" }, { value: "cloned", label: "Clonados", count: counts?.cloned ?? "…" },
              { value: "not", label: "Não clonados", count: counts?.notCloned ?? "…" }]} onchange={() => soft(() => {})} />
          {:else}
            <Segmented bind:value={filter} options={[{ value: "all", label: "Todos", count: repos.local.length },
              { value: "dirty", label: "Com alterações", count: repos.local.filter(r => (r.status?.changes || 0) > 0).length },
              { value: "ahead", label: "Para sincronizar", count: repos.local.filter(r => (r.status?.ahead || 0) + (r.status?.behind || 0) > 0).length }]} />
          {/if}
        {/snippet}
      </Toolbar>
      <div class="card scroll">
        {#if catalogId}
          {#if loading || !view}<Skeleton rows={9} />
          {:else}
            {#each Object.entries(view.errors) as [k, e] (k)}<div class="err">{k}: {e}</div>{/each}
            {#each list as r (r.key)}<RepoRow remote={r} job={jobs[r.key]} onclone={() => clone(r.key)} onchanged={() => loadCatalog()} />
            {:else}<Empty title={q ? "Nada encontrado" : filter === "not" ? "Tudo clonado" : "Catálogo vazio"} done={filter === "not" && !q} text={view.sources.length ? "" : "Edite o catálogo e escolha as origens."} />{/each}
          {/if}
        {:else if !repos.loaded}<Skeleton rows={8} />
        {:else}
          {#each locals as r (r.id)}<RepoRow local={r} />
          {:else}
            <Empty title={q || filter !== "all" ? "Nada com esses filtros" : "Nenhum repositório local ainda"} text="Adicione uma pasta, procure repositórios dentro de uma pasta ou crie um catálogo para clonar.">
              <button class="btn" onclick={addFolder}><FolderPlus size={14} /> Adicionar pasta</button>
              <button class="btn primary" onclick={() => (editing = "new")}><Plus size={14} /> Novo catálogo</button>
            </Empty>
          {/each}
        {/if}
      </div>
    </div>
  </div>
</Page>

{#if editing}
  <CatalogEditor catalog={editing === "edit" ? view : null} onclose={() => { editing = null; if (router.parts[1] === "new-catalog") go("/repos", "soft"); loadCatalog(); }} />
{/if}

{#if adding}
  <Drawer title="Adicionar repositório local" subtitle="Registre clones que já existem ou clone um novo" onclose={() => { adding = false; if (router.parts[1] === "add") go("/repos", "soft"); }} width={520}>
    <div class="opts">
      <button class="opt" onclick={addFolder}><FolderPlus size={20} /><div><b>Uma pasta</b><small>Escolha a pasta de um repositório Git que já existe.</small></div></button>
      <button class="opt" onclick={scanFolder}><FolderSearch size={20} /><div><b>Procurar numa pasta</b><small>Encontra todos os repositórios dentro de uma pasta (até 3 níveis).</small></div></button>
      <div class="opt static"><Link size={20} /><div class="grow"><b>Clonar por URL</b><small>https ou ssh. A credencial vem das contas conectadas no app.</small>
        <input class="input mono" bind:value={cloneUrl} placeholder="https://github.com/dono/repo.git" />
        <input class="input mono" bind:value={cloneDest} placeholder="pasta de destino (vazio = escolher)" />
        <button class="btn primary sm" disabled={!cloneUrl.trim()} onclick={cloneByUrl}><Download size={13} /> Clonar</button></div></div>
    </div>
  </Drawer>
{/if}

<style>
  .layout { flex: 1; min-height: 0; display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 14px; }
  .collections { padding: 8px; display: flex; flex-direction: column; gap: 2px; overflow: auto; }
  .ch { font: 650 10.5px/1 var(--font); text-transform: uppercase; letter-spacing: 0.07em; color: var(--muted); padding: 8px 10px 8px; }
  .col-it { display: flex; align-items: center; gap: 9px; height: 32px; padding: 0 10px; border-radius: 8px; border: 0; background: none; color: var(--text-2);
    font: 500 13px var(--font); cursor: pointer; text-align: left; transition: background var(--t), color var(--t); }
  .col-it:hover { background: var(--surface-2); color: var(--text); }
  .col-it.on { background: var(--accent-soft); color: var(--text); font-weight: 600; }
  .col-it.add { color: var(--accent); margin-top: 4px; }
  .cdot { width: 9px; height: 9px; border-radius: 3px; flex-shrink: 0; }
  .n { font-size: 11.5px; color: var(--muted); }
  .main { min-height: 0; display: flex; flex-direction: column; }
  .scroll { flex: 1; min-height: 0; overflow: auto; overscroll-behavior: contain; }
  .err { margin: 10px 16px 0; padding: 8px 12px; border-radius: 9px; background: var(--bad-soft); color: var(--bad); font-size: 12.5px; }
  .opts { display: grid; gap: 10px; padding-top: 14px; }
  .opt { display: flex; gap: 14px; align-items: flex-start; text-align: left; padding: 14px; border-radius: 12px; border: 1px solid var(--line-2); background: var(--surface-2);
    color: var(--text); font: 13px var(--font); cursor: pointer; transition: border-color var(--t), transform var(--t-fast); }
  .opt:not(.static):hover { border-color: var(--accent); transform: translateY(-1px); }
  .opt.static { cursor: default; }
  .opt :global(svg) { color: var(--accent); flex-shrink: 0; margin-top: 2px; }
  .opt b { display: block; margin-bottom: 2px; }
  .opt small { display: block; color: var(--muted); margin-bottom: 8px; }
  .opt .grow { display: grid; gap: 8px; }
  .opt .grow small { margin-bottom: 0; }
  @media (max-width: 960px) { .layout { grid-template-columns: minmax(0, 1fr); } .collections { display: none; } }
</style>
