<script lang="ts">
  import { GitBranch, KeyRound, Lock, Rocket } from "@lucide/svelte";
  import { decideDeploy, isProdStage, RES_TYPE } from "../../lib/actions";
  import { ago } from "../../lib/format";
  import type { Deploy } from "../../lib/types";
  import ProviderIcon from "../ProviderIcon.svelte";

  let { d, selected = false, onselect }: { d: Deploy; selected?: boolean; onselect: () => void } = $props();
  const prod = $derived(isProdStage(d));
</script>

<div class="list-row dep" class:sel={selected} class:prod data-row={d.key} onclick={onselect} role="button" tabindex="-1" onkeydown={(e) => e.key === "Enter" && onselect()}>
  <span class="ic" class:perm={d.kind === "permission"}>{#if d.kind === "permission"}<KeyRound size={16} />{:else}<Rocket size={16} />{/if}</span>
  <div class="grow">
    <div class="t"><span class="kind">{d.kind === "permission" ? "Permissão" : d.provider === "github" ? "Environment" : "Release"}</span>
      <span class="title ell">{d.pipeline}</span>{#if d.stage}<span class="stage">→ {d.stage}</span>{/if}</div>
    <div class="meta">
      <span class="row" style="gap:5px"><ProviderIcon provider={d.provider} size={12} />{d.org}{#if d.repo}<span class="faint">/</span>{d.repo}{/if}</span>
      {#if d.branch}<span class="branch"><GitBranch size={11} /><b>{d.branch}</b>{#if d.version} · {d.version}{/if}</span>{/if}
      {#if d.prNumber}<span class="small">PR #{d.prNumber}</span>{/if}
      <span>esperando há {ago(d.created)}</span>
      {#each d.resources as r (r.id)}<span class="pill warn" title={RES_TYPE[r.type] || r.type}><KeyRound size={10} /> {r.name}</span>{/each}
      {#if prod}<span class="pill warn"><Lock size={10} /> produção</span>{/if}
      {#if !d.mine}<span class="pill neutral" title="Você não é aprovador deste estágio">não é com você</span>{/if}
      {#if d.ruleId}<span class="pill accent">⚡ auto{d.waiting ? ` · aguardando ${d.waiting}` : ""}</span>{/if}
    </div>
  </div>
  <div class="acts" onclick={(e) => e.stopPropagation()} role="presentation">
    <button class="btn sm good" onclick={() => decideDeploy(d, "approve")}>{d.kind === "permission" ? "Permitir" : "Aprovar"}</button>
    {#if d.kind !== "permission"}<button class="btn sm danger" onclick={() => decideDeploy(d, "reject")}>Rejeitar</button>{/if}
  </div>
</div>

<style>
  .ic { width: 32px; height: 32px; border-radius: 10px; display: grid; place-items: center; background: var(--accent-soft); color: var(--accent); }
  .ic.perm { background: var(--warn-soft); color: var(--warn); }
  .t { display: flex; align-items: baseline; gap: 7px; min-width: 0; }
  .kind { font: 700 10.5px/1 var(--font); text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); flex-shrink: 0; }
  .title { font-weight: 600; }
  .stage { font-weight: 650; flex-shrink: 0; }
  .faint { color: var(--faint); }
  .acts { display: flex; gap: 6px; }
  .prod::after { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--warn); }
</style>
