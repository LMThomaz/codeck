export const VOTES: Record<number, [string, string]> = {
  10: ["Aprovada", "good"], 5: ["Aprovada c/ sugestões", "good"], [-5]: ["Aguardando autor", "warn"], [-10]: ["Recusada", "bad"],
};
export const POLICY: Record<string, [string, string]> = {
  approved: ["✓", "good"], rejected: ["✕", "bad"], broken: ["✕", "bad"], running: ["⟳", "warn"], queued: ["⟳", "warn"], notApplicable: ["–", "neutral"],
};
