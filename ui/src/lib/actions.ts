// Ações sobre PRs, deploys e builds — usadas por linhas, painéis e atalhos.
import { post } from "./api";
import { store } from "./store.svelte";
import type { Build, Deploy, PR } from "./types";
import { ui } from "./ui.svelte";
import { VOTES } from "../components/pr/votes";

const isProtected = (t?: string) => !!t && !!store.s?.rules.protectedTargets.map(x => x.toLowerCase()).includes(t.toLowerCase());

const wait = (ms: number) => new Promise(r => setTimeout(r, ms));
const VERB: Record<number, string> = { 10: "Aprovando", 5: "Aprovando com sugestões", 0: "Removendo o voto de", [-5]: "Marcando aguardando autor em", [-10]: "Recusando" };

/**
 * Vota numa PR com retorno visual em cada fase: a linha e o botão mostram "enviando", depois um ✓, e só então a PR sai
 * da fila (`leaves`: a lista onde ela está deixa de mostrá-la depois do voto). O estado local é atualizado na hora,
 * sem esperar a próxima leitura.
 */
export async function vote(p: PR, v: number, leaves = false) {
  if (store.votes[p.key]?.phase === "sending") return false;
  if (v >= 5 && isProtected(p.target) &&
      !(await ui.ask({ title: `Aprovar PR para ${p.target}?`, message: `#${p.prId} ${p.title}\n\n${p.target} é uma branch protegida.`, confirm: "Aprovar", danger: true }))) return false;
  let comment = "";
  if (p.provider === "github" && v < 0) {
    const c = await ui.ask({ title: v === -10 ? "Pedir mudanças" : "Aguardando o autor", input: { label: "Comentário para o autor", multiline: true, required: true }, confirm: "Enviar" });
    if (c === null) return false;
    comment = c;
  }
  const label = (VOTES[v] || ["voto removido"])[0].toLowerCase();
  const prog = ui.progress(`${VERB[v] ?? "Votando em"} #${p.prId}…`);
  store.votes[p.key] = { vote: v, phase: "sending" };
  try {
    await post("vote", { key: p.key, vote: v, comment });
  } catch (e) {
    store.votes[p.key] = { vote: v, phase: "error" };
    prog.fail(e);
    await wait(600);
    delete store.votes[p.key];
    return false;
  }
  prog.done(`#${p.prId}: ${label}`);
  store.votes[p.key] = { vote: v, phase: "done" };
  await wait(leaves ? 650 : 900);
  if (leaves) {
    store.votes[p.key] = { vote: v, phase: "leaving" };
    await wait(340);
  }
  for (const list of [store.s?.prs, store.s?.myPrs]) {
    const it = list?.find(x => x.key === p.key);
    if (it) it.myVote = v;
  }
  delete store.votes[p.key];
  store.load();
  return true;
}

export async function archive(keys: string[], on = true) {
  const prog = ui.progress(on ? "Arquivando…" : "Restaurando…");
  try {
    await post("archive", { keys, archive: on });
    prog.done(on ? `${keys.length} arquivada(s)` : "Voltou para a fila");
    store.load();
  } catch (e) { prog.fail(e); }
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
  const prog = ui.progress(d.kind === "permission" ? (decision === "approve" ? "Liberando a permissão…" : "Cancelando a execução…")
    : decision === "approve" ? `Aprovando ${d.stage}…` : `Rejeitando ${d.stage}…`);
  try {
    await post("deploy", { key: d.key, decision, comment });
    prog.done(d.kind === "permission" ? (decision === "approve" ? "Permissão liberada — o run continua" : "Execução cancelada")
      : decision === "approve" ? "Deploy aprovado" : "Deploy rejeitado");
    store.load();
    return true;
  } catch (e) { prog.fail(e); return false; }
}

export async function buildAction(b: Build, action: "retry" | "rerun" | "cancel") {
  const msg = { retry: `Tentar de novo o que falhou em ${b.pipeline} ${b.number}?`, rerun: `Rodar ${b.pipeline} de novo no mesmo commit (${b.branch})?`,
                cancel: `Cancelar ${b.pipeline} ${b.number}?` }[action];
  const ok = await ui.ask({ title: msg, message: isProtected(b.branch) && action !== "cancel" ? "⚠ Branch protegida — pode disparar deploy." : undefined,
    confirm: { retry: "Tentar de novo", rerun: "Rodar de novo", cancel: "Cancelar build" }[action], danger: action === "cancel" });
  if (!ok) return;
  const prog = ui.progress({ retry: "Pedindo nova tentativa…", rerun: "Enfileirando um novo run…", cancel: "Cancelando…" }[action]);
  try {
    await post("build-action", { key: b.key, action });
    prog.done({ retry: "Reexecutando o que falhou", rerun: "Novo run na fila", cancel: "Build cancelado" }[action]);
    store.refresh();
  } catch (e) { prog.fail(e); }
}
