<script lang="ts">
  // Editor de catálogo: nome, cor, pasta-base para clonar e as origens (organização/projeto do Azure, organização/conta do GitHub).
  import { Check, Plus, X } from "@lucide/svelte";
  import { get, post } from "../../lib/api";
  import { repos } from "../../lib/repos.svelte";
  import { go } from "../../lib/router.svelte";
  import { store } from "../../lib/store.svelte";
  import type { Catalog, CatalogSource } from "../../lib/types";
  import { ui } from "../../lib/ui.svelte";
  import Drawer from "../Drawer.svelte";
  import ProviderIcon from "../ProviderIcon.svelte";

  let { catalog = null, onclose }: { catalog?: Catalog | null; onclose: () => void } = $props();
  const COLORS = ["#3F8CF0", "#22C38E", "#F0A23F", "#E5577B", "#8B6CF0", "#2EC4D6", "#F06A3F", "#9AA4B2"];
  // svelte-ignore state_referenced_locally
  let name = $state(catalog?.name || "");
  // svelte-ignore state_referenced_locally
  let color = $state(catalog?.color || COLORS[repos.catalogs.length % COLORS.length]);
  // svelte-ignore state_referenced_locally
  // svelte-ignore state_referenced_locally
  let description = $state(catalog?.description || "");
  // svelte-ignore state_referenced_locally
  let sources = $state<CatalogSource[]>(catalog?.sources ? JSON.parse(JSON.stringify(catalog.sources)) : []);
  let suggestions = $state<any[] | null>(null);
  let custom = $state({ provider: "github", account: "", owner: "", project: "" });
  let saving = $state(false);

  get<{ suggestions: any[] }>("catalogs/suggestions").then(r => (suggestions = r.suggestions)).catch(() => (suggestions = []));
  const keyOf = (s: CatalogSource) => `${s.provider}|${s.account}|${s.owner || ""}|${s.project || ""}`.toLowerCase();
  const has = (s: CatalogSource) => sources.some(x => keyOf(x) === keyOf(s));
  function toggle(s: CatalogSource) {
    sources = has(s) ? sources.filter(x => keyOf(x) !== keyOf(s)) : [...sources, s];
    if (!name && sources.length === 1) name = (suggestions || []).find(x => keyOf(x.sources[0]) === keyOf(s))?.name || "";
  }
  function addCustom() {
    const acc = custom.provider === "github" ? store.s?.githubAccounts[0]?.login || "" : store.s?.orgs[0] || "";
    const s: CatalogSource = { provider: custom.provider as any, account: custom.account || acc, owner: custom.owner.trim() || null, project: custom.project.trim() || null };
    if (custom.provider === "github" && !s.owner) return ui.toast("Informe a organização ou usuário do GitHub", "error");
    if (!has(s)) sources = [...sources, s];
    custom = { ...custom, owner: "", project: "" };
  }
  async function save() {
    saving = true;
    try {
      const c = await post<Catalog>("catalogs/save", { id: catalog?.id, name, color, description, sources, extra: catalog?.extra || [], exclude: catalog?.exclude || [] });
      await repos.load(false);
      ui.toast(catalog ? "Catálogo salvo" : "Catálogo criado");
      onclose();
      go("/repos/catalog/" + c.id);
    } catch (e) { ui.error(e); }
    saving = false;
  }
  async function remove() {
    if (!(await ui.ask({ title: `Excluir o catálogo ${catalog!.name}?`, message: "Só o agrupamento some — nenhum repositório é apagado.", confirm: "Excluir", danger: true }))) return;
    await post("catalogs/delete", { id: catalog!.id });
    await repos.load(false);
    onclose();
    go("/repos");
  }
  const srcLabel = (s: CatalogSource) => s.provider === "github" ? `GitHub · ${s.owner || "@" + s.account}` : `Azure · ${s.account}${s.project ? " / " + s.project : ""}`;
</script>

