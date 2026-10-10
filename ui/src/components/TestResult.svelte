<script lang="ts">
  // Resultado do teste de uma conta (Azure ou GitHub): veredito no topo e cada verificação agrupada por área.
  let { test }: { test: any } = $props();
  const icon: Record<string, string> = { ok: "✓", fail: "✕", warn: "!" };
  const groups = $derived(test?.checks ? [...new Set(test.checks.map((c: any) => c.group))] as string[] : []);
  const cls = $derived(test?.verdict === "Pronto para tudo" ? "ok" : test?.verdict === "Não conecta" ? "fail" : "warn");
</script>

{#if test?.running}
  <div class="verdict run"><span class="spinner"></span> Testando cada coisa que o app faz…</div>
{:else if test?.error}
  <div class="verdict fail">✕ {test.error}</div>
{:else if test}
  <div class="verdict {cls}">{icon[cls]} <b>{test.verdict}</b>
    <span class="sub">{test.checks.filter((c: any) => c.status === "ok").length} de {test.checks.length} verificações · {test.ms} ms · nada foi alterado</span></div>
  <div class="grid stagger">
    {#each groups as g (g)}
      <div class="group">
        <h5>{g}</h5>
        {#each test.checks.filter((c: any) => c.group === g) as c (c.label)}
          <div class="check {c.status}">
            <span class="ti">{icon[c.status]}</span>
            <div class="grow"><b>{c.label}</b><div class="small muted">{c.detail}</div>{#if c.fix}<div class="small fix">→ {c.fix}</div>{/if}</div>
          </div>
        {/each}
      </div>
    {/each}
  </div>
{/if}

<style>
  .verdict { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 10px 13px; border-radius: 10px; font-size: 13.5px; animation: rise 0.3s var(--ease-out); }
  .verdict.ok { background: var(--good-soft); color: var(--good); }
  .verdict.fail { background: var(--bad-soft); color: var(--bad); }
  .verdict.warn { background: var(--warn-soft); color: var(--warn); }
  .verdict.run { background: var(--surface-2); color: var(--text-2); }
  .sub { opacity: 0.75; font-size: 12px; }
  .spinner { width: 13px; height: 13px; border-radius: 50%; border: 2px solid var(--line-3); border-top-color: var(--accent); animation: spin 0.8s linear infinite; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px 20px; margin-top: 12px; }
  h5 { margin: 0 0 4px; font: 650 10.5px/1 var(--font); text-transform: uppercase; letter-spacing: 0.07em; color: var(--muted); }
  .check { display: grid; grid-template-columns: 20px minmax(0, 1fr); gap: 7px; padding: 5px 0; font-size: 13px; }
  .ti { width: 18px; height: 18px; border-radius: 50%; display: grid; place-items: center; font-size: 10.5px; font-weight: 800; margin-top: 1px; }
  .ok .ti { background: var(--good-soft); color: var(--good); }
  .fail .ti { background: var(--bad-soft); color: var(--bad); }
  .warn .ti { background: var(--warn-soft); color: var(--warn); }
  .fix { color: var(--bad); font-weight: 600; margin-top: 2px; }
</style>
