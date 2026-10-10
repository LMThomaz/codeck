<script lang="ts">
  // Detalhe de um commit: mensagem, autor, arquivos alterados (+/−) e ações (cherry-pick, revert, branch aqui…).
  import { Copy, GitBranchPlus, Undo2 } from "@lucide/svelte";
  import { get } from "../../lib/api";
  import { colorFor, dateTime, initials } from "../../lib/format";
  import type { CommitDetail, FileChange } from "../../lib/types";
  import { ui } from "../../lib/ui.svelte";

  let { repoId, sha, onopen, onaction }:
    { repoId: string; sha: string; onopen: (f: FileChange) => void; onaction: (a: string, sha: string) => void } = $props();
  let c = $state<CommitDetail | null>(null);
  let error = $state<string | null>(null);
  $effect(() => {
    void sha;
    c = null; error = null;
    get<CommitDetail>("repo/commit", { id: repoId, sha }).then(r => (c = r)).catch(e => (error = e.message));
  });
  const totals = $derived(c ? c.files.reduce((t, f) => ({ add: t.add + (f.add || 0), del: t.del + (f.del || 0) }), { add: 0, del: 0 }) : null);
  const LETTER: Record<string, string> = { M: "warn", A: "good", D: "bad", R: "info", C: "info" };
</script>

<div class="panel">
  {#if error}<div class="err">{error}</div>
  {:else if !c}<div class="sk"><i class="shim" style="height:14px;width:70%"></i><i class="shim" style="height:40px"></i><i class="shim" style="height:120px"></i></div>
  {:else}
    <div class="hd">
      <div class="who"><span class="av" style="background:{colorFor(c.author)}">{initials(c.author)}</span>
        <div><b>{c.author}</b><div class="small muted">{dateTime(c.date)}{#if c.committer && c.committer !== c.author} · commit por {c.committer}{/if}</div></div></div>
      <pre class="message">{c.message}</pre>
      <div class="shas">
        <button class="sha" title="Copiar SHA" onclick={() => { navigator.clipboard.writeText(c!.sha); ui.toast("SHA copiado"); }}><Copy size={11} /> {c.sha.slice(0, 10)}</button>
        {#if c.parents.length > 1}<span class="pill neutral">merge de {c.parents.length} pais</span>{/if}
      </div>
      <div class="acts">
        <button class="btn sm" onclick={() => onaction("branch", c!.sha)}><GitBranchPlus size={13} /> Branch aqui</button>
        <button class="btn sm" onclick={() => onaction("cherry-pick", c!.sha)}>Cherry-pick</button>
        <button class="btn sm" onclick={() => onaction("revert", c!.sha)}><Undo2 size={13} /> Revert</button>
      </div>
    </div>
    <div class="files">
      <div class="sec"><span>{c.files.length} arquivo(s)</span>{#if totals}<span class="add">+{totals.add}</span><span class="del">−{totals.del}</span>{/if}</div>
      {#each c.files as f (f.path)}
        <button class="f" onclick={() => onopen(f)}>
          <span class="st {LETTER[f.status] || ''}">{f.status}</span>
          <span class="path ell" title={f.from ? `${f.from} → ${f.path}` : f.path}><b>{f.path.split("/").pop()}</b> <i>{f.path.split("/").slice(0, -1).join("/")}</i></span>
          <span class="nums">{#if f.add !== null && f.add !== undefined}<span class="add">+{f.add}</span> <span class="del">−{f.del}</span>{:else}<span class="muted">bin</span>{/if}</span>
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .panel { display: flex; flex-direction: column; height: 100%; min-height: 0; }
  .hd { padding: 14px; border-bottom: 1px solid var(--line); display: grid; gap: 10px; }
  .who { display: flex; align-items: center; gap: 10px; }
  .av { width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center; font: 700 11px var(--font); color: #fff; flex-shrink: 0; }
  .message { margin: 0; white-space: pre-wrap; font: 13px/1.5 var(--font); color: var(--text); max-height: 180px; overflow: auto; }
  .shas { display: flex; gap: 8px; align-items: center; }
  .sha { display: inline-flex; align-items: center; gap: 5px; border: 1px solid var(--line-2); background: var(--surface-2); color: var(--text-2); font: 11.5px var(--mono);
    border-radius: 6px; padding: 3px 7px; cursor: pointer; }
  .sha:hover { color: var(--text); border-color: var(--line-3); }
  .acts { display: flex; gap: 6px; flex-wrap: wrap; }
  .files { flex: 1; min-height: 0; overflow: auto; }
  .sec { position: sticky; top: 0; display: flex; gap: 8px; align-items: center; padding: 8px 14px; background: color-mix(in srgb, var(--surface) 94%, transparent);
    backdrop-filter: blur(8px); font: 650 10.5px/1 var(--font); text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }
  .sec span:first-child { flex: 1; }
  .f { display: grid; grid-template-columns: 16px minmax(0, 1fr) auto; gap: 8px; align-items: center; width: 100%; height: 30px; padding: 0 14px; border: 0; background: none;
    color: var(--text); font: 12.5px var(--font); text-align: left; cursor: pointer; transition: background var(--t-fast); }
  .f:hover { background: var(--surface-2); }
  .st { font: 700 10.5px/1 var(--mono); color: var(--muted); }
  .st.warn { color: var(--warn); } .st.good { color: var(--good); } .st.bad { color: var(--bad); } .st.info { color: var(--info); }
  .path b { font-weight: 550; }
  .path i { font-style: normal; color: var(--muted); font-size: 11.5px; }
  .nums { font: 11px var(--mono); }
  .add { color: var(--good); }
  .del { color: var(--bad); }
  .err { padding: 16px; color: var(--bad); }
  .sk { display: grid; gap: 10px; padding: 16px; }
</style>
