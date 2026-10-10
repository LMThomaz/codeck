<script lang="ts">
  // Contas de IA: cada conta é uma pasta de configuração da CLI (Claude: CLAUDE_CONFIG_DIR; Codex: CODEX_HOME).
  // O login é o da própria CLI — o app nunca lê nem guarda token de IA.
  import { Check, Copy, FolderOpen, Plus, RefreshCw, Star, Trash2 } from "@lucide/svelte";
  import { get, post } from "../../lib/api";
  import { pickFolder } from "../../lib/native";
  import { store } from "../../lib/store.svelte";
  import { ui } from "../../lib/ui.svelte";
  import { work, type AiAccount } from "../../lib/work.svelte";
  import AgentIcon from "../work/AgentIcon.svelte";

  let found = $state<{ provider: string; dir: string; name: string; email?: string }[]>([]);
  let adding = $state<{ provider: string; name: string; dir: string } | null>(null);
  $effect(() => { work.loadAi(); });
  const home = (p: string) => p.replace(/^\/Users\/[^/]+|^C:\\Users\\[^\\]+/i, "~");
  const scopes = $derived(["*", ...(store.s?.orgs || []).map(o => `azure:${o}`), ...(store.s?.githubAccounts || []).map(a => `github:${a.login}`)]);
  const scopeLabel = (s: string) => (s === "*" ? "Geral" : s.replace(/^azure:/, "Azure · ").replace(/^github:/, "GitHub · "));

  async function detect() {
    found = (await get<any>("ai/detect")).found.filter((f: any) => !work.ai.some(a => a.dir === f.dir));
    if (!found.length) ui.toast("Nenhuma conta nova encontrada", "info");
  }
  async function add(f: { provider: string; name: string; dir: string }) {
    try { await post("ai/save", f); await work.loadAi(); found = found.filter(x => x.dir !== f.dir); adding = null; ui.toast("Conta adicionada"); } catch (e) { ui.error(e); }
  }
  async function remove(a: AiAccount) {
    if (!(await ui.ask({ title: `Tirar ${a.label} · ${a.name} do app?`, message: "A pasta e o login continuam na máquina; só some daqui.", confirm: "Tirar", danger: true }))) return;
    await post("ai/delete", { id: a.id }); await work.loadAi();
  }
  async function setDefault(scope: string, id: string) { await post("ai/default", { scope, id }); await work.loadAi(); ui.toast("Conta padrão salva"); }
  const loginCmd = (p: string, dir: string) => p === "claude" ? `CLAUDE_CONFIG_DIR=${dir} claude` : p === "codex" ? `CODEX_HOME=${dir} codex login` : p === "cursor" ? "cursor-agent login" : p;
  async function copy(t: string) { await navigator.clipboard.writeText(t); ui.toast("Comando copiado — rode num terminal (Projetos → ⌘T)"); }
  const grouped = $derived(Object.entries(work.providers).map(([k, v]) => ({ key: k, ...v, accounts: work.ai.filter(a => a.provider === k) })).filter(g => g.accounts.length || g.installed));
</script>

<div class="head"><div><h2>Contas de IA</h2><p class="muted small">Claude Code, Codex, Cursor e outras CLIs. Cada conta é uma pasta de configuração — o login é o da própria CLI.</p></div>
  <span class="spacer"></span>
  <button class="btn sm ghost" onclick={detect}><RefreshCw size={14} /> Procurar contas</button>
  <button class="btn sm" onclick={() => (adding = { provider: "claude", name: "", dir: "" })}><Plus size={14} /> Conta</button></div>

