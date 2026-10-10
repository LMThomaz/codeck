// Área de trabalho (v3): projetos abertos em abas, tarefas em worktree, terminais/agentes e contas de IA.
// O estado vem de /api/ws (relido a cada 2,5 s enquanto a tela está aberta — o status dos agentes muda rápido).
import { get, post } from "./api";
import { repos } from "./repos.svelte";
import { go } from "./router.svelte";
import { ui } from "./ui.svelte";

export type Provider = "claude" | "codex" | "cursor" | "gemini" | "opencode";
export interface AiAccount {
  id: string; provider: Provider; dir: string; name: string; email?: string | null; color?: string | null; label: string;
  installed: boolean; telemetry: "hooks" | "log" | null;
  usage?: { rateLimits: { window: string; used: number | null; resetsAt: string | null }[]; updated: string; source: string; plan?: string } | null;
}
export interface TermInfo {
  id: string; title: string; kind: "shell" | "agent" | "setup"; cwd: string; alive: boolean; exit: number | null; created: number; lastOutput: number;
  meta: { project?: string; task?: string; account?: string; provider?: Provider; sid?: string };
}
export interface Session {
  account: string; provider: Provider; status: "starting" | "idle" | "working" | "done" | "needs-you" | "compacting"; started: number;
  model: string | null; cost: number | null; context: { used: number | null; size: number | null; tokens: number | null } | null;
  events: { at: string; event: string; message?: string }[]; title?: string; statusAt?: number;
}
export interface Resumable { sid: string; account: string; provider: Provider; title: string; cliSession: string; updated: string }
export interface Task {
  id: string; title: string; slug: string; branch: string; base: string; path: string; repoId: string; createdAt: string;
  status: string; prompt: string; exists: boolean; terms: TermInfo[]; workItem?: any; pr?: any; copied: string[]; group?: string | null; resumable?: Resumable[];
}
export interface Project {
  id: string; name: string; path: string; provider?: string | null; slug?: string | null; webUrl?: string | null;
  settings: { copy: string[]; setup: string; worktreeRoot: string; shell?: string; addDirs?: string[] }; tasks: Task[]; terms: TermInfo[]; resumable?: Resumable[];
}

class Work {
  projects = $state<Project[]>([]);
  active = $state<string | null>(null);
  sessions = $state<Record<string, Session>>({});
  ai = $state<AiAccount[]>([]);
  providers = $state<Record<string, { label: string; installed: boolean }>>({});
  defaults = $state<Record<string, string>>({});
  loaded = $state(false);
  /** "Nova tarefa" já preenchida, pedida de outra tela (PR, build, issue): a tela de trabalho abre o formulário */
  pendingTask = $state<{ projectId: string; preset: any } | null>(null);
  /** abrir um projeto já numa aba (ex.: a Git), vindo de um link de repositório */
  focusRequest = $state<{ projectId: string; scope: string | null; tab: "git" | "review" } | null>(null);
  private timer: ReturnType<typeof setInterval> | null = null;

  get project() { return this.projects.find(p => p.id === this.active) || null; }
  account(id?: string | null) { return this.ai.find(a => a.id === id) || null; }
  session(t: TermInfo | null | undefined) { return t?.meta.sid ? this.sessions[t.meta.sid] || null : null; }

  /** Todos os terminais de agente abertos, com a sessão — para a barra lateral e o quadro. */
  get agents() {
    const out: { project: Project; task: Task | null; term: TermInfo; session: Session | null }[] = [];
    for (const p of this.projects) {
      for (const t of p.terms.filter(x => x.kind === "agent")) out.push({ project: p, task: null, term: t, session: this.session(t) });
      for (const k of p.tasks) for (const t of k.terms.filter(x => x.kind === "agent")) out.push({ project: p, task: k, term: t, session: this.session(t) });
    }
    return out;
  }
  get needsYou() { return this.agents.filter(a => a.session?.status === "needs-you").length; }

