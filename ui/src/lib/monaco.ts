// Monaco (o editor do VS Code), carregado sob demanda: só baixa quando o primeiro arquivo é aberto.
import type * as Monaco from "monaco-editor";

let loading: Promise<typeof Monaco> | null = null;

export function loadMonaco(): Promise<typeof Monaco> {
  if (loading) return loading;
  loading = (async () => {
    const [monaco, editorW, jsonW, cssW, htmlW, tsW] = await Promise.all([
      import("monaco-editor"),
      import("monaco-editor/esm/vs/editor/editor.worker?worker"),
      import("monaco-editor/esm/vs/language/json/json.worker?worker"),
      import("monaco-editor/esm/vs/language/css/css.worker?worker"),
      import("monaco-editor/esm/vs/language/html/html.worker?worker"),
      import("monaco-editor/esm/vs/language/typescript/ts.worker?worker"),
    ]);
    (self as any).MonacoEnvironment = {
      getWorker(_: string, label: string) {
        if (label === "json") return new jsonW.default();
        if (["css", "scss", "less"].includes(label)) return new cssW.default();
        if (["html", "handlebars", "razor"].includes(label)) return new htmlW.default();
        if (["typescript", "javascript"].includes(label)) return new tsW.default();
        return new editorW.default();
      },
    };
    // o Monaco cancela buscas em andamento quando o arquivo troca (rejeita com "Canceled"): é esperado, não é erro
    // (idem "no diff result available": o diff foi fechado no meio do cálculo)
    window.addEventListener("unhandledrejection", e => {
      const m = e.reason?.message || "";
      if (e.reason?.name === "Canceled" || m === "Canceled" || m === "no diff result available") e.preventDefault();
    });
    // o TypeScript embutido não conhece o projeto (sem node_modules): sem erros falsos de import
    monaco.languages.typescript.typescriptDefaults.setDiagnosticsOptions({ noSemanticValidation: true, noSyntaxValidation: false });
    monaco.languages.typescript.javascriptDefaults.setDiagnosticsOptions({ noSemanticValidation: true, noSyntaxValidation: false });
    if ((window as any).__CD_SELFTEST) (window as any).__cdMonaco = monaco;   // autoteste: marcações e modelos
    monaco.editor.defineTheme("commitdeck-dark", {
      base: "vs-dark", inherit: true, rules: [
        { token: "comment", foreground: "6e778c", fontStyle: "italic" }, { token: "keyword", foreground: "b07cff" },
        { token: "string", foreground: "3ccf91" }, { token: "number", foreground: "f5b84f" }, { token: "type", foreground: "4fc3f7" },
      ],
      colors: { "editor.background": "#12151c", "editor.lineHighlightBackground": "#171b24", "editorLineNumber.foreground": "#4a5163",
        "editorLineNumber.activeForeground": "#a7aec0", "editor.selectionBackground": "#6f8cff40", "editorCursor.foreground": "#8ba3ff",
        "editorIndentGuide.background1": "#1d222d", "editorWidget.background": "#1a1f29", "editorGutter.background": "#12151c",
        "minimap.background": "#12151c", "scrollbarSlider.background": "#ffffff14" },
    });
    monaco.editor.defineTheme("commitdeck-light", { base: "vs", inherit: true, rules: [], colors: { "editor.background": "#ffffff" } });
    return monaco;
  })();
  return loading;
}

export const monacoTheme = () => (document.documentElement.dataset.theme === "light" ? "commitdeck-light" : "commitdeck-dark");
