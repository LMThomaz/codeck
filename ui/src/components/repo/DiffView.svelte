<script lang="ts">
  // Diff unificado com números de linha dos dois lados, cores de adição/remoção e cabeçalhos de trecho.
  let { diff, binary = false, truncated = false }: { diff: string; binary?: boolean; truncated?: boolean } = $props();

  interface Line { kind: "add" | "del" | "ctx" | "hunk" | "meta"; text: string; a?: number; b?: number }
  const lines = $derived.by<Line[]>(() => {
    const out: Line[] = [];
    let a = 0, b = 0;
    for (const raw of (diff || "").split("\n")) {
      if (raw.startsWith("@@")) {
        const m = /@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)/.exec(raw);
        if (m) { a = Number(m[1]); b = Number(m[2]); }
        out.push({ kind: "hunk", text: raw });
      } else if (raw.startsWith("diff --git") || raw.startsWith("index ") || raw.startsWith("--- ") || raw.startsWith("+++ ") || raw.startsWith("new file") ||
                 raw.startsWith("deleted file") || raw.startsWith("similarity") || raw.startsWith("rename ") || raw.startsWith("old mode") || raw.startsWith("new mode")) {
        if (raw.startsWith("diff --git")) out.push({ kind: "meta", text: raw.replace(/^diff --git a\/(.*) b\/.*$/, "$1") });
      } else if (raw.startsWith("+")) out.push({ kind: "add", text: raw.slice(1), b: b++ });
      else if (raw.startsWith("-")) out.push({ kind: "del", text: raw.slice(1), a: a++ });
      else if (raw.startsWith("\\")) continue;
      else if (raw.length || out.length) out.push({ kind: "ctx", text: raw.slice(1), a: a++, b: b++ });
    }
    return out;
  });
  const stats = $derived({ add: lines.filter(l => l.kind === "add").length, del: lines.filter(l => l.kind === "del").length });
</script>

{#if binary}
  <div class="note">Arquivo binário — sem diff de texto.</div>
{:else if !diff}
  <div class="note">Sem diferenças.</div>
{:else}
  <div class="stats"><span class="add">+{stats.add}</span><span class="del">−{stats.del}</span>{#if truncated}<span class="muted">diff grande: mostrando o começo</span>{/if}</div>
  <div class="diff">
    {#each lines as l, i (i)}
      {#if l.kind === "meta"}<div class="file">{l.text}</div>
      {:else if l.kind === "hunk"}<div class="hunk">{l.text}</div>
      {:else}
        <div class="ln {l.kind}"><span class="na">{l.a ?? ""}</span><span class="nb">{l.b ?? ""}</span><span class="sg">{l.kind === "add" ? "+" : l.kind === "del" ? "−" : ""}</span><span class="code">{l.text}</span></div>
      {/if}
    {/each}
  </div>
{/if}

<style>
  .note { padding: 30px; text-align: center; color: var(--muted); }
  .stats { display: flex; gap: 10px; font: 600 12px var(--mono); padding: 0 2px 8px; }
  .add { color: var(--good); }
  .del { color: var(--bad); }
  .diff { font: 12px/1.6 var(--mono); border: 1px solid var(--line); border-radius: 10px; overflow: auto; background: var(--bg-2); }
  .file { position: sticky; top: 0; z-index: 1; padding: 8px 12px; background: var(--surface-2); border-bottom: 1px solid var(--line); font-weight: 600; color: var(--text); }
  .hunk { padding: 4px 12px; background: color-mix(in srgb, var(--accent) 9%, transparent); color: var(--accent); font-size: 11.5px; }
  .ln { display: grid; grid-template-columns: 46px 46px 18px minmax(0, 1fr); min-width: max-content; }
  .na, .nb { color: var(--faint); text-align: right; padding-right: 10px; user-select: none; font-size: 11px; }
  .sg { color: var(--muted); user-select: none; }
  .code { white-space: pre; padding-right: 16px; color: var(--text-2); }
  .add { background: color-mix(in srgb, var(--good) 10%, transparent); }
  .ln.add .code { color: var(--text); }
  .ln.add .sg { color: var(--good); }
  .ln.del { background: color-mix(in srgb, var(--bad) 10%, transparent); }
  .ln.del .code { color: var(--text); }
  .ln.del .sg { color: var(--bad); }
</style>
