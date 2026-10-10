<script lang="ts">
  let { rows = 6, avatar = true, kpis = 0 }: { rows?: number; avatar?: boolean; kpis?: number } = $props();
</script>

{#if kpis}
  <div class="kpis">
    {#each Array(kpis) as _, i (i)}<div class="kpi"><i class="shim" style="width:60%;height:10px"></i><i class="shim" style="width:35%;height:20px"></i><i class="shim" style="width:50%;height:9px"></i></div>{/each}
  </div>
{/if}
<div class="list">
  {#each Array(rows) as _, i (i)}
    <div class="r">
      {#if avatar}<i class="shim av"></i>{/if}
      <div class="lines"><i class="shim" style="width:{72 - ((i * 9) % 30)}%;height:13px"></i><i class="shim" style="width:{44 + ((i * 13) % 30)}%;height:10px"></i></div>
      <i class="shim" style="width:90px;height:22px"></i>
    </div>
  {/each}
</div>

<style>
  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 14px; }
  .kpi { display: grid; gap: 8px; padding: 12px 14px; border: 1px solid var(--line); border-radius: var(--r); background: var(--surface); }
  .r { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 14px 16px; border-top: 1px solid var(--line); }
  .r:first-child { border-top: 0; }
  .av { width: 30px; height: 30px; border-radius: 50%; }
  .lines { display: grid; gap: 8px; }
</style>