{#if found.length}
  <div class="card org found"><b>Encontradas nesta máquina</b>
    {#each found as f (f.dir)}<div class="acc"><AgentIcon provider={f.provider} size={18} /><div class="grow"><b>{f.name}</b><span class="tiny muted mono">{home(f.dir)}{f.email ? " · " + f.email : ""}</span></div><button class="btn sm" onclick={() => add(f)}><Plus size={13} /> Adicionar</button></div>{/each}
  </div>
{/if}

{#if adding}
  <div class="card org">
    <b>Nova conta</b>
    <div class="row3">
      <select class="input" bind:value={adding.provider}>{#each Object.entries(work.providers) as [k, p] (k)}<option value={k}>{p.label}</option>{/each}</select>
      <input class="input" bind:value={adding.name} placeholder="nome (ex.: dematec)" />
    </div>
    <div class="row3"><input class="input mono" bind:value={adding.dir} placeholder={adding.provider === "claude" ? "~/.claude-minha-conta" : adding.provider === "codex" ? "~/.codex-minha-conta" : "pasta de configuração"} />
      <button class="btn" onclick={async () => { const p = await pickFolder("Pasta de configuração da conta"); if (p && adding) adding.dir = p; }}><FolderOpen size={14} /></button></div>
    {#if adding.dir}<div class="small muted">Login (uma vez): <span class="mono">{loginCmd(adding.provider, adding.dir)}</span> <button class="btn sm ghost icon" onclick={() => copy(loginCmd(adding!.provider, adding!.dir))}><Copy size={12} /></button></div>{/if}
    <div class="row3 end"><button class="btn sm" onclick={() => (adding = null)}>Cancelar</button><button class="btn sm primary" disabled={!adding.dir} onclick={() => add(adding!)}><Check size={13} /> Salvar</button></div>
  </div>
{/if}

{#each grouped as g (g.key)}
  <div class="card org">
    <div class="gh"><AgentIcon provider={g.key} size={18} /><b>{g.label}</b>{#if !g.installed}<span class="pill warn">CLI não instalada</span>{/if}</div>
    {#each g.accounts as a (a.id)}
      <div class="acc">
        <div class="grow"><b>{a.name}</b><span class="tiny muted mono ell">{home(a.dir)}{a.email ? " · " + a.email : ""}</span></div>
        {#if a.usage?.rateLimits?.length}<span class="tiny muted">{a.usage.rateLimits.map(w => `${w.window} ${Math.round(w.used || 0)}%`).join(" · ")}</span>{/if}
        {#each Object.entries(work.defaults).filter(([, id]) => id === a.id) as [sc] (sc)}<span class="pill accent"><Star size={10} /> {scopeLabel(sc)}</span>{/each}
        <select class="input mini" value="" onchange={(e) => { const sc = (e.target as HTMLSelectElement).value; if (sc) setDefault(sc, a.id); (e.target as HTMLSelectElement).value = ""; }}>
          <option value="">Padrão para…</option>{#each scopes as sc (sc)}<option value={sc}>{scopeLabel(sc)}</option>{/each}</select>
        <button class="btn sm ghost icon" title="Copiar comando de login" onclick={() => copy(loginCmd(a.provider, a.dir))}><Copy size={13} /></button>
        <button class="btn sm ghost icon" title="Tirar do app" onclick={() => remove(a)}><Trash2 size={13} /></button>
      </div>
    {:else}<div class="small muted">Nenhuma conta. “Procurar contas” acha as pastas existentes; “Conta” cria uma nova.</div>{/each}
  </div>
{/each}

<style>
  .head { display: flex; align-items: flex-start; gap: 8px; }
  .head h2 { margin: 0 0 4px; }
  .spacer { flex: 1; }
  .card { display: grid; gap: 10px; padding: 14px; margin-top: 12px; }
  .gh { display: flex; align-items: center; gap: 9px; }
  .acc { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 10px; background: var(--surface-2); border: 1px solid var(--line); animation: rise 0.25s var(--ease-out) both; }
  .acc .grow { flex: 1; min-width: 0; display: grid; }
  .row3 { display: flex; gap: 8px; }
  .row3 .input { flex: 1; }
  .row3.end { justify-content: flex-end; }
  .mini { width: 140px; height: 27px; font-size: 12px; flex: none; }
  .found { border-color: var(--accent-line); }
</style>
