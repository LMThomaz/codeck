<script lang="ts">
  // Configurações: organizações do Azure DevOps, contas do GitHub, preferências e sobre/atualização.
  // Segredos (PAT/token) só vão para o servidor local, que os guarda no cofre do sistema — nunca voltam para a tela.
  import { Bot } from "@lucide/svelte";
  import { Check, ExternalLink, KeyRound, LogIn, Monitor, Moon, Plus, RefreshCw, Shield, SlidersHorizontal, Sun, Terminal, Trash2, Info } from "@lucide/svelte";
  import { untrack } from "svelte";
  import { get, post } from "../lib/api";
  import { dateTime } from "../lib/format";
  import { go, router } from "../lib/router.svelte";
  import { store } from "../lib/store.svelte";
  import { ui } from "../lib/ui.svelte";
  import Avatar from "../components/Avatar.svelte";
  import Page from "../components/Page.svelte";
  import ProviderIcon from "../components/ProviderIcon.svelte";
  import Skeleton from "../components/Skeleton.svelte";
  import Switch from "../components/Switch.svelte";
  import Segmented from "../components/Segmented.svelte";
  import AiAccounts from "../components/settings/AiAccounts.svelte";
  import TestResult from "../components/TestResult.svelte";
  import { chooseTheme, type ThemePref } from "../lib/theme";

  type OrgForm = { name: string; url: string; pat: string; enabled: boolean; originalName?: string; hasPat?: boolean; patStore?: string; me?: any; test?: any };
  const TABS = [
    { id: "accounts", label: "Azure DevOps", provider: "azure" },
    { id: "github", label: "GitHub", provider: "github" },
    { id: "ai", label: "IA", icon: Bot },
    { id: "prefs", label: "Preferências", icon: SlidersHorizontal },
    { id: "about", label: "Sobre", icon: Info },
  ];
  const tab = $derived(TABS.some(t => t.id === router.param) ? router.param : "accounts");

  let cfg = $state<any>(null);
  let orgs = $state<OrgForm[]>([]);
  let saving = $state(false);
  let ghTests = $state<Record<string, any>>({});
  let token = $state("");
  let device = $state<any>(null);
  let busy = $state("");

  async function load() {
    const c = await get("config");
    cfg = c;
    orgs = c.orgs.map((o: any) => ({ name: o.name, url: o.url, pat: "", enabled: o.enabled, originalName: o.name, hasPat: o.hasPat, patStore: o.patStore, me: o.me }));
    if (!orgs.length && !c.github.length) orgs = [blankOrg()];
  }
  $effect(() => { untrack(() => load().catch(ui.error)); });

  const blankOrg = (): OrgForm => ({ name: "", url: "https://dev.azure.com/", pat: "", enabled: true });

  async function testOrg(o: OrgForm) {
    o.test = { running: true };
    try { o.test = await post("config/test", { name: o.name, url: o.url, pat: o.pat, originalName: o.originalName }); }
    catch (e: any) { o.test = { error: e.message }; }
  }
  async function saveOrgs() {
    saving = true;
    try {
      await post("config", { orgs: orgs.map(o => ({ name: o.name, url: o.url, pat: o.pat, enabled: o.enabled, originalName: o.originalName })), pollSeconds: cfg.pollSeconds });
      ui.toast("Organizações salvas — PATs no cofre do sistema");
      await load(); store.refreshSoon();
    } catch (e) { ui.error(e); } finally { saving = false; }
  }
  async function removeOrg(i: number) {
    const o = orgs[i];
    if (o.originalName && !(await ui.ask({ title: `Remover ${o.name}?`, message: "O PAT sai do cofre ao salvar.", confirm: "Remover", danger: true }))) return;
    orgs = orgs.filter((_, k) => k !== i);
  }

  async function addAccount(kind: "token" | "cli") {
    busy = kind;
    try {
      const a = kind === "cli" ? await post("github/cli") : await post("github/token", { token });
      token = "";
      ui.toast(`Conectado como @${a.login}`);
      await load(); store.refreshSoon();
    } catch (e) { ui.error(e); } finally { busy = ""; }
  }
  async function startDevice() {
    busy = "device";
    try {
      device = await post("github/device/start");
      window.open(device.verificationUri, "_blank");
      const id = device.id;
      while (device?.id === id && device.status === "pending") {
        await new Promise(r => setTimeout(r, 2500));
        if (device?.id !== id) return;
        device = await get("github/device", { id });
      }
      if (device?.status === "done") { ui.toast(`Conectado como @${device.account.login}`); device = null; await load(); store.refreshSoon(); }
    } catch (e) { ui.error(e); device = null; } finally { busy = ""; }
  }
  async function testGh(id: string) {
    ghTests[id] = { running: true };
    try { ghTests[id] = await post("github/test", { id }); } catch (e: any) { ghTests[id] = { error: e.message }; }
  }
  async function removeGh(a: any) {
    if (!(await ui.ask({ title: `Desconectar @${a.login}?`, message: "O token é apagado do cofre do sistema.", confirm: "Desconectar", danger: true }))) return;
    try { await post("github/remove", { id: a.id }); await load(); store.refreshSoon(); } catch (e) { ui.error(e); }
  }

  async function savePrefs(patch: Record<string, unknown>) {
    try { await post("prefs", patch); cfg = { ...cfg, ...patch }; ui.toast("Preferência salva"); } catch (e) { ui.error(e); }
  }
  async function copy(t: string) { await navigator.clipboard.writeText(t); ui.toast("Código copiado"); }
