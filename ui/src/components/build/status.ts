import type { Build } from "../../lib/types";
export function buildState(b: Build): { icon: string; cls: string; label: string } {
  if (b.waiting) return { icon: "⏸", cls: "warn", label: "aguardando" };
  if (b.status === "inProgress") return { icon: "⟳", cls: "warn", label: "rodando" };
  if (b.status === "notStarted") return { icon: "⏱", cls: "neutral", label: "na fila" };
  if (b.status === "cancelling") return { icon: "⊘", cls: "neutral", label: "cancelando" };
  return ({ succeeded: { icon: "✓", cls: "good", label: "sucesso" }, failed: { icon: "✕", cls: "bad", label: "falhou" },
    partiallySucceeded: { icon: "!", cls: "warn", label: "parcial" }, canceled: { icon: "⊘", cls: "neutral", label: "cancelado" } } as any)[b.result || ""]
    || { icon: "?", cls: "neutral", label: b.result || b.status };
}
export const REASON: Record<string, string> = { individualCI: "CI", batchedCI: "CI", pullRequest: "PR", manual: "manual", schedule: "agendado",
  resourceTrigger: "gatilho", buildCompletion: "gatilho" };
