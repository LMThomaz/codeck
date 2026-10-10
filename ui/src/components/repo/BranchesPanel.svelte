<script lang="ts">
  // Branches locais (com ↑/↓), remotas, tags e stashes — com as ações de cada uma.
  import { ArrowDown, ArrowUp, Archive, ChevronRight, Cloud, CloudOff, GitBranch, GitMerge, GitPullRequestCreate, Pencil, Sparkles, Tag, Trash2 } from "@lucide/svelte";
  import { ago } from "../../lib/format";
  import type { Refs } from "../../lib/types";
  import Menu from "../Menu.svelte";

  let { refs, onaction, onfocus, focused = null }:
    { refs: Refs; onaction: (action: string, arg: any) => void; onfocus: (name: string | null) => void; focused?: string | null } = $props();
  let open = $state<Record<string, boolean>>({ local: true, remote: false, tags: false, stashes: true });
  let q = $state("");
  const f = (n: string) => !q || n.toLowerCase().includes(q.toLowerCase());
</script>

<div class="panel">
  <div class="filter"><input class="input" bind:value={q} placeholder="Filtrar branches…" /></div>
  <div class="scroll">
    <div class="sech">
      <button class="sec" onclick={() => (open.local = !open.local)}><ChevronRight size={13} class={open.local ? "rot" : ""} /> Locais <em>{refs.local.length}</em></button>
      {#if refs.local.some(b => b.gone && b.name !== refs.current)}
        <button class="tidy" title="Apagar as branches locais cuja remota já foi apagada" onclick={() => onaction("tidy", refs.local.filter(b => b.gone && b.name !== refs.current).map(b => b.name))}>
          <Sparkles size={12} /> Limpar {refs.local.filter(b => b.gone && b.name !== refs.current).length}</button>
      {/if}
    </div>
    {#if open.local}
      {#each refs.local.filter(b => f(b.name)) as b (b.name)}
        <div class="b" class:cur={b.name === refs.current} class:foc={focused === b.name} role="button" tabindex="-1"
          onclick={() => onfocus(focused === b.name ? null : b.name)} ondblclick={() => b.name !== refs.current && onaction("checkout", b.name)} onkeydown={() => {}}>
          <GitBranch size={13} />
          <span class="name ell" title={b.name}>{b.name}</span>
          {#if b.gone}<span class="gone" title="A branch no servidor foi apagada (normalmente já mesclada)"><CloudOff size={12} /></span>{/if}
          {#if b.ahead}<span class="ab up"><ArrowUp size={10} />{b.ahead}</span>{/if}
          {#if b.behind}<span class="ab down"><ArrowDown size={10} />{b.behind}</span>{/if}
          <span onclick={(e) => e.stopPropagation()} role="presentation" class="m">
            <Menu items={[
              { label: "Fazer checkout", icon: GitBranch, onclick: () => onaction("checkout", b.name), disabled: b.name === refs.current },
              { label: `Merge em ${refs.current}`, icon: GitMerge, onclick: () => onaction("merge", b.name), disabled: b.name === refs.current || !refs.current },
              { label: "Criar PR desta branch", icon: GitPullRequestCreate, onclick: () => onaction("pr", b.name), disabled: b.name === refs.default },
              { separator: true },
              { label: "Renomear", icon: Pencil, onclick: () => onaction("rename", b.name) },
              { label: "Apagar branch local", icon: Trash2, danger: true, onclick: () => onaction("delete", b.name), disabled: b.name === refs.current },
            ]} />
          </span>
        </div>
      {/each}
    {/if}

    <button class="sec" onclick={() => (open.remote = !open.remote)}><ChevronRight size={13} class={open.remote ? "rot" : ""} /> Remotas <em>{refs.remote.length}</em></button>
    {#if open.remote}
      {#each refs.remote.filter(b => f(b.name)) as b (b.name)}
        <div class="b" class:foc={focused === b.name} role="button" tabindex="-1" onclick={() => onfocus(focused === b.name ? null : b.name)} onkeydown={() => {}}
          ondblclick={() => onaction("track", b.name)} title={`${b.subject} — ${b.author}, ${ago(b.date)}`}>
          <Cloud size={13} /><span class="name ell">{b.name}</span>
          <span onclick={(e) => e.stopPropagation()} role="presentation" class="m">
            <Menu items={[
              { label: "Checkout (cria a local)", icon: GitBranch, onclick: () => onaction("track", b.name), disabled: refs.local.some(l => l.name === b.name.split("/").slice(1).join("/")) },
              { label: `Merge em ${refs.current}`, icon: GitMerge, onclick: () => onaction("merge", b.name), disabled: !refs.current },
              { separator: true },
              { label: "Apagar no servidor", icon: Trash2, danger: true, onclick: () => onaction("delete-remote", b.name) },
            ]} />
          </span>
        </div>
      {/each}
    {/if}

    <button class="sec" onclick={() => (open.tags = !open.tags)}><ChevronRight size={13} class={open.tags ? "rot" : ""} /> Tags <em>{refs.tags.length}</em></button>
    {#if open.tags}
      {#each refs.tags.filter(t => f(t.name)).slice(0, 80) as t (t.name)}
        <div class="b" role="button" tabindex="-1" onclick={() => onfocus("tag: " + t.name)} onkeydown={() => {}}><Tag size={13} /><span class="name ell">{t.name}</span><span class="tiny muted">{ago(t.date)}</span></div>
      {/each}
    {/if}

    <button class="sec" onclick={() => (open.stashes = !open.stashes)}><ChevronRight size={13} class={open.stashes ? "rot" : ""} /> Stashes <em>{refs.stashes.length}</em></button>
    {#if open.stashes}
      {#each refs.stashes as s (s.ref)}
        <div class="b" title={s.message}><Archive size={13} /><span class="name ell">{s.message.replace(/^On [^:]+: /, "").replace(/^WIP on [^:]+: /, "")}</span>
          <span class="m"><Menu items={[
            { label: "Aplicar e remover (pop)", onclick: () => onaction("stash-pop", s.ref) },
            { label: "Aplicar e manter", onclick: () => onaction("stash-apply", s.ref) },
            { separator: true },
            { label: "Descartar stash", icon: Trash2, danger: true, onclick: () => onaction("stash-drop", s.ref) },
          ]} /></span>
        </div>
      {:else}<div class="none">Nenhum stash.</div>{/each}
    {/if}
  </div>
</div>

<style>
  .panel { display: flex; flex-direction: column; height: 100%; min-height: 0; }
  .filter { padding: 10px; border-bottom: 1px solid var(--line); }
  .filter .input { height: 28px; font-size: 12.5px; }
  .scroll { flex: 1; overflow: auto; padding: 4px 0 10px; }
  .sec { display: flex; align-items: center; gap: 6px; width: 100%; padding: 9px 12px 5px; border: 0; background: none; cursor: pointer;
    font: 650 10.5px/1 var(--font); text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }
  .sec em { font-style: normal; color: var(--text-2); }
  .sec :global(svg) { transition: transform var(--t) var(--ease); }
  .sec :global(.rot) { transform: rotate(90deg); }
  .b { display: flex; align-items: center; gap: 8px; height: 29px; padding: 0 6px 0 16px; cursor: pointer; font-size: 12.5px; color: var(--text-2);
    transition: background var(--t-fast), color var(--t-fast); }
  .b:hover { background: var(--surface-2); color: var(--text); }
  .b.cur { color: var(--text); font-weight: 650; }
  .b.cur :global(svg:first-child) { color: var(--good); }
  .b.foc { background: var(--accent-soft); color: var(--text); }
  .name { flex: 1; }
  .sech { display: flex; align-items: center; padding-right: 8px; }
  .tidy { margin-left: auto; display: inline-flex; align-items: center; gap: 4px; border: 0; background: var(--accent-soft); color: var(--accent);
    font: 600 11px/1 var(--font); padding: 4px 7px; border-radius: 6px; cursor: pointer; white-space: nowrap; }
  .gone { color: var(--faint); display: inline-grid; }
  .ab { display: inline-flex; align-items: center; gap: 2px; font: 650 10.5px/1 var(--font); }
  .ab.up { color: var(--accent); }
  .ab.down { color: var(--info); }
  .m { opacity: 0; transition: opacity var(--t-fast); }
  .b:hover .m { opacity: 1; }
  .none { padding: 4px 16px; font-size: 12px; color: var(--muted); }
</style>
