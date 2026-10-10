<script lang="ts">
  // Área de trabalho: arquivos alterados (stage/unstage/descartar) e a caixa de commit.
  import { Archive, Minus, Plus, RotateCcw, Send } from "@lucide/svelte";
  import { post } from "../../lib/api";
  import type { FileChange, RepoStatus } from "../../lib/types";
  import { ui } from "../../lib/ui.svelte";

  let { repoId, status, onopen, onchanged }:
    { repoId: string; status: RepoStatus; onopen: (f: FileChange, staged: boolean) => void; onchanged: () => void } = $props();
  let summary = $state("");
  let body = $state("");
  let amend = $state(false);
  let busy = $state(false);

  const unstaged = $derived([...status.conflicts, ...status.unstaged, ...status.untracked]);
  const LETTER: Record<string, [string, string]> = { M: ["M", "warn"], A: ["A", "good"], D: ["D", "bad"], R: ["R", "info"], C: ["C", "info"], "?": ["U", "good"], U: ["!", "bad"], T: ["T", "warn"] };

  async function act(path: string, payload: Record<string, unknown>, msg?: string) {
    try { await post("repo/" + path, { id: repoId, ...payload }); if (msg) ui.toast(msg); onchanged(); } catch (e) { ui.error(e); }
  }
  async function discard(paths: string[]) {
    const ok = await ui.ask({ title: `Descartar ${paths.length === 1 ? paths[0] : paths.length + " arquivos"}?`,
      message: "As alterações voltam ao último commit. Arquivos novos vão para a Lixeira.", confirm: "Descartar", danger: true });
    if (ok) act("discard", { paths }, "Alterações descartadas");
  }
  async function commit(push = false) {
    const message = summary.trim() + (body.trim() ? "\n\n" + body.trim() : "");
    if (!message && !amend) return ui.toast("Escreva o resumo do commit", "error");
    busy = true;
    try {
      const stageAll = !status.staged.length && !amend;
      await post("repo/commit", { id: repoId, message, amend, stageAll });
      ui.toast(amend ? "Commit corrigido" : "Commit feito");
      summary = ""; body = ""; amend = false;
      if (push) { await post("repo/push", { id: repoId }); ui.toast("Enviado para o servidor"); }
      onchanged();
    } catch (e) { ui.error(e); }
    busy = false;
  }
  async function stash() {
    const m = await ui.ask({ title: "Guardar alterações (stash)", input: { label: "Descrição (opcional)", placeholder: "ex.: experimento do relatório" }, confirm: "Guardar" });
    if (m !== null) act("stash", { action: "push", message: m || undefined }, "Alterações guardadas no stash");
  }
</script>

