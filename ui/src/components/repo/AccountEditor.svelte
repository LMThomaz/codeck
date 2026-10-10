<script lang="ts">
  // Pastas base de uma conta: onde ficam os clones dela (pode haver várias — …/apis, …/mobile). São usadas para
  // reconhecer clones que já existem e aparecem primeiro na hora de clonar. Catálogos e tags só filtram; quem gere é a conta.
  import { ArrowUp, Folder, FolderPlus, Trash2 } from "@lucide/svelte";
  import { get, post } from "../../lib/api";
  import { pickFolder } from "../../lib/native";
  import { repos } from "../../lib/repos.svelte";
  import { ui } from "../../lib/ui.svelte";
  import Drawer from "../Drawer.svelte";
  import ProviderIcon from "../ProviderIcon.svelte";

  const key = $derived(ui.editAccount!);
  const acc = $derived(repos.accounts.find(a => a.key === key));
  let dirs = $state<string[]>([]);
  let counts = $state<Record<string, number>>({});
  let suggestions = $state<{ path: string; count: number }[]>([]);
  const home = (p: string) => p.replace(/^\/Users\/[^/]+|^C:\\Users\\[^\\]+/i, "~");

  $effect(() => {
    dirs = [...(acc?.dirs || [])];
    get<{ targets: { path: string; count: number; account: boolean }[] }>("clone-targets", { account: key }).then(r => {
      counts = Object.fromEntries(r.targets.map(t => [t.path, t.count]));
      suggestions = r.targets.filter(t => !t.account && t.count > 0);
    }).catch(() => {});
  });

  async function save(next: string[], msg: string) {
    try {
      const r = await post<{ dirs: string[] }>("accounts/dirs", { key, dirs: next });
      dirs = r.dirs;
      if (acc) acc.dirs = r.dirs;
      ui.toast(msg);
    } catch (e) { ui.error(e); }
  }
  async function add(path?: string) {
    const p = path || (await pickFolder(`Pasta base de ${acc?.name}`));
    if (p && !dirs.includes(p)) save([...dirs, p], "Pasta adicionada — os clones dentro dela já são reconhecidos");
  }
</script>

<Drawer title={acc ? acc.name : "Conta"} subtitle="Pastas base dos clones desta conta" onclose={() => (ui.editAccount = null)} width={540}>
  <div class="wrap">
    {#if acc}<div class="who"><ProviderIcon provider={acc.provider} size={16} /><b>{acc.name}</b><span class="muted small">· {acc.provider === "azure" ? "Azure DevOps" : "GitHub"} · {acc.count ?? "…"} repositórios</span></div>{/if}
    <p class="small muted">Onde ficam os repositórios clonados de <b>{acc?.name}</b>. Pode ter várias (ex.: <span class="mono">…/apis</span> e <span class="mono">…/mobile</span>).
      O app reconhece sozinho os clones dentro delas e as oferece primeiro na hora de clonar — a primeira da lista é a sugerida.</p>

    <div class="list">
      {#each dirs as d, i (d)}
        <div class="dir">
          <Folder size={15} />
          <div class="grow"><b>{d.split(/[\\/]/).pop()}</b><span class="small muted mono ell">{home(d)}</span></div>
          <span class="tiny muted">{counts[d] ? `${counts[d]} clone${counts[d] > 1 ? "s" : ""}` : "vazia"}</span>
          {#if i > 0}<button class="btn sm ghost icon" title="Usar como sugerida" onclick={() => save([d, ...dirs.filter(x => x !== d)], "Pasta sugerida alterada")}><ArrowUp size={13} /></button>
          {:else}<span class="pill accent">sugerida</span>{/if}
          <button class="btn sm ghost icon" title="Tirar da conta (a pasta continua no disco)" onclick={() => save(dirs.filter(x => x !== d), "Pasta removida da conta")}><Trash2 size={13} /></button>
        </div>
      {:else}
        <div class="empty small muted">Nenhuma pasta ainda — ao clonar, o app pergunta e pode guardar a escolha aqui.</div>
      {/each}
      <button class="btn" onclick={() => add()}><FolderPlus size={14} /> Adicionar pasta</button>
    </div>

    {#if suggestions.filter(s => !dirs.includes(s.path)).length}
      <h4>Pastas onde você já tem clones</h4>
      <div class="list">
        {#each suggestions.filter(s => !dirs.includes(s.path)) as s (s.path)}
          <button class="dir sug" onclick={() => add(s.path)}><Folder size={15} /><div class="grow"><b>{s.path.split(/[\\/]/).pop()}</b><span class="small muted mono ell">{home(s.path)}</span></div>
            <span class="tiny muted">{s.count} clone{s.count > 1 ? "s" : ""}</span><span class="pill neutral">+ usar</span></button>
        {/each}
      </div>
    {/if}
  </div>
</Drawer>

<style>
  .wrap { display: grid; gap: 14px; padding-top: 12px; }
  p { margin: 0; }
  h4 { margin: 4px 0 0; font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }
  .list { display: grid; gap: 6px; justify-items: start; }
  .dir { display: flex; align-items: center; gap: 10px; width: 100%; padding: 8px 8px 8px 12px; border-radius: 10px; border: 1px solid var(--line); background: var(--surface-2);
    color: var(--text-2); font: 13px var(--font); text-align: left; animation: rise 0.25s var(--ease-out) both; }
  .dir .grow { flex: 1; min-width: 0; display: grid; }
  .dir b { color: var(--text); }
  .sug { cursor: pointer; border-style: dashed; background: none; transition: border-color var(--t); }
  .sug:hover { border-color: var(--accent); }
  .who { display: flex; align-items: center; gap: 8px; }
  .empty { padding: 10px 2px; }
</style>
