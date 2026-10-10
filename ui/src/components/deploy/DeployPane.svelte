<script lang="ts">
  import { ExternalLink, GitBranch } from "@lucide/svelte";
  import { decideDeploy, RES_TYPE } from "../../lib/actions";
  import { ago } from "../../lib/format";
  import type { Deploy } from "../../lib/types";
  import ProviderIcon from "../ProviderIcon.svelte";
  let { d }: { d: Deploy } = $props();
</script>

<div class="pane-h">
  <div class="small muted row"><ProviderIcon provider={d.provider} size={12} />{d.org} · {d.kind === "permission" ? "Permissão de pipeline" : "Aprovação de deploy"}</div>
  <h2>{d.pipeline}{#if d.stage} → {d.stage}{/if}</h2>
  <div class="meta">{#if d.branch}<span class="branch"><GitBranch size={11} /><b>{d.branch}</b>{#if d.version} · {d.version}{/if}</span>{/if}<span>esperando há {ago(d.created)}</span></div>
  <div class="acts">
    <button class="btn sm good" onclick={() => decideDeploy(d, "approve")}>{d.kind === "permission" ? "Permitir" : "Aprovar"}</button>
    <button class="btn sm danger" onclick={() => decideDeploy(d, "reject")}>{d.kind === "permission" ? "Cancelar run" : "Rejeitar"}</button>
    <a class="btn sm" href={d.url} target="_blank" rel="noopener"><ExternalLink size={13} /> Abrir</a>
    {#if d.prUrl}<a class="btn sm ghost" href={d.prUrl} target="_blank" rel="noopener">PR #{d.prNumber}</a>{/if}
  </div>
</div>
<div class="pane-b">
  {#if d.kind === "permission"}
    <h4>O que está sendo pedido</h4>
    <p class="dim">O run <b>{d.version}</b> parou no estágio <b>{d.stage}</b> porque o pipeline ainda não tem permissão para usar:</p>
    {#each d.resources as r (r.id)}<div class="kv"><span>{RES_TYPE[r.type] || r.type}</span><span class="mono">{r.name}</span></div>{/each}
    <p class="small muted">“Permitir” libera esse pipeline nesses recursos (como o botão Permit do Azure) e o run continua sozinho.</p>
  {:else}
    <h4>Aprovação</h4>
    {#if d.releaseName}<div class="kv"><span>Release</span><span>{d.releaseName}</span></div>{/if}
    <div class="kv"><span>Estágio</span><span>{d.stage || "—"}</span></div>
    <div class="kv"><span>Aprovador</span><span>{d.approver || "—"}{d.mine ? " (você)" : ""}</span></div>
    {#if d.otherApprovers?.length}<div class="kv"><span>Também podem aprovar</span><span>{d.otherApprovers.join(", ")}</span></div>{/if}
  {/if}
  <h4>Origem</h4>
  <div class="kv"><span>Branch</span><span class="mono">{d.branch || "—"}</span></div>
  <div class="kv"><span>Build</span><span>{d.version || "—"}</span></div>
  <div class="kv"><span>Commit</span><span class="small">{d.message || "—"}</span></div>
  <div class="kv"><span>Disparado por</span><span>{d.requestedFor || "—"}</span></div>
</div>

<style>
  .pane-h { padding: 16px 18px 14px; border-bottom: 1px solid var(--line); }
  h2 { margin: 6px 0 8px; font-size: 16.5px; letter-spacing: -0.015em; }
  .acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
  .pane-b { padding: 4px 18px 18px; }
  h4 { margin: 18px 0 8px; font: 650 10.5px/1 var(--font); text-transform: uppercase; letter-spacing: 0.07em; color: var(--muted); }
  p { margin: 0 0 8px; font-size: 13px; }
</style>