  async load() {
    try {
      const s = await get<{ projects: Project[]; active: string | null; sessions: Record<string, Session> }>("ws");
      this.projects = s.projects;
      this.active = this.projects.some(p => p.id === this.active) ? this.active : s.active;
      this.sessions = s.sessions;
      this.loaded = true;
    } catch (e) { ui.error(e); }
  }
  async loadAi() {
    const r = await get<{ accounts: AiAccount[]; providers: any; defaults: Record<string, string> }>("ai");
    this.ai = r.accounts;
    this.providers = r.providers;
    this.defaults = r.defaults;
  }
  watch() {
    if (this.timer) return () => {};
    this.load();
    this.loadAi();
    this.timer = setInterval(() => this.load(), 2500);
    const aiT = setInterval(() => this.loadAi(), 30000);
    return () => { clearInterval(this.timer!); clearInterval(aiT); this.timer = null; };
  }

  async open(repoId?: string, path?: string) {
    const r = await post<{ id: string }>("ws/open", { repoId, path });
    this.active = r.id;
    await this.load();
    return r.id;
  }
  async close(repoId: string) {
    const p = this.projects.find(x => x.id === repoId);
    const running = p ? [...p.terms, ...p.tasks.flatMap(t => t.terms)].filter(t => t.alive).length : 0;
    if (running && !(await ui.ask({ title: `Fechar ${p!.name}?`, message: `${running} terminal(is)/agente(s) deste projeto serão encerrados. As tarefas e os worktrees continuam.`, confirm: "Fechar", danger: true }))) return;
    await post("ws/close", { repoId });
    await this.load();
  }
  async activate(repoId: string) {
    this.active = repoId;
    post("ws/activate", { repoId }).catch(() => {});
  }

  /** Acha o clone local de um repositório remoto. GitHub: "dono/repo"; Azure: org + nome do repo. */
  findLocal(provider: string, org: string, repo: string) {
    const n = (s?: string | null) => (s || "").toLowerCase();
    return repos.local.find(r => r.provider === provider && r.exists && r.slug && (provider === "github"
      ? n(r.slug) === n(repo.includes("/") ? repo : `${org}/${repo}`)
      : n(r.slug.split("/")[0]) === n(org) && n(r.slug.split("/").pop()) === n(repo))) || null;
  }

  /** Abre o projeto certo e a "Nova tarefa" preenchida. Sem clone local, avisa; sem repo (work item do Azure), usa o projeto ativo. */
  async startTask(target: { provider: string; org: string; repo?: string | null } | null, preset: any) {
    if (!repos.loaded) await repos.load(false);
    let local = target?.repo ? this.findLocal(target.provider, target.org, target.repo) : null;
    if (!local && target?.repo) {
      return ui.toast(`${target.repo} não está clonado nesta máquina — clone em Repositórios e tente de novo`, "info");
    }
    const projectId = local ? await this.open(local.id) : this.active;
    if (!projectId) return ui.toast("Abra um projeto em Projetos primeiro", "info");
    this.pendingTask = { projectId, preset };
    go("/work/" + projectId);
  }

  /** Repositório = projeto. Um link de repositório (lista, barra lateral, ⌘K) abre o projeto na aba Git; se o
   *  repositório é o worktree de uma tarefa, abre a tarefa (o Git dela é o do worktree). */
  async openRepo(repoId: string, tab: "git" | "review" = "git") {
    if (!this.loaded) await this.load();
    const owner = this.projects.find(p => p.tasks.some(t => t.repoId === repoId));
    const task = owner?.tasks.find(t => t.repoId === repoId);
    const projectId = owner ? owner.id : repoId;
    this.focusRequest = { projectId, scope: task?.id || null, tab };
    go("/work/" + projectId);
  }

  /** Conta sugerida para um projeto: a padrão do dono (org) do repositório, senão a geral, senão a 1ª instalada. */
  defaultAccount(p?: Project | null) {
    const scope = p?.provider && p.slug ? `${p.provider}:${p.slug.split("/")[0]}` : "";
    return this.defaults[scope] || this.defaults["*"] || this.ai.find(a => a.installed && a.provider === "claude")?.id || this.ai.find(a => a.installed)?.id || null;
  }
}

export const work = new Work();

export const STATUS: Record<string, [string, string]> = {
  starting: ["abrindo…", "muted"], idle: ["pronto", "muted"], working: ["trabalhando", "accent"], done: ["terminou", "good"],
  "needs-you": ["precisa de você", "warn"], compacting: ["compactando", "info"],
};
