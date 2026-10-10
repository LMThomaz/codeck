export const hoursSince = (iso?: string | null) => (iso ? (Date.now() - new Date(iso).getTime()) / 36e5 : null);

export function ago(iso?: string | null): string {
  const h = hoursSince(iso);
  if (h === null) return "—";
  if (h < 1 / 60) return "agora";
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min`;
  if (h < 48) return `${Math.round(h)} h`;
  if (h < 24 * 60) return `${Math.round(h / 24)} d`;
  return `${Math.round(h / 24 / 30)} meses`;
}

export function fmtH(h?: number | null): string {
  if (h === null || h === undefined) return "—";
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min`;
  if (h < 48) return `${Math.round(h)} h`;
  return `${(h / 24).toFixed(1).replace(".", ",")} d`;
}

export function fmtMs(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
  return `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`;
}

export const fmtDur = (a?: string | null, b?: string | null) => (a ? fmtMs((b ? new Date(b).getTime() : Date.now()) - new Date(a).getTime()) : "—");

export const dateTime = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
export const shortDate = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" }) : "—";
export const time = (iso?: string | null) => (iso ? new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "—");

export const initials = (n?: string) =>
  (n || "?").split(/[\s.@_-]+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join("");

const hash = (s: string) => [...(s || "")].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7);
const AVATAR = ["#6f8cff", "#f0726f", "#3ccf91", "#b48cff", "#f5b84f", "#4fc3f7", "#ff8fb1", "#7ad6c0", "#e0a36f", "#9aa9ff"];
export const colorFor = (s?: string) => AVATAR[hash((s || "").toLowerCase()) % AVATAR.length];

export const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
export const shortSha = (s?: string | null) => (s || "").slice(0, 7);
