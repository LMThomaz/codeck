<script lang="ts">
  // Criar PR a partir de uma branch local — no GitHub ou no Azure DevOps, conforme o remoto do repositório.
  import { ExternalLink } from "@lucide/svelte";
  import { post } from "../../lib/api";
  import { store } from "../../lib/store.svelte";
  import type { LocalRepo, Refs } from "../../lib/types";
  import { ui } from "../../lib/ui.svelte";
  import Drawer from "../Drawer.svelte";
  import ProviderIcon from "../ProviderIcon.svelte";
  import Switch from "../Switch.svelte";

  let { repo, refs, source, onclose, ondone }: { repo: LocalRepo; refs: Refs; source: string; onclose: () => void; ondone: () => void } = $props();
  const b = $derived(refs.local.find(x => x.name === source));
  // svelte-ignore state_referenced_locally
  let target = $state(refs.default && refs.default !== source ? refs.default : refs.local.find(x => x.name !== source)?.name || "");
  // svelte-ignore state_referenced_locally
  let title = $state(b?.subject || "");
  let description = $state("");
  let draft = $state(false);
  let pushFirst = $state(true);
  let busy = $state(false);
  const needsPush = $derived(!b?.upstream || (b?.ahead || 0) > 0);
  const targets = $derived([...new Set([refs.default, ...refs.remote.map(r => r.name.split("/").slice(1).join("/")), ...refs.local.map(l => l.name)].filter(t => t && t !== source))] as string[]);
  const conventional = $derived(source.startsWith("feature/") ? "Feature: " : source.startsWith("fix/") ? "Fix: " : "");

  async function create() {
    busy = true;
    try {
      if (needsPush && pushFirst) {
        if (source !== refs.current) throw new Error(`Faça checkout de ${source} para enviá-la antes de abrir a PR`);
        await post("repo/push", { id: repo.id });
      }
      const r = await post<{ id: number; url: string }>("pr/create", { repoId: repo.id, source, target, title, description, draft });
      ui.toast(`PR #${r.id} criada`, "ok", { label: "Abrir", run: () => window.open(r.url, "_blank") });
      store.refreshSoon(3000);
      ondone();
      onclose();
    } catch (e) { ui.error(e); }
    busy = false;
  }
</script>

<Drawer title="Criar pull request" subtitle={`${repo.provider === "github" ? "GitHub" : repo.provider === "azure" ? "Azure DevOps" : "remoto"} · ${repo.slug || repo.name}`} {onclose} width={560}>
  <section>
    <div class="flow"><span class="br">{source}</span><span class="arrow">→</span>
      <select class="select" bind:value={target}>{#each targets as t (t)}<option value={t}>{t}</option>{/each}</select></div>
    {#if needsPush}
      <div class="warn"><Switch bind:checked={pushFirst} label={b?.upstream ? `Enviar ${b.ahead} commit(s) antes` : "Enviar a branch para o servidor antes"} hint="A PR usa o que está no servidor." /></div>
    {/if}
  </section>
  <section>
    <label class="label">Título
      <input class="input" bind:value={title} placeholder="O que esta PR faz" />
    </label>
    {#if conventional && !title.startsWith(conventional)}<button class="link" onclick={() => (title = conventional + title)}>Usar o prefixo “{conventional.trim()}”</button>{/if}
    <label class="label">Descrição<textarea class="textarea" rows="8" bind:value={description} placeholder="Contexto, como testar, o que mudou…"></textarea></label>
    <Switch bind:checked={draft} label="Abrir como rascunho" hint="Ninguém é chamado para revisar até você marcar como pronta." />
  </section>
  {#snippet footer()}
    <span class="row small muted"><ProviderIcon provider={repo.provider} size={13} /> {repo.slug}</span>
    <span class="spacer"></span>
    <button class="btn ghost" onclick={onclose}>Cancelar</button>
    <button class="btn primary" disabled={busy || !title.trim() || !target} onclick={create}><ExternalLink size={14} /> {busy ? "Criando…" : "Criar PR"}</button>
  {/snippet}
</Drawer>

<style>
  section { padding: 16px 0; border-bottom: 1px solid var(--line); display: grid; gap: 12px; }
  .flow { display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); gap: 10px; align-items: center; }
  .br { font: 600 12.5px var(--mono); padding: 7px 10px; border-radius: 8px; background: var(--accent-soft); color: var(--accent); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .arrow { color: var(--muted); }
  .warn { padding: 10px 12px; border-radius: 10px; background: var(--warn-soft); }
  .link { justify-self: start; border: 0; background: none; color: var(--accent); font: 12.5px var(--font); cursor: pointer; padding: 0; margin-top: -6px; }
</style>
