<script lang="ts">
  import { ExternalLink } from "@lucide/svelte";
  import { dateTime } from "../lib/format";
  import { store } from "../lib/store.svelte";
  import type { Activity } from "../lib/types";
  import Empty from "../components/Empty.svelte";
  import Page from "../components/Page.svelte";
  import ProviderIcon from "../components/ProviderIcon.svelte";
  import Segmented from "../components/Segmented.svelte";
  import { VOTES } from "../components/pr/votes";

  let who = $state("all");
  let kind = $state("");
  const list = $derived((store.s?.activity || []).filter(a => (who === "all" || (who === "auto" ? a.by === "auto" : a.by !== "auto"))
    && (!kind || (kind === "pr" ? !a.kind : kind === "git" ? a.kind === "git" : a.kind && a.kind !== "git"))));
  const LABEL: Record<string, [string, string]> = {
    "deploy-approve": ["Aprovou deploy", "good"], "deploy-reject": ["Rejeitou deploy", "bad"], permit: ["Liberou permissão", "good"], cancel: ["Cancelou run", "bad"],
    "build-retry": ["Tentou de novo", "neutral"], "build-rerun": ["Rodou de novo", "neutral"], "build-cancel": ["Cancelou build", "bad"],
    archive: ["Arquivou", "neutral"], unarchive: ["Desarquivou", "neutral"], "pr-create": ["Criou PR", "accent"],
  };
  function label(a: Activity): [string, string] {
    if (LABEL[a.action]) return LABEL[a.action];
    if (a.action.startsWith("git-")) return [a.action.slice(4).replace("-", " "), "info"];
    return VOTES[a.vote as number] || ["Removeu o voto", "neutral"];
  }
</script>

<Page title="Histórico" sub="Tudo que você e o piloto fizeram — votos, deploys, builds e operações de Git">
  <div class="toolbar">
    <Segmented bind:value={who} options={[{ value: "all", label: "Tudo" }, { value: "auto", label: "Piloto" }, { value: "manual", label: "Você" }]} />
    <Segmented bind:value={kind} options={[{ value: "", label: "Todos os tipos" }, { value: "pr", label: "PRs" }, { value: "deploy", label: "Deploys e builds" }, { value: "git", label: "Git" }]} />
    <span class="muted small">últimos {store.s?.activity.length || 0} eventos</span>
  </div>
  <div class="card scroll">
    <table>
      <thead><tr><th>Quando</th><th>Quem</th><th>Ação</th><th>Item</th></tr></thead>
      <tbody>
        {#each list as a, i (a.ts + i)}
          {@const l = label(a)}
          <tr>
            <td class="small muted nowrap">{dateTime(a.ts)}</td>
            <td>{#if a.by === "auto"}<span class="pill accent">⚡ piloto</span>{:else}<span class="pill neutral">você</span>{/if}{#if a.detail}<div class="tiny muted">{a.detail}</div>{/if}</td>
            <td><span class="pill {l[1]}">{l[0]}</span></td>
            <td>
              <div class="row" style="gap:6px"><ProviderIcon provider={a.kind === "git" ? null : a.provider} size={12} />
                {#if a.url}<a href={a.url} target="_blank" rel="noopener" class="ell">{a.prId ? `#${a.prId} ` : ""}{a.pipeline ? `${a.pipeline}${a.stage ? " → " + a.stage : ""}` : a.title}</a><ExternalLink size={11} class="muted" />
                {:else}<span class="ell">{a.title}</span>{/if}</div>
              <div class="tiny muted">{a.org}{#if a.creatorName} · {a.creatorName} → {a.target}{/if}{#if a.branch} · {a.branch}{/if}</div>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
    {#if !list.length}<Empty title="Nada por aqui ainda" />{/if}
  </div>
</Page>

<style>
  .toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex: none; flex-wrap: wrap; }
  .scroll { flex: 1; min-height: 0; overflow: auto; overscroll-behavior: contain; }
  table { width: 100%; border-collapse: collapse; }
  th { position: sticky; top: 0; z-index: 1; text-align: left; font: 650 10.5px/1 var(--font); text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted);
    padding: 11px 14px; background: var(--surface); box-shadow: inset 0 -1px 0 var(--line); }
  td { padding: 9px 14px; border-top: 1px solid var(--line); vertical-align: middle; font-size: 13px; }
  tbody tr { transition: background var(--t-fast); }
  tbody tr:hover { background: var(--surface-2); }
</style>
