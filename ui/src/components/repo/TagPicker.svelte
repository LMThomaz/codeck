<script lang="ts">
  // Tags de um favorito: chips + campo que sugere as tags existentes e CRIA a tag nova ao digitar e confirmar.
  // Enter/Tab confirma, Backspace no campo vazio remove a última, Esc fecha. A cor da tag nova é a próxima da paleta.
  import { Plus, X } from "@lucide/svelte";
  import { tick } from "svelte";
  import { repos } from "../../lib/repos.svelte";
  import { ui } from "../../lib/ui.svelte";

  let { key, compact = false }: { key: string; compact?: boolean } = $props();
  const current = $derived(repos.fav(key)?.tags || []);
  let open = $state(false);
  let text = $state("");
  let hi = $state(0);
  let input: HTMLInputElement | undefined = $state();

  const options = $derived.by(() => {
    const t = text.trim().toLowerCase();
    const list = repos.tags.filter(x => !current.includes(x.name) && (!t || x.name.toLowerCase().includes(t)))
      .map(x => ({ name: x.name, color: x.color, count: x.count, create: false }));
    if (t && !repos.tags.some(x => x.name.toLowerCase() === t)) list.push({ name: text.trim(), color: "", count: 0, create: true });
    return list.slice(0, 8);
  });
  $effect(() => { void text; hi = 0; });

  async function save(tags: string[]) {
    try { await repos.setTags(key, tags); } catch (e) { ui.error(e); }
  }
  async function add(name: string) {
    if (!name.trim() || current.some(c => c.toLowerCase() === name.trim().toLowerCase())) return;
    text = "";
    await save([...current, name.trim()]);
    input?.focus();
  }
  const remove = (name: string) => save(current.filter(c => c !== name));
  async function start(e: MouseEvent) { e.stopPropagation(); open = true; await tick(); input?.focus(); }
  function key_(e: KeyboardEvent) {
    if (e.key === "ArrowDown") { hi = Math.min(hi + 1, options.length - 1); e.preventDefault(); }
    else if (e.key === "ArrowUp") { hi = Math.max(hi - 1, 0); e.preventDefault(); }
    else if ((e.key === "Enter" || e.key === "Tab") && (options[hi] || text.trim())) { e.preventDefault(); add(options[hi]?.name ?? text); }
    else if (e.key === "Backspace" && !text && current.length) remove(current[current.length - 1]);
    else if (e.key === "Escape") { open = false; text = ""; }
  }
  const color = (n: string) => repos.tag(n)?.color || "var(--muted)";
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<div class="tags" class:compact onclick={(e) => e.stopPropagation()} role="presentation" aria-label="Tags">
  {#each current as t (t)}
    <span class="chip" style="--c:{color(t)}"><span class="d"></span>{t}<button title="Tirar a tag" onclick={() => remove(t)}><X size={10} /></button></span>
  {/each}
  {#if open}
    <span class="combo">
      <input bind:this={input} bind:value={text} placeholder="tag…" onkeydown={key_} onblur={() => setTimeout(() => { open = false; text = ""; }, 150)} />
      {#if options.length}
        <div class="menu">
          {#each options as o, i (o.name + o.create)}
            <button class:hi={i === hi} onmousedown={(e) => { e.preventDefault(); add(o.name); }} onmouseenter={() => (hi = i)}>
              {#if o.create}<Plus size={12} /><span>Criar <b>“{o.name}”</b></span>
              {:else}<span class="d" style="background:{o.color}"></span><span class="grow">{o.name}</span><span class="n">{o.count}</span>{/if}
            </button>
          {/each}
        </div>
      {/if}
    </span>
  {:else}
    <button class="add" onclick={start} title="Adicionar tag"><Plus size={11} />{current.length ? "" : "tag"}</button>
  {/if}
</div>

<style>
  .tags { display: inline-flex; align-items: center; flex-wrap: wrap; gap: 4px; }
  .chip { --c: var(--muted); display: inline-flex; align-items: center; gap: 5px; height: 20px; padding: 0 3px 0 7px; border-radius: 99px; font: 550 11px/1 var(--font);
    color: var(--text-2); background: color-mix(in srgb, var(--c) 14%, transparent); border: 1px solid color-mix(in srgb, var(--c) 32%, transparent);
    animation: chip-in 0.28s var(--spring); }
  .chip .d, .menu .d { width: 6px; height: 6px; border-radius: 50%; background: var(--c); flex: none; }
  .chip button { display: grid; place-items: center; width: 15px; height: 15px; border: 0; border-radius: 50%; background: none; color: var(--muted); cursor: pointer; padding: 0; }
  .chip button:hover { background: color-mix(in srgb, var(--c) 30%, transparent); color: var(--text); }
  .add { display: inline-flex; align-items: center; gap: 3px; height: 20px; padding: 0 7px; border-radius: 99px; border: 1px dashed var(--line-3); background: none;
    color: var(--muted); font: 550 11px var(--font); cursor: pointer; transition: color var(--t), border-color var(--t); }
  .add:hover { color: var(--accent); border-color: var(--accent-line); }
  .combo { position: relative; }
  .combo input { width: 120px; height: 22px; padding: 0 8px; border-radius: 99px; border: 1px solid var(--accent-line); background: var(--surface); color: var(--text);
    font: 12px var(--font); outline: none; box-shadow: var(--ring); animation: chip-in 0.2s var(--ease-out); }
  .menu { position: absolute; z-index: 40; top: calc(100% + 6px); left: 0; min-width: 200px; padding: 4px; border-radius: 10px; background: var(--elevated);
    border: 1px solid var(--line-2); box-shadow: var(--shadow-3); display: grid; gap: 1px; animation: rise 0.18s var(--ease-out); }
  .menu button { display: flex; align-items: center; gap: 8px; height: 28px; padding: 0 8px; border: 0; border-radius: 7px; background: none; color: var(--text-2);
    font: 12.5px var(--font); text-align: left; cursor: pointer; }
  .menu button.hi { background: var(--accent-soft); color: var(--text); }
  .menu :global(svg) { color: var(--accent); }
  .menu .n { color: var(--faint); font-size: 11px; }
  @keyframes chip-in { from { opacity: 0; transform: scale(0.7); } }
</style>