<Drawer title={catalog ? "Editar catálogo" : "Novo catálogo"} subtitle="Agrupe os repositórios de uma empresa ou projeto — clonados ou não" {onclose}>
  <section>
    <label class="label">Nome<input class="input" bind:value={name} placeholder="ex.: Cifal" /></label>
    <div class="colors">{#each COLORS as c (c)}<button class="sw" class:on={c === color} style="background:{c}" aria-label={c} onclick={() => (color = c)}>{#if c === color}<Check size={13} />{/if}</button>{/each}</div>
    <label class="label">Descrição <span class="muted">(opcional)</span><input class="input" bind:value={description} placeholder="ex.: APIs e bibliotecas do ERP" /></label>
  </section>

  <section>
    <h4>Origens <span class="muted small">— todos os repositórios delas entram no catálogo</span></h4>
    {#if sources.length}
      <div class="chips">{#each sources as s (keyOf(s))}<span class="chip"><ProviderIcon provider={s.provider} size={12} />{srcLabel(s)}<button aria-label="Remover" onclick={() => toggle(s)}><X size={12} /></button></span>{/each}</div>
    {/if}
    <h5>Sugestões das contas conectadas</h5>
    {#if suggestions === null}<div class="sk"><i class="shim" style="height:30px"></i><i class="shim" style="height:30px"></i></div>
    {:else}
      <div class="sugs">
        {#each suggestions as sg (sg.label)}
          <button class="sug" class:on={has(sg.sources[0])} onclick={() => toggle(sg.sources[0])}>
            <ProviderIcon provider={sg.sources[0].provider} size={14} /><span class="ell">{sg.label}</span>{#if has(sg.sources[0])}<Check size={14} />{/if}
          </button>
        {:else}<p class="small muted">Conecte uma conta do GitHub ou do Azure em Contas e ajustes.</p>{/each}
      </div>
    {/if}
    <h5>Outra origem</h5>
    <div class="custom">
      <select class="select" bind:value={custom.provider}><option value="github">GitHub</option><option value="azure">Azure DevOps</option></select>
      {#if custom.provider === "github"}
        <input class="input" bind:value={custom.owner} placeholder="organização ou usuário (ex.: vercel)" />
      {:else}
        <select class="select" bind:value={custom.account}>{#each store.s?.orgs || [] as o (o)}<option value={o}>{o}</option>{/each}</select>
        <input class="input" bind:value={custom.project} placeholder="projeto (vazio = todos)" />
      {/if}
      <button class="btn" onclick={addCustom}><Plus size={14} /> Adicionar</button>
    </div>
  </section>

  {#snippet footer()}
    {#if catalog}<button class="btn danger" onclick={remove}>Excluir</button>{/if}
    <span class="spacer"></span>
    <button class="btn ghost" onclick={onclose}>Cancelar</button>
    <button class="btn primary" disabled={!name.trim() || !sources.length || saving} onclick={save}>{catalog ? "Salvar" : "Criar catálogo"}</button>
  {/snippet}
</Drawer>

<style>
  section { padding: 16px 0; border-bottom: 1px solid var(--line); display: grid; gap: 10px; }
  h4 { margin: 0; font: 650 11px/1 var(--font); text-transform: uppercase; letter-spacing: 0.07em; color: var(--text-2); }
  h5 { margin: 6px 0 0; font-size: 12px; color: var(--text-2); }
  p { margin: 0; }
  .colors { display: flex; gap: 8px; }
  .sw { width: 26px; height: 26px; border-radius: 8px; border: 2px solid transparent; cursor: pointer; display: grid; place-items: center; color: #fff;
    transition: transform var(--t) var(--spring); }
  .sw:hover { transform: scale(1.1); }
  .sw.on { border-color: var(--text); }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 4px 4px 10px; border-radius: 99px; background: var(--accent-soft); border: 1px solid var(--accent-line);
    font-size: 12.5px; animation: rise 0.25s var(--ease-out); }
  .chip button { border: 0; background: none; color: var(--text-2); cursor: pointer; display: grid; place-items: center; width: 20px; height: 20px; border-radius: 50%; }
  .chip button:hover { background: var(--surface-3); }
  .sugs { display: grid; gap: 4px; max-height: 260px; overflow: auto; }
  .sug { display: flex; align-items: center; gap: 9px; height: 34px; padding: 0 10px; border-radius: 8px; border: 1px solid var(--line); background: var(--surface-2);
    color: var(--text); font: 13px var(--font); cursor: pointer; text-align: left; transition: border-color var(--t), background var(--t); }
  .sug span { flex: 1; }
  .sug:hover { border-color: var(--line-3); }
  .sug.on { border-color: var(--accent); background: var(--accent-soft); }
  .sug.on :global(svg:last-child) { color: var(--accent); }
  .custom { display: grid; grid-template-columns: 140px minmax(0, 1fr) auto; gap: 8px; }
  .custom:has(select + select) { grid-template-columns: 140px 1fr 1fr auto; }
  .sk { display: grid; gap: 6px; }
</style>
