// Ações sobre PRs, deploys e builds — usadas por linhas, painéis e atalhos.
import { post } from "./api";
import { store } from "./store.svelte";
import type { Build, Deploy, PR } from "./types";
import { ui } from "./ui.svelte";
import { VOTES } from "../components/pr/votes";

const isProtected = (t?: string) => !!t && !!store.s?.rules.protectedTargets.map(x => x.toLowerCase()).includes(t.toLowerCase());

export async function vote(p: PR, v: number) {
  if (v >= 5 && isProtected(p.target) &&
      !(await ui.ask({ title: `Aprovar PR para ${p.target}?`, message: `#${p.prId} ${p.title}\n\n${p.target} é uma branch protegida.`, confirm: "Aprovar", danger: true }))) return false;
  let comment = "";
  if (p.provider === "github" && v < 0) {
    const c = await ui.ask({ title: v === -10 ? "Pedir mudanças" : "Aguardando o autor", input: { label: "Comentário para o autor", multiline: true, required: true }, confirm: "Enviar" });
    if (c === null) return false;
    comment = c;
  }
  try {
    await post("vote", { key: p.key, vote: v, comment });
    ui.toast(`#${p.prId}: ${(VOTES[v] || ["voto removido"])[0].toLowerCase()}`);
    store.load();
    return true;
  } catch (e) { ui.error(e); return false; }
}

export async function archive(keys: string[], on = true) {
  try {
    await post("archive", { keys, archive: on });
    ui.toast(on ? `${keys.length} arquivada(s)` : "Voltou para a fila");
    store.load();
  } catch (e) { ui.error(e); }
}

export const RES_TYPE: Record<string, string> = { variablegroup: "grupo de variáveis", endpoint: "service connection", queue: "agent pool",
  securefile: "arquivo seguro", environment: "ambiente", repository: "repositório" };
export const isProdStage = (d: Deploy) => /prod/i.test(d.stage || "") || isProtected(d.branch);

export async function decideDeploy(d: Deploy, decision: "approve" | "reject") {
  if (d.kind === "permission") {
    const ok = await ui.ask(decision === "approve"
      ? { title: `Permitir que ${d.pipeline} use estes recursos?`, detail: d.resources.map(r => `${RES_TYPE[r.type] || r.type}: ${r.name}`),
          message: "Vale para todas as execuções futuras desse pipeline.", confirm: "Permitir" }
      : { title: `Cancelar a execução ${d.version} de ${d.pipeline}?`, confirm: "Cancelar execução", danger: true, cancel: "Voltar" });
    if (!ok) return false;
    return send(d, decision, "");
  }
  const comment = await ui.ask({
    title: `${decision === "approve" ? "Aprovar" : "Rejeitar"} ${d.pipeline} → ${d.stage}?`,
    message: decision === "approve" && isProdStage(d) ? "⚠ Isto sobe para produção." : undefined,
    input: { label: "Comentário (opcional)", placeholder: "ex.: validado em homologação" },
    confirm: decision === "approve" ? "Aprovar" : "Rejeitar", danger: decision === "reject" || isProdStage(d),
  });
  if (comment === null) return false;
  return send(d, decision, comment);
}

async function send(d: Deploy, decision: string, comment: string) {
  try {
    await post("deploy", { key: d.key, decision, comment });
    ui.toast(d.kind === "permission" ? (decision === "approve" ? "Permissão liberada — o run continua" : "Execução cancelada")
      : decision === "approve" ? "Deploy aprovado" : "Deploy rejeitado");
    store.load();
    return true;
  } catch (e) { ui.error(e); return false; }
}

export async function buildAction(b: Build, action: "retry" | "rerun" | "cancel") {
  const msg = { retry: `Tentar de novo o que falhou em ${b.pipeline} ${b.number}?`, rerun: `Rodar ${b.pipeline} de novo no mesmo commit (${b.branch})?`,
                cancel: `Cancelar ${b.pipeline} ${b.number}?` }[action];
  const ok = await ui.ask({ title: msg, message: isProtected(b.branch) && action !== "cancel" ? "⚠ Branch protegida — pode disparar deploy." : undefined,
    confirm: { retry: "Tentar de novo", rerun: "Rodar de novo", cancel: "Cancelar build" }[action], danger: action === "cancel" });
  if (!ok) return;
  try {
    await post("build-action", { key: b.key, action });
    ui.toast({ retry: "Reexecutando o que falhou", rerun: "Novo run na fila", cancel: "Cancelando" }[action]);
    await post("refresh");
    store.refreshSoon(4000);
  } catch (e) { ui.error(e); }
}
