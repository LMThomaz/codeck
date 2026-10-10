// Ponte com o app nativo (Swift no macOS, C# no Windows): instalar atualização e escolher pasta.
const pending = new Map<string, (v: string | null) => void>();

window.__nativeResolve = (id, value) => {
  pending.get(id)?.(value);
  pending.delete(id);
};

export function send(msg: Record<string, unknown>) {
  if (window.webkit?.messageHandlers?.commitdeck) window.webkit.messageHandlers.commitdeck.postMessage(msg);
  else if (window.chrome?.webview) window.chrome.webview.postMessage(msg);
  else return false;
  return true;
}

export const isNative = () => !!(window.webkit?.messageHandlers?.commitdeck || window.chrome?.webview);
export const platform = () => window.COMMITDECK_PLATFORM || (navigator.userAgent.includes("Windows") ? "windows" : "macos");

/** Abre o seletor de pasta do sistema. Sem app nativo (dev no navegador), pede o caminho num prompt. */
export function pickFolder(title = "Escolha uma pasta"): Promise<string | null> {
  if (!isNative()) return Promise.resolve(window.prompt(`${title} — caminho completo:`) || null);
  const id = Math.random().toString(36).slice(2);
  return new Promise(resolve => {
    pending.set(id, resolve);
    send({ type: "pickFolder", id, title });
  });
}

export const fileManagerName = () => (platform() === "windows" ? "Explorer" : "Finder");