</script>

<Page title="Configurações" sub="Contas, preferências e segurança">
  <div class="layout">
    <nav class="tabs">
      {#each TABS as t (t.id)}
        <button class:on={tab === t.id} onclick={() => go(`/settings/${t.id}`, "soft")}>{#if t.provider}<ProviderIcon provider={t.provider} size={15} />{:else if t.icon}<t.icon size={15} />{/if} {t.label}</button>
      {/each}
      <div class="sec-note"><Shield size={14} /><span>Credenciais ficam criptografadas no {cfg?.orgs?.[0]?.patStore || cfg?.github?.[0]?.store || "cofre do sistema"}; a tela nunca as recebe de volta.</span></div>
    </nav>

    <div class="body">
      {#if !cfg}<Skeleton rows={4} />
      {:else if tab === "accounts"}
        <div class="head"><div><h2>Organizações do Azure DevOps</h2><p class="muted small">PRs, builds, releases, aprovações de deploy e work items.</p></div>
          <span class="spacer"></span><button class="btn sm ghost" onclick={() => (orgs = [...orgs, blankOrg()])}><Plus size={14} /> Organização</button></div>
        {#each orgs as o, i (i)}
          <div class="card org">
            <div class="row" style="gap:10px">
              <Switch bind:checked={o.enabled} />
              <b>{o.name || "Nova organização"}</b>
              {#if o.me}<span class="pill good"><Check size={11} /> {o.me.displayName || o.me.name || "conectado"}</span>{/if}
              <span class="spacer"></span>
              <button class="btn sm ghost danger" onclick={() => removeOrg(i)}><Trash2 size={14} /></button>
            </div>
            <div class="fields">
              <label><span>Nome</span><input class="input" bind:value={o.name} placeholder="Cifal" /></label>
              <label><span>URL da organização</span><input class="input" bind:value={o.url} placeholder="https://dev.azure.com/minha-org" /></label>
              <label class="full"><span>Personal Access Token {#if o.hasPat}<em class="good">· salvo no {o.patStore || "cofre"} — deixe vazio para manter</em>{/if}</span>
                <input class="input mono" type="password" autocomplete="off" bind:value={o.pat} placeholder={o.hasPat ? "••••••••••••••••" : "cole o PAT"} /></label>
            </div>
            <div class="row" style="gap:8px">
              <button class="btn sm" onclick={() => testOrg(o)} disabled={!o.url || (!o.pat && !o.hasPat)}><KeyRound size={14} /> Testar</button>
              <span class="tiny muted">Escopos: Code (Read & Write), Build (Read & Execute), Release (Read, Write & Execute), Work Items (Read), Project (Read).</span>
            </div>
            {#if o.test}<div class="test"><TestResult test={o.test} /></div>{/if}
          </div>
        {/each}
        <div class="foot"><button class="btn primary" onclick={saveOrgs} disabled={saving}>{saving ? "Salvando…" : "Salvar organizações"}</button></div>

      {:else if tab === "github"}
        <div class="head"><div><h2>Contas do GitHub</h2><p class="muted small">Pessoais, organizações e repositórios de terceiros a que o perfil tem acesso — PRs, Actions, issues e deploys.</p></div></div>
        {#each cfg.github as a (a.id)}
          <div class="card org">
            <div class="row" style="gap:10px">
              <Avatar name={a.login} src={a.avatar} size={30} />
              <div><b>{a.name || a.login}</b><div class="tiny muted">@{a.login} · {a.store || "cofre"} · conectado {dateTime(a.connectedAt)}</div></div>
              <span class="spacer"></span>
              {#if a.rate}<span class="tiny muted">API {a.rate.remaining}/{a.rate.limit}</span>{/if}
              <button class="btn sm" onclick={() => testGh(a.id)}><KeyRound size={14} /> Testar</button>
              <button class="btn sm ghost danger" onclick={() => removeGh(a)}><Trash2 size={14} /></button>
            </div>
            {#if a.scopes?.length}<div class="scopes">{#each a.scopes as s (s)}<span class="pill neutral">{s}</span>{/each}</div>{/if}
            {#if ghTests[a.id]}<div class="test"><TestResult test={ghTests[a.id]} /></div>{/if}
          </div>
        {/each}

        <div class="connect">
          <div class="card opt">
            <LogIn size={20} /><h4>Entrar com GitHub</h4>
            <p class="small muted">Abre o navegador, você digita um código e pronto. Sem copiar token.</p>
            {#if device}
              <div class="code"><button class="mono" onclick={() => copy(device.userCode)} title="Copiar">{device.userCode}</button>
                <a href={device.verificationUri} target="_blank" rel="noopener" class="small">{device.verificationUri} <ExternalLink size={11} /></a>
                <span class="small muted">{device.status === "error" ? device.error : "aguardando você autorizar…"}</span></div>
            {:else}
              <button class="btn primary sm" onclick={startDevice} disabled={!cfg.githubLogin || !!busy} title={cfg.githubLogin ? "" : "Este build ainda não tem o client id do OAuth App"}>Entrar</button>
              {#if !cfg.githubLogin}<span class="tiny muted">indisponível neste build — use o gh CLI ou um token</span>{/if}
            {/if}
          </div>
          <div class="card opt">
            <Terminal size={20} /><h4>Usar o login do gh CLI</h4>
            <p class="small muted">Reaproveita o <code>gh auth login</code> já feito nesta máquina.</p>
            <button class="btn sm" onclick={() => addAccount("cli")} disabled={!cfg.ghCli || !!busy}>{busy === "cli" ? "Conectando…" : "Importar"}</button>
            {#if !cfg.ghCli}<span class="tiny muted">gh CLI não encontrado</span>{/if}
          </div>
          <div class="card opt">
            <KeyRound size={20} /><h4>Colar um token</h4>
            <p class="small muted">Classic com <code>repo</code>, <code>workflow</code>, <code>read:org</code> — ou fine-grained.</p>
            <input class="input mono" type="password" autocomplete="off" bind:value={token} placeholder="ghp_… ou github_pat_…" />
            <button class="btn sm" onclick={() => addAccount("token")} disabled={!token.trim() || !!busy}>{busy === "token" ? "Conectando…" : "Conectar"}</button>
          </div>
        </div>

      {:else if tab === "ai"}
        <AiAccounts />
      {:else if tab === "prefs"}
        <div class="head"><div><h2>Preferências</h2></div></div>
        <div class="card org">
          <div class="pref"><div><b>Tema</b><div class="small muted">“Sistema” acompanha o claro/escuro do {navigator.platform.includes("Mac") ? "macOS" : "Windows"} e troca sozinho.</div></div>
            <Segmented size="sm" value={cfg.theme || "system"} onchange={(v) => { chooseTheme(v as ThemePref); savePrefs({ theme: v }); }}
              options={[{ value: "system", label: "Sistema", icon: Monitor }, { value: "dark", label: "Escuro", icon: Moon }, { value: "light", label: "Claro", icon: Sun }]} /></div>
          <div class="pref"><div><b>Editor</b><div class="small muted">Usado em “Abrir no editor” nos repositórios.</div></div>
            <select class="input" value={cfg.editor} onchange={(e) => savePrefs({ editor: (e.target as HTMLSelectElement).value })}>
              {#each cfg.editors as ed (ed.id)}<option value={ed.id}>{ed.name}</option>{:else}<option value="">nenhum editor encontrado</option>{/each}
            </select></div>
          <div class="pref"><div><b>Intervalo de leitura</b><div class="small muted">De quanto em quanto tempo o piloto consulta Azure e GitHub (15 s a 1 h).</div></div>
            <select class="input" value={String(cfg.pollSeconds)} onchange={(e) => savePrefs({ pollSeconds: Number((e.target as HTMLSelectElement).value) })}>
              {#each [15, 30, 60, 120, 300, 600] as s (s)}<option value={String(s)}>{s < 60 ? `${s} s` : `${s / 60} min`}</option>{/each}
            </select></div>
          <div class="pref"><div><b>Pastas dos clones</b><div class="small muted">Ficam em cada conta: Repositórios → Contas → “⋯” → Pastas base.</div></div></div>
          <div class="pref"><div><b>Pasta de dados</b><div class="small muted mono">{cfg.dataDir}</div></div></div>
        </div>

      {:else}
        <div class="head"><div><h2>{store.s?.app.product || "Codeck"}</h2><p class="muted small">Versão {store.s?.app.version} · build {store.s?.app.build} · {store.s?.app.platform}</p></div></div>
        <div class="card org">
          <div class="pref"><div><b>Atualizações</b><div class="small muted">
            {#if store.s?.update.available}Versão {store.s.update.version} disponível{:else if store.s?.update.checkedAt}Em dia — verificado {dateTime(store.s.update.checkedAt)}{:else}Ainda não verificado{/if}</div></div>
            <button class="btn sm" onclick={() => (window as any).checkUpdate?.(true)}><RefreshCw size={14} /> Procurar agora</button></div>
          <div class="pref"><div><b>Segurança</b><div class="small muted">O servidor local só escuta em 127.0.0.1 e exige um token por execução. PATs e tokens ficam no Keychain (macOS) ou DPAPI (Windows).</div></div></div>
        </div>
      {/if}
    </div>
  </div>
</Page>

<style>
  .layout { display: grid; grid-template-columns: 210px minmax(0, 1fr); gap: 22px; flex: 1; min-height: 0; }
  .tabs { display: flex; flex-direction: column; gap: 2px; }
  .tabs button { display: flex; align-items: center; gap: 9px; height: 34px; padding: 0 11px; border: 0; border-radius: 9px; background: none; color: var(--text-2);
    font: 550 13px var(--font); cursor: pointer; text-align: left; transition: background var(--t-fast), color var(--t-fast); }
  .tabs button:hover { background: var(--surface-2); color: var(--text); }
  .tabs button.on { background: var(--accent-soft); color: var(--text); }
  .sec-note { margin-top: 14px; display: flex; gap: 8px; font-size: 11.5px; color: var(--muted); line-height: 1.45; padding: 0 6px; }
  .sec-note :global(svg) { flex: none; color: var(--good); margin-top: 1px; }
  .body { overflow: auto; min-height: 0; overscroll-behavior: contain; padding-right: 4px; max-width: 920px; }
  .head { display: flex; align-items: flex-end; gap: 10px; margin-bottom: 12px; }
  .head h2 { margin: 0 0 3px; font-size: 16px; }
  .head p { margin: 0; }
  .org { padding: 14px 16px; margin-bottom: 12px; display: grid; gap: 12px; }
  .fields { display: grid; grid-template-columns: 1fr 2fr; gap: 10px; }
  .fields label { display: grid; gap: 5px; font-size: 12px; color: var(--text-2); }
  .fields .full { grid-column: 1 / -1; }
  .fields em { font-style: normal; }
  .good { color: var(--good); }
  .danger:hover { color: var(--bad); }
  .foot { display: flex; justify-content: flex-end; padding-bottom: 20px; }
  .scopes { display: flex; flex-wrap: wrap; gap: 5px; }
  .connect { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-top: 6px; }
  .opt { padding: 16px; display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
  .opt h4 { margin: 2px 0 0; font-size: 14px; }
  .opt p { margin: 0; flex: 1; }
  .opt :global(svg:first-child) { color: var(--accent); }
  .opt .input { width: 100%; }
  .code { display: grid; gap: 6px; }
  .code button { font-size: 22px; letter-spacing: 0.12em; border: 1px dashed var(--line-2); background: var(--surface-2); color: var(--text); border-radius: 9px; padding: 6px 12px; cursor: copy; }
  .pref { display: flex; align-items: center; gap: 16px; justify-content: space-between; }
  .pref + .pref { border-top: 1px solid var(--line); padding-top: 12px; }
  .pref select { width: 220px; }
  .test { border-top: 1px solid var(--line); padding-top: 10px; }
  @media (max-width: 900px) { .layout { grid-template-columns: 1fr; } .tabs { flex-direction: row; flex-wrap: wrap; } .sec-note { display: none; } .fields { grid-template-columns: 1fr; } }
</style>
