<script lang="ts" module>
  // Um editor Monaco por tela; cada arquivo aberto é um "model" (com o próprio desfazer e posição do cursor).
  // O agente edita os mesmos arquivos no disco: se o arquivo não tem alteração sua, ele é recarregado sozinho;
  // se tem, o salvar avisa que o disco mudou (nunca sobrescreve em silêncio).
  import type * as Monaco from "monaco-editor";
  type Doc = { model: Monaco.editor.ITextModel; mtime: number; saved: number; view: Monaco.editor.ICodeEditorViewState | null };
  export const docs = new Map<string, Doc>();
  export const dirty = $state<Record<string, boolean>>({});
  export const keyOf = (repoId: string, taskId: string | null | undefined, path: string) => `${repoId}:${taskId || ""}:${path}`;
  export function forget(key: string) { docs.get(key)?.model.dispose(); docs.delete(key); delete dirty[key]; }
</script>

<script lang="ts">
  import { get, post } from "../../lib/api";
  import { loadMonaco, monacoTheme } from "../../lib/monaco";
  import { ui } from "../../lib/ui.svelte";

  let { repoId, taskId = null, path, line = 0 }: { repoId: string; taskId?: string | null; path: string; line?: number } = $props();
  let host: HTMLDivElement | undefined = $state();
  let editor: Monaco.editor.IStandaloneCodeEditor | null = null;
  let monaco: typeof Monaco | null = null;
  let note = $state<string | null>(null);
  let loading = $state(true);
  const key = $derived(keyOf(repoId, taskId, path));

  async function openDoc(k: string, rel: string): Promise<Doc | null> {
    if (docs.has(k)) return docs.get(k)!;
    const f = await get<any>("ws/file", { repoId, taskId, path: rel });
    if (f.binary || f.tooLarge) { note = f.binary ? "Arquivo binário — não dá para editar aqui." : `Arquivo grande demais (${Math.round(f.size / 1e6)} MB).`; return null; }
    const uri = monaco!.Uri.parse(`file:///${encodeURIComponent(repoId + "-" + (taskId || "main"))}/${rel}`);
    const model = monaco!.editor.getModel(uri) || monaco!.editor.createModel(f.text, undefined, uri);
    if (f.crlf) model.setEOL(monaco!.editor.EndOfLineSequence.CRLF);
    const d: Doc = { model, mtime: f.mtime, saved: model.getAlternativeVersionId(), view: null };
    model.onDidChangeContent(() => { dirty[k] = model.getAlternativeVersionId() !== d.saved; });
    docs.set(k, d);
    return d;
  }

  async function save() {
    const k = key, d = docs.get(k);
    if (!d) return;
    try {
      const r = await post<{ mtime: number }>("ws/file", { repoId, taskId, path, text: d.model.getValue(), mtime: d.mtime });
      d.mtime = r.mtime;
      d.saved = d.model.getAlternativeVersionId();
      dirty[k] = false;
      ui.toast(`${path.split("/").pop()} salvo`);
    } catch (e: any) {
      if (/mudou no disco/.test(e.message || "") && await ui.ask({ title: "O arquivo mudou no disco", message: "Alguém (provavelmente o agente) editou este arquivo depois que você abriu. Sobrescrever com a sua versão?", confirm: "Sobrescrever", danger: true })) {
        d.mtime = 0;
        const r = await post<{ mtime: number }>("ws/file", { repoId, taskId, path, text: d.model.getValue() });
        d.mtime = r.mtime; d.saved = d.model.getAlternativeVersionId(); dirty[k] = false;
      } else ui.error(e);
    }
  }

  // o arquivo aberto e sem alteração sua acompanha o disco (o agente editando aparece ao vivo)
  async function syncFromDisk() {
    const k = key, d = docs.get(k);
    if (!d || dirty[k] || document.hidden) return;
    try {
      const f = await get<any>("ws/file", { repoId, taskId, path });
      if (f.text !== undefined && f.mtime !== d.mtime && f.text !== d.model.getValue()) {
        const view = editor?.saveViewState();
        d.model.pushEditOperations([], [{ range: d.model.getFullModelRange(), text: f.text }], () => null);
        d.saved = d.model.getAlternativeVersionId();
        dirty[k] = false;
        if (view) editor?.restoreViewState(view);
      }
      d.mtime = f.mtime ?? d.mtime;
    } catch { /* arquivo apagado ou fora do ar: deixa como está */ }
  }

  $effect(() => {
    if (!host) return;
    let disposed = false;
    loadMonaco().then(m => {
      if (disposed || !host) return;
      monaco = m;
      editor = m.editor.create(host, { automaticLayout: true, theme: monacoTheme(), fontFamily: '"JetBrains Mono Variable", ui-monospace, Menlo, monospace',
        fontSize: 13, lineHeight: 20, minimap: { enabled: true, renderCharacters: false }, smoothScrolling: true, cursorSmoothCaretAnimation: "on",
        bracketPairColorization: { enabled: true }, renderWhitespace: "selection", scrollBeyondLastLine: false, stickyScroll: { enabled: true },
        padding: { top: 8 }, fixedOverflowWidgets: true });
      editor.addCommand(m.KeyMod.CtrlCmd | m.KeyCode.KeyS, () => save());
      loading = false;
    });
    const obs = new MutationObserver(() => monaco?.editor.setTheme(monacoTheme()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const t = setInterval(syncFromDisk, 3000);
    return () => { disposed = true; clearInterval(t); obs.disconnect(); editor?.dispose(); editor = null; };
  });

  let shownKey = "";
  $effect(() => {
    const k = key, rel = path, ln = line;
    if (loading || !editor) return;
    note = null;
    const prev = docs.get(shownKey);
    if (prev && shownKey !== k) prev.view = editor.saveViewState();
    openDoc(k, rel).then(d => {
      if (!d || !editor || key !== k) return;
      editor.setModel(d.model);
      if (d.view) editor.restoreViewState(d.view);
      if (ln) { editor.revealLineInCenter(ln); editor.setPosition({ lineNumber: ln, column: 1 }); }
      shownKey = k;
      editor.focus();
    }).catch(e => (note = e.message));
  });
</script>

<div class="ed">
  {#if note}<div class="note">{note}</div>{/if}
  <div class="host" class:hidden={!!note} bind:this={host}></div>
  {#if loading}<div class="loading"><span class="shim"></span><span class="shim"></span><span class="shim"></span></div>{/if}
</div>

<style>
  .ed { position: relative; width: 100%; height: 100%; min-height: 0; background: var(--surface); }
  .host { position: absolute; inset: 0; }
  .host.hidden { visibility: hidden; }
  .note { position: absolute; inset: 0; display: grid; place-items: center; color: var(--muted); font-size: 13px; }
  .loading { position: absolute; inset: 16px; display: grid; gap: 10px; align-content: start; }
  .loading .shim { height: 12px; }
  .loading .shim:nth-child(2) { width: 70%; }
  .loading .shim:nth-child(3) { width: 45%; }
</style>
