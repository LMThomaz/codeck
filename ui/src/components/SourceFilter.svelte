<script lang="ts">
  // Filtro de origem: organização do Azure ou dono no GitHub (com o ícone da plataforma).
  import { store } from "../lib/store.svelte";
  let { value = $bindable(""), items = [] }: { value?: string; items?: { org: string; provider: string }[] } = $props();
  const options = $derived.by(() => {
    const seen = new Map<string, string>();
    for (const i of items) if (!seen.has(i.org)) seen.set(i.org, i.provider);
    for (const o of store.s?.orgs || []) if (!seen.has(o)) seen.set(o, "azure");
    return [...seen.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  });
</script>

<select class="select" style="width:auto;min-width:170px" bind:value>
  <option value="">Todas as origens</option>
  {#each options as [org, prov] (org)}<option value={org}>{prov === "github" ? "GitHub · " : "Azure · "}{org}</option>{/each}
</select>