<div class="panel">
  <div class="hd"><b>Alterações</b><span class="muted small">{unstaged.length + status.staged.length} arquivo(s)</span><span class="spacer"></span>
    <button class="btn sm ghost" title="Guardar no stash" onclick={stash}><Archive size={14} /></button></div>

  <div class="files">
    <div class="sec"><span>Não preparados <em>{unstaged.length}</em></span>
      {#if unstaged.length}<button class="btn sm ghost" onclick={() => act("stage-all", {})}>Preparar tudo</button>{/if}</div>
    {#each unstaged as f (f.path + f.status)}
      {@const l = LETTER[f.status] || [f.status, "neutral"]}
      <div class="f" role="button" tabindex="-1" onclick={() => onopen(f, false)} onkeydown={(e) => e.key === "Enter" && onopen(f, false)}>
        <span class="st {l[1]}">{l[0]}</span><span class="path ell" title={f.path}><b>{f.path.split("/").pop()}</b> <i>{f.path.split("/").slice(0, -1).join("/")}</i></span>
        <span class="fa" onclick={(e) => e.stopPropagation()} role="presentation">
          {#if f.status !== "U"}<button class="btn sm ghost icon" title="Descartar" onclick={() => discard([f.path])}><RotateCcw size={13} /></button>{/if}
          <button class="btn sm ghost icon" title="Preparar (stage)" onclick={() => act("stage", { paths: [f.path] })}><Plus size={14} /></button>
        </span>
      </div>
    {:else}<div class="none">Nada fora do stage.</div>{/each}

    <div class="sec"><span>Preparados <em>{status.staged.length}</em></span>
      {#if status.staged.length}<button class="btn sm ghost" onclick={() => act("unstage", { paths: status.staged.map(f => f.path) })}>Tirar tudo</button>{/if}</div>
    {#each status.staged as f (f.path)}
      {@const l = LETTER[f.status] || [f.status, "neutral"]}
      <div class="f" role="button" tabindex="-1" onclick={() => onopen(f, true)} onkeydown={(e) => e.key === "Enter" && onopen(f, true)}>
        <span class="st {l[1]}">{l[0]}</span><span class="path ell" title={f.path}><b>{f.path.split("/").pop()}</b> <i>{f.path.split("/").slice(0, -1).join("/")}</i></span>
        <span class="fa" onclick={(e) => e.stopPropagation()} role="presentation">
          <button class="btn sm ghost icon" title="Tirar do stage" onclick={() => act("unstage", { paths: [f.path] })}><Minus size={14} /></button>
        </span>
      </div>
    {:else}<div class="none">{status.dirty ? "Nada preparado — o commit leva todos os arquivos." : "Nada preparado."}</div>{/each}
  </div>

  <div class="commit">
    <input class="input" bind:value={summary} placeholder={amend ? "Novo resumo (vazio = mantém)" : "Resumo do commit"} maxlength="120" />
    <div class="cnt" class:over={summary.length > 72}>{summary.length}/72</div>
    <textarea class="textarea" rows="3" bind:value={body} placeholder="Descrição (opcional)"></textarea>
    <label class="amend"><input type="checkbox" bind:checked={amend} /> Corrigir o último commit (amend)</label>
    <div class="cb">
      <button class="btn primary" disabled={busy || (!summary.trim() && !amend) || (!status.dirty && !amend)} onclick={() => commit(false)}>
        {amend ? "Corrigir commit" : status.staged.length ? `Commit (${status.staged.length})` : "Commit de tudo"}</button>
      <button class="btn" disabled={busy || (!summary.trim() && !amend) || (!status.dirty && !amend)} onclick={() => commit(true)} title="Commit e enviar"><Send size={14} /> e push</button>
    </div>
  </div>
</div>

<style>
  .panel { display: flex; flex-direction: column; height: 100%; min-height: 0; }
  .hd { display: flex; align-items: center; gap: 8px; padding: 12px 14px; border-bottom: 1px solid var(--line); }
  .files { flex: 1; min-height: 0; overflow: auto; padding-bottom: 8px; }
  .sec { position: sticky; top: 0; z-index: 1; display: flex; align-items: center; gap: 6px; padding: 8px 14px; background: color-mix(in srgb, var(--surface) 94%, transparent);
    backdrop-filter: blur(8px); font: 650 10.5px/1 var(--font); text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }
  .sec span { flex: 1; }
  .sec em { font-style: normal; color: var(--text-2); }
  .f { display: grid; grid-template-columns: 18px minmax(0, 1fr) auto; align-items: center; gap: 8px; height: 30px; padding: 0 8px 0 14px; cursor: pointer;
    transition: background var(--t-fast); }
  .f:hover { background: var(--surface-2); }
  .fa { display: flex; opacity: 0; transition: opacity var(--t-fast); }
  .f:hover .fa { opacity: 1; }
  .st { font: 700 10.5px/1 var(--mono); text-align: center; }
  .st.warn { color: var(--warn); } .st.good { color: var(--good); } .st.bad { color: var(--bad); } .st.info { color: var(--info); } .st.neutral { color: var(--muted); }
  .path { font-size: 12.5px; }
  .path b { font-weight: 550; }
  .path i { font-style: normal; color: var(--muted); font-size: 11.5px; }
  .none { padding: 6px 14px 10px; font-size: 12px; color: var(--muted); }
  .commit { display: grid; gap: 8px; padding: 12px 14px 14px; border-top: 1px solid var(--line); background: var(--surface); position: relative; }
  .cnt { position: absolute; right: 22px; top: 21px; font-size: 10.5px; color: var(--muted); pointer-events: none; }
  .cnt.over { color: var(--warn); }
  .amend { display: flex; align-items: center; gap: 7px; font-size: 12.5px; color: var(--text-2); cursor: pointer; }
  .cb { display: grid; grid-template-columns: 1fr auto; gap: 8px; }
</style>
