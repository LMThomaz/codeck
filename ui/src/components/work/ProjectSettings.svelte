<script lang="ts">
  // Ajustes do projeto: o que copiar para cada worktree (arquivos locais que o Git não leva), o script de preparação,
  // onde ficam os worktrees e o shell dos terminais.
  import { FolderOpen, Plus, X } from "@lucide/svelte";
  import { untrack } from "svelte";
  import { post } from "../../lib/api";
  import { pickFolder } from "../../lib/native";
  import { ui } from "../../lib/ui.svelte";
  import type { Project } from "../../lib/work.svelte";
  import { work } from "../../lib/work.svelte";
  import Drawer from "../Drawer.svelte";

  let { project, onclose }: { project: Project; onclose: () => void } = $props();
  const s0 = untrack(() => project.settings);
  let copy = $state<string[]>([...(s0.copy || [])]);
  let setup = $state(s0.setup || "");
  let root = $state(s0.worktreeRoot || "");
  let shell = $state((s0 as any).shell || "");
  let addDirs = $state<string[]>([...((s0 as any).addDirs || [])]);
  let novo = $state("");
  let busy = $state(false);
  const SUGGEST = ["workspace.local.json", "nuget.config", ".env", ".env.local", "**/appsettings.Development.json", "**/appsettings.Local.json",
    ".claude/settings.local.json", ".vscode/settings.json", "*.pem", "*.p12"];

  async function save() {
    busy = true;
    try {
      await post("ws/settings", { repoId: project.id, copy, setup, worktreeRoot: root, shell, addDirs });
      await work.load();
      ui.toast("Ajustes do projeto salvos");
      onclose();
    } catch (e) { ui.error(e); }
    busy = false;
  }
  const add = (p: string) => { p = p.trim(); if (p && !copy.includes(p)) copy = [...copy, p]; novo = ""; };
</script>

<Drawer title={`Ajustes de ${project.name}`} subtitle="Valem para as próximas tarefas e terminais deste projeto" {onclose} width={560}>
  <div class="form">
    <section>
      <h4>Copiar para cada worktree</h4>
      <p class="small muted">Arquivos locais que o Git não leva e sem os quais o projeto não roda. Aceita padrões (<span class="mono">**/appsettings.Development.json</span>).
        Os copiados entram no exclude do Git — nunca vão para commit.</p>
      <div class="chips">{#each copy as c (c)}<span class="chip mono">{c}<button aria-label="Tirar" onclick={() => (copy = copy.filter(x => x !== c))}><X size={11} /></button></span>{/each}</div>
      <div class="row"><input class="input mono" bind:value={novo} placeholder="ex.: config/local.json" onkeydown={(e) => e.key === "Enter" && add(novo)} />
        <button class="btn" disabled={!novo.trim()} onclick={() => add(novo)}><Plus size={14} /></button></div>
      <div class="sugg">{#each SUGGEST.filter(x => !copy.includes(x)) as s (s)}<button class="pill neutral" onclick={() => add(s)}>+ {s}</button>{/each}</div>
    </section>
    <section>
      <h4>Preparação</h4>
      <p class="small muted">Roda num terminal quando a tarefa é criada (ex.: <span class="mono">npm ci</span>, <span class="mono">bash .claude/scripts/ws-dotnet.sh restore</span>).</p>
      <textarea class="input mono" rows="3" bind:value={setup} placeholder="vazio = nada"></textarea>
    </section>
    <section>
      <h4>Pasta dos worktrees</h4>
      <p class="small muted">Vazio = <span class="mono">&lt;pasta do repositório&gt;/../.worktrees/{project.name}</span>.</p>
      <div class="row"><input class="input mono" bind:value={root} placeholder="padrão" />
        <button class="btn" onclick={async () => { const p = await pickFolder("Pasta dos worktrees"); if (p) root = p; }}><FolderOpen size={14} /></button></div>
    </section>
    <section>
      <h4>Pastas extras para o agente</h4>
      <p class="small muted">Outros repositórios que o agente pode ler/editar junto (ex.: a lib de entidades). No Claude vira <span class="mono">--add-dir</span>.</p>
      <div class="chips">{#each addDirs as d (d)}<span class="chip mono">{d.replace(/^\/Users\/[^/]+/, "~")}<button aria-label="Tirar" onclick={() => (addDirs = addDirs.filter(x => x !== d))}><X size={11} /></button></span>{/each}</div>
      <button class="btn sm" onclick={async () => { const p = await pickFolder("Pasta extra para o agente"); if (p && !addDirs.includes(p)) addDirs = [...addDirs, p]; }}><Plus size={13} /> Adicionar pasta</button>
    </section>
    <section>
      <h4>Shell dos terminais</h4>
      <input class="input mono" bind:value={shell} placeholder="padrão do sistema (ex.: /bin/zsh, pwsh, bash)" />
    </section>
  </div>
  {#snippet footer()}
    <span class="spacer"></span>
    <button class="btn" onclick={onclose}>Cancelar</button>
    <button class="btn primary" disabled={busy} onclick={save}>Salvar</button>
  {/snippet}
</Drawer>

<style>
  .form { display: grid; gap: 18px; padding-top: 12px; }
  section { display: grid; gap: 8px; }
  h4 { margin: 0; font: 650 10.5px/1 var(--font); text-transform: uppercase; letter-spacing: 0.07em; color: var(--muted); }
  p { margin: 0; }
  .row { display: flex; gap: 6px; }
  .row .input { flex: 1; }
  .chips { display: flex; flex-wrap: wrap; gap: 5px; }
  .chip { display: inline-flex; align-items: center; gap: 5px; padding: 3px 4px 3px 9px; border-radius: 99px; background: var(--surface-2); border: 1px solid var(--line-2); font-size: 12px; }
  .chip button { display: grid; place-items: center; width: 16px; height: 16px; border: 0; border-radius: 50%; background: none; color: var(--muted); cursor: pointer; }
  .chip button:hover { background: var(--surface-3); color: var(--text); }
  .sugg { display: flex; flex-wrap: wrap; gap: 4px; }
  .sugg .pill { cursor: pointer; border: 1px dashed var(--line-3); }
  textarea { resize: vertical; height: auto; font-size: 12.5px; padding: 8px 10px; }
  .spacer { flex: 1; }
</style>
