<script lang="ts">
  let { value = $bindable(), options }: { value: string; options: { value: string; icon: string; label: string; desc: string }[] } = $props();
</script>

<div class="acts">
  {#each options as o (o.value)}
    <button type="button" class="ac" class:on={value === o.value} onclick={() => (value = o.value)}>
      <span class="ai">{o.icon}</span><span><b>{o.label}</b><small>{o.desc}</small></span>
    </button>
  {/each}
</div>

<style>
  .acts { display: grid; gap: 8px; }
  .ac { display: flex; gap: 12px; align-items: flex-start; text-align: left; padding: 11px 13px; border-radius: 11px; border: 1px solid var(--line-2);
    background: var(--surface-2); color: var(--text); font: 13px var(--font); cursor: pointer; transition: border-color var(--t), background var(--t), transform var(--t-fast); }
  .ac:hover { border-color: var(--line-3); transform: translateY(-1px); }
  .ac.on { border-color: var(--accent); background: var(--accent-soft); box-shadow: 0 0 0 1px var(--accent); }
  .ai { font-size: 18px; line-height: 1.2; }
  small { display: block; color: var(--muted); font-size: 12px; margin-top: 2px; }
</style>
