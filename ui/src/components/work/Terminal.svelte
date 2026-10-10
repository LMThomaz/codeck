<script lang="ts" module>
  // Instâncias vivas por terminal: trocar de aba/projeto NÃO recria o xterm nem a conexão — só move o elemento.
  import { Terminal as XTerm } from "@xterm/xterm";
  import { FitAddon } from "@xterm/addon-fit";
  import { SearchAddon } from "@xterm/addon-search";
  import { WebLinksAddon } from "@xterm/addon-web-links";
  import "@xterm/xterm/css/xterm.css";

  type Live = { term: XTerm; fit: FitAddon; search: SearchAddon; el: HTMLDivElement; ws: WebSocket | null; exited: boolean; tries: number; dispose: () => void };
  const live = new Map<string, Live>();

  function css(name: string) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function theme() {
    const light = document.documentElement.dataset.theme === "light";
    return light
      ? { background: "#ffffff", foreground: "#1f2430", cursor: "#4f6ef7", selectionBackground: "#4f6ef733", black: "#1f2430", brightBlack: "#6b7385",
          red: "#d1384f", green: "#0f9f66", yellow: "#a86c12", blue: "#3f5fe0", magenta: "#8b4cd6", cyan: "#0a83b8", white: "#c9ced8" }
      : { background: css("--surface") || "#12151c", foreground: "#d8dce6", cursor: "#8ba3ff", selectionBackground: "#6f8cff40", black: "#1b1f29",
          brightBlack: "#5d667a", red: "#ff6b7d", green: "#3ccf91", yellow: "#f5b84f", blue: "#6f8cff", magenta: "#b07cff", cyan: "#4fc3f7",
          white: "#d8dce6", brightWhite: "#ffffff" };
  }

  function connect(id: string, l: Live) {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/term/${id}`, ["commitdeck." + (window.COMMITDECK_TOKEN || "")]);
    ws.binaryType = "arraybuffer";
    let first = true;
    ws.onmessage = (e) => {
      if (typeof e.data === "string") {
        const m = JSON.parse(e.data);
        if (m.t === "exit") { l.exited = true; l.term.write(`\r\n\x1b[90m— processo terminou${m.code != null ? ` (código ${m.code})` : ""} —\x1b[0m\r\n`); }
        return;
      }
      if (first) { l.term.reset(); first = false; }   // 1º binário = histórico inteiro: redesenha do zero
      l.term.write(new Uint8Array(e.data));
    };
    ws.onopen = () => { l.tries = 0; resize(id); };
    ws.onclose = () => {
      l.ws = null;
      if (!l.exited && live.get(id) === l && l.tries < 20) setTimeout(() => { if (live.get(id) === l) { l.tries++; l.ws = connect(id, l); } }, 600 * (l.tries + 1));
    };
    return ws;
  }

  function resize(id: string) {
    const l = live.get(id);
    if (!l || !l.el.isConnected || !l.el.offsetWidth) return;
    try { l.fit.fit(); } catch { return; }
    if (l.ws?.readyState === 1) l.ws.send(JSON.stringify({ t: "resize", c: l.term.cols, r: l.term.rows }));
  }

  export function ensure(id: string): Live {
    let l = live.get(id);
    if (l) return l;
    const el = document.createElement("div");
    el.className = "xterm-host";
    const term = new XTerm({ fontFamily: '"JetBrains Mono Variable", ui-monospace, "SF Mono", Menlo, Consolas, monospace', fontSize: 13, lineHeight: 1.25,
      cursorBlink: true, allowProposedApi: true, scrollback: 20000, macOptionIsMeta: true, theme: theme(), smoothScrollDuration: 80 });
    const fit = new FitAddon(), search = new SearchAddon();
    term.loadAddon(fit); term.loadAddon(search); term.loadAddon(new WebLinksAddon((_e, uri) => window.open(uri, "_blank")));
    term.open(el);
    const sub = term.onData(d => { const ws = live.get(id)?.ws; if (ws?.readyState === 1) ws.send(JSON.stringify({ t: "in", d })); });
    const bin = term.onBinary(d => { const ws = live.get(id)?.ws; if (ws?.readyState === 1) ws.send(new Uint8Array([...d].map(c => c.charCodeAt(0) & 255))); });
    // ⌘K limpa a tela (como no Terminal do macOS); ⌘F é tratado pela tela
    term.attachCustomKeyEventHandler(e => {
      if (e.type === "keydown" && (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k" && !e.shiftKey) { term.clear(); return false; }
      return true;
    });
    l = { term, fit, search, el, ws: null, exited: false, tries: 0, dispose: () => { sub.dispose(); bin.dispose(); } };
    live.set(id, l);
    l.ws = connect(id, l);
    return l;
  }

  export function drop(id: string) {
    const l = live.get(id);
    if (!l) return;
    live.delete(id);
    l.ws?.close();
    l.dispose();
    l.term.dispose();
    l.el.remove();
  }

  /** Escreve no terminal como se fosse digitado (ex.: mandar um prompt para o agente). */
  export function typeInto(id: string, text: string) {
    const ws = live.get(id)?.ws;
    if (ws?.readyState === 1) ws.send(JSON.stringify({ t: "in", d: text }));
  }

  // autoteste do desktop: lê o que o terminal RECEBEU (buffer), independente de a janela estar sendo desenhada
  if ((window as any).__CD_SELFTEST) (window as any).__cdTermText = () => [...live.values()].map(l => {
    const b = l.term.buffer.active, out: string[] = [];
    for (let i = 0; i < b.length; i++) out.push(b.getLine(i)?.translateToString(true) || "");
    return out.join("\n");
  }).join("\n");

  export function retheme() { for (const l of live.values()) l.term.options.theme = theme(); }
  new MutationObserver(retheme).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
</script>

<script lang="ts">
  let { id, active = true }: { id: string; active?: boolean } = $props();
  let host: HTMLDivElement | undefined = $state();

  $effect(() => {
    if (!host) return;
    const l = ensure(id);
    host.appendChild(l.el);
    // reajusta no quadro seguinte: dentro do próprio aviso o resize muda o layout de novo (o WebKit reporta "ResizeObserver loop")
    let raf = 0;
    const ro = new ResizeObserver(() => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => resize(id)); });
    ro.observe(host);
    requestAnimationFrame(() => resize(id));
    return () => { ro.disconnect(); if (l.el.parentElement === host) l.el.remove(); };
  });
  $effect(() => { if (active) requestAnimationFrame(() => { resize(id); live.get(id)?.term.focus(); }); });
</script>

<div class="term" bind:this={host}></div>

<style>
  .term { width: 100%; height: 100%; min-height: 0; padding: 8px 4px 4px 10px; background: var(--surface); overflow: hidden; }
  .term :global(.xterm-host) { width: 100%; height: 100%; }
  .term :global(.xterm) { height: 100%; }
  .term :global(.xterm-viewport) { background: transparent !important; }
  .term :global(.xterm-viewport::-webkit-scrollbar) { width: 8px; }
  .term :global(.xterm-viewport::-webkit-scrollbar-thumb) { background: var(--line-2); border-radius: 8px; }
</style>
