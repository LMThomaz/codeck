// Avisos (toasts) e diálogos do próprio app — consistentes no macOS e no Windows.
export interface Toast { id: number; text: string; kind: "ok" | "error" | "info"; action?: { label: string; run: () => void } }
export interface Dialog {
  title: string; message?: string; detail?: string[]; confirm?: string; cancel?: string; danger?: boolean;
  input?: { label: string; value?: string; placeholder?: string; multiline?: boolean; required?: boolean };
  blocked?: string[]; resolve: (v: string | boolean | null) => void;
}

class UI {
  toasts = $state<Toast[]>([]);
  dialog = $state<Dialog | null>(null);
  palette = $state(false);
  private seq = 0;

  toast(text: string, kind: Toast["kind"] = "ok", action?: Toast["action"]) {
    const id = ++this.seq;
    this.toasts = [...this.toasts.slice(-3), { id, text, kind, action }];
    setTimeout(() => (this.toasts = this.toasts.filter(t => t.id !== id)), kind === "error" ? 6000 : 3200);
  }
  error(e: unknown) { this.toast((e as any)?.message || String(e), "error"); }

  /** Confirmação. Com `input`, devolve o texto (ou null se cancelou). Com `blocked`, só informa e não deixa confirmar. */
  ask(d: Omit<Dialog, "resolve">): Promise<any> {
    return new Promise(resolve => (this.dialog = { ...d, resolve }));
  }
  close(v: string | boolean | null) {
    this.dialog?.resolve(v);
    this.dialog = null;
  }
}

export const ui = new UI();
