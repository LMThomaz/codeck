<script lang="ts">
  import { AlertTriangle, Check, GitBranch, MessageSquare } from "@lucide/svelte";
  import { ago } from "../../lib/format";
  import type { PR } from "../../lib/types";
  import Avatar from "../Avatar.svelte";
  import ProviderIcon from "../ProviderIcon.svelte";
  import { VOTES } from "./votes";

  let { pr, selected = false, onselect, actions = undefined, showVote = true }:
    { pr: PR; selected?: boolean; onselect: () => void; actions?: import("svelte").Snippet; showVote?: boolean } = $props();
  const v = $derived(VOTES[pr.myVote]);
  const conflict = $derived(pr.mergeStatus === "conflicts");
</script>

<div class="list-row pr" class:sel={selected} class:conflict data-row={pr.key} onclick={onselect} role="button" tabindex="-1"
  onkeydown={(e) => e.key === "Enter" && onselect()}>
  <Avatar name={pr.creatorName} src={pr.creatorAvatar} size={32} />
  <div class="grow">
    <div class="t"><span class="num">#{pr.prId}</span><span class="title ell">{pr.title}</span></div>
    <div class="meta">
      <span class="row" style="gap:5px"><ProviderIcon provider={pr.provider} size={12} />{pr.org}<span class="faint">/</span>{pr.repo}</span>
      <span class="branch"><GitBranch size={11} />{pr.source} → <b>{pr.target}</b></span>
      <span>{pr.creatorName.split(" ").slice(0, 2).join(" ")} · {ago(pr.created)}</span>
      {#if conflict}<span class="pill solid-bad"><AlertTriangle size={11} /> Conflito</span>{/if}
      {#if pr.isDraft}<span class="pill neutral">rascunho</span>{/if}
      {#if pr.build === "ok"}<span class="pill good">Build ✓</span>{:else if pr.build === "failed"}<span class="pill bad">Build ✕</span>{:else if pr.build === "running" || pr.build === "pending"}<span class="pill warn">Build ⟳</span>{/if}
      {#if showVote && v}<span class="pill {v[1]}">{v[0]}</span>{/if}
      {#if pr.approvals}<span class="pill neutral" title={pr.reviewers.filter(r => r.vote >= 5).map(r => r.name).join(", ")}><Check size={11} /> {pr.approvals}</span>{/if}
      {#if pr.ruleId}<span class="pill accent" title="Regra de automação">⚡ auto{pr.waiting ? ` · aguardando ${pr.waiting}` : ""}</span>{/if}
      {#each pr.blockers || [] as b (b.code)}<span class="pill {b.code === 'waiting' ? 'warn' : 'bad'}">{b.label}</span>{/each}
    </div>
  </div>
  <div class="acts" onclick={(e) => e.stopPropagation()} role="presentation">{#if actions}{@render actions()}{/if}</div>
</div>

<style>
  .t { display: flex; align-items: baseline; gap: 7px; min-width: 0; }
  .num { color: var(--muted); font-weight: 550; font-variant-numeric: tabular-nums; flex-shrink: 0; font-size: 12.5px; }
  .title { font-weight: 600; }
  .faint { color: var(--faint); }
  .acts { display: flex; gap: 6px; align-items: center; }
  .conflict { background: color-mix(in srgb, var(--bad-soft) 55%, transparent); }
  .conflict::after { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--bad); }
</style>
