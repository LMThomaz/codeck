<script lang="ts">
  import { ExternalLink, MessageSquare } from "@lucide/svelte";
  import { ago } from "../lib/format";
  import { store } from "../lib/store.svelte";
  import Empty from "../components/Empty.svelte";
  import Page from "../components/Page.svelte";
  import ProviderIcon from "../components/ProviderIcon.svelte";
  import Segmented from "../components/Segmented.svelte";
  import Skeleton from "../components/Skeleton.svelte";
  import SourceFilter from "../components/SourceFilter.svelte";
  import Toolbar from "../components/Toolbar.svelte";

  let q = $state("");
  let reason = $state("");
  let org = $state("");
  const s = $derived(store.s);
  const list = $derived((s?.issues || []).filter(i => (!reason || i.reason === reason) && (!org || i.org === org)
    && (!q || `${i.number} ${i.title} ${i.repo} ${i.labels.map(l => l.name).join(" ")} ${i.type}`.toLowerCase().includes(q.toLowerCase()))));
  const count = (r: string) => (s?.issues || []).filter(i => i.reason === r).length;
  const REASON: Record<string, string> = { assigned: "atribuída a você", created: "criada por você", mentioned: "menciona você" };
</script>

<Page title="Issues e tarefas" sub="Issues do GitHub e itens de trabalho do Azure Boards atribuídos a você">
  {#if !s?.lastIssuePoll}
    <Skeleton rows={9} />
  {:else}
    <Toolbar bind:query={q} placeholder="Buscar por título, número, repositório, etiqueta…">
      {#snippet left()}
        <Segmented bind:value={reason} options={[{ value: "", label: "Tudo", count: s.issues.length }, { value: "assigned", label: "Atribuídas", count: count("assigned") },
          { value: "created", label: "Criadas por mim", count: count("created") }, { value: "mentioned", label: "Menções", count: count("mentioned") }]} />
      {/snippet}
      <SourceFilter bind:value={org} items={s.issues} />
    </Toolbar>
    <div class="card scroll">
      {#each list as i (i.key)}
        <a class="list-row" href={i.url} target="_blank" rel="noopener">
          <span class="ic" class:wi={i.provider === "azure"}><ProviderIcon provider={i.provider} size={15} /></span>
          <div class="grow">
            <div class="t"><span class="num">#{i.number}</span><span class="title ell">{i.title}</span></div>
            <div class="meta">
              <span>{i.repo}</span>
              {#if i.provider === "azure"}<span class="pill neutral">{i.type}</span><span class="pill info">{i.state}</span>{/if}
              {#each i.labels.slice(0, 5) as l (l.name)}<span class="label-chip" style="--c:{l.color || 'var(--muted)'}">{l.name}</span>{/each}
              <span>{REASON[i.reason] || ""} · atualizada há {ago(i.updated)}</span>
              {#if i.comments}<span class="row" style="gap:4px"><MessageSquare size={11} />{i.comments}</span>{/if}
            </div>
          </div>
          <ExternalLink size={14} class="muted" />
        </a>
      {:else}
        <Empty done={!q && !reason && !org} title={q || reason || org ? "Nada com esses filtros" : "Nenhuma issue aberta com você"} />
      {/each}
    </div>
    {#if Object.keys(s.issueErrors || {}).length}
      <p class="small muted note">Algumas origens não responderam: {Object.entries(s.issueErrors).map(([k, v]) => `${k} (${v.slice(0, 80)})`).join("; ")}</p>
    {/if}
  {/if}
</Page>

<style>
  .scroll { flex: 1; min-height: 0; overflow: auto; overscroll-behavior: contain; }
  .ic { width: 32px; height: 32px; border-radius: 10px; display: grid; place-items: center; background: var(--surface-2); border: 1px solid var(--line); }
  .t { display: flex; align-items: baseline; gap: 7px; min-width: 0; }
  .num { color: var(--muted); font-size: 12.5px; flex-shrink: 0; }
  .title { font-weight: 600; }
  .label-chip { font: 600 11px/1 var(--font); padding: 4px 8px; border-radius: 99px; color: var(--c); background: color-mix(in srgb, var(--c) 14%, transparent);
    border: 1px solid color-mix(in srgb, var(--c) 30%, transparent); }
  .note { margin: 10px 2px 0; flex: none; }
</style>
