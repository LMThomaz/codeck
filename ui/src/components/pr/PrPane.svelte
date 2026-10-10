<script lang="ts">
  // Painel de detalhes da PR: ações de voto, descrição, revisores e checks/policies.
  import { AlertTriangle, Archive, ExternalLink, GitBranch } from "@lucide/svelte";
  import { archive, vote } from "../../lib/actions";
  import { ago, dateTime } from "../../lib/format";
  import type { PR } from "../../lib/types";
  import Avatar from "../Avatar.svelte";
  import ProviderIcon from "../ProviderIcon.svelte";
  import { POLICY, VOTES } from "./votes";

  let { pr, mine = false }: { pr: PR; mine?: boolean } = $props();

  async function doArchive() { await archive([pr.key], !pr.archived); }
  const btn = (v: number) => pr.myVote !== v;
</script>

<div class="pane-h">
  <div class="small muted row"><ProviderIcon provider={pr.provider} size={12} />{pr.org} / {pr.repo} · #{pr.prId}</div>
  <h2>{pr.title}</h2>
  <div class="meta">
    <span class="branch"><GitBranch size={11} />{pr.source} → <b>{pr.target}</b></span>
    <span class="row" style="gap:6px"><Avatar name={pr.creatorName} src={pr.creatorAvatar} size={16} />{pr.creatorName} · {ago(pr.created)}</span>
  </div>
  <div class="acts">
    {#if !mine}
      {#if btn(10)}<button class="btn sm good" onclick={() => vote(pr, 10)}>Aprovar</button>{/if}
      {#if btn(5)}<button class="btn sm" onclick={() => vote(pr, 5)}>Aprovar c/ sugestões</button>{/if}
      {#if btn(-5)}<button class="btn sm" onclick={() => vote(pr, -5)}>Aguardando autor</button>{/if}
      {#if btn(-10)}<button class="btn sm danger" onclick={() => vote(pr, -10)}>{pr.provider === "github" ? "Pedir mudanças" : "Recusar"}</button>{/if}
      {#if btn(0) && pr.provider === "azure"}<button class="btn sm ghost" onclick={() => vote(pr, 0)}>Remover voto</button>{/if}
    {/if}
    <a class="btn sm" href={pr.url} target="_blank" rel="noopener"><ExternalLink size={13} /> Abrir</a>
    {#if !mine}<button class="btn sm ghost" onclick={doArchive}><Archive size={13} /> {pr.archived ? "Restaurar" : "Arquivar"}</button>{/if}
  </div>
</div>
<div class="pane-b">
  {#if pr.mergeStatus === "conflicts"}
    <div class="warnbox"><AlertTriangle size={15} /><span><b>{pr.source}</b> tem conflito com <b>{pr.target}</b>. O merge fica bloqueado até o autor atualizar a branch — aprovar não resolve.</span></div>
  {/if}
  <h4>Descrição</h4>
  <div class="desc">{#if pr.description}{pr.description}{:else}<span class="muted">Sem descrição.</span>{/if}</div>
  <div class="small muted" style="margin-top:8px">Criada em {dateTime(pr.created)}{#if pr.autoComplete} · auto-complete ligado{/if}</div>

  <h4>Revisores</h4>
  {#each pr.reviewers as r (r.id || r.name)}
    <div class="kv"><span class="row" style="gap:7px"><Avatar name={r.name} size={18} />{r.name}{#if r.required}<span class="pill neutral">obrigatório</span>{/if}</span>
      {#if VOTES[r.vote]}<span class="pill {VOTES[r.vote][1]}">{VOTES[r.vote][0]}</span>{:else}<span class="small muted">pendente</span>{/if}</div>
  {:else}<div class="small muted">Sem revisores.</div>{/each}

  <h4>{pr.provider === "github" ? "Checks" : "Policies"}</h4>
  {#each pr.policies as p (p.name + p.status)}
    {@const st = POLICY[p.status] || ["?", "neutral"]}
    <div class="kv"><span>{p.name}{#if !p.blocking && pr.provider === "azure"} <span class="small muted">(opcional)</span>{/if}</span><span class="pill {st[1]}">{st[0]} {p.status}</span></div>
  {:else}<div class="small muted">Nenhum check.</div>{/each}
</div>

<style>
  .pane-h { padding: 16px 18px 14px; border-bottom: 1px solid var(--line); }
  h2 { margin: 6px 0 8px; font-size: 16.5px; line-height: 1.35; letter-spacing: -0.015em; }
  .acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
  .pane-b { padding: 6px 18px 18px; }
  h4 { margin: 18px 0 8px; font: 650 10.5px/1 var(--font); text-transform: uppercase; letter-spacing: 0.07em; color: var(--muted); }
  .desc { white-space: pre-wrap; font-size: 13px; color: var(--text-2); max-height: 280px; overflow: auto; background: var(--bg-2); border: 1px solid var(--line);
    border-radius: 10px; padding: 10px 12px; }
  .warnbox { display: flex; gap: 9px; align-items: flex-start; margin-top: 14px; padding: 10px 12px; border-radius: 10px; background: var(--bad-soft);
    color: var(--bad); font-size: 13px; }
  .warnbox :global(svg) { flex-shrink: 0; margin-top: 2px; }
</style>
