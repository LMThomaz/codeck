<script lang="ts">
  let { checked = $bindable(false), onchange = undefined, label = "", hint = "", disabled = false }:
    { checked?: boolean; onchange?: (v: boolean) => void; label?: string; hint?: string; disabled?: boolean } = $props();
</script>

<label class="sw" class:disabled>
  <input type="checkbox" bind:checked {disabled} onchange={() => onchange?.(checked)} />
  <span class="track"><span class="knob"></span></span>
  {#if label}<span class="txt"><span>{label}</span>{#if hint}<small>{hint}</small>{/if}</span>{/if}
</label>

<style>
  .sw { display: inline-flex; align-items: flex-start; gap: 10px; cursor: pointer; user-select: none; }
  .disabled { opacity: 0.5; cursor: not-allowed; }
  input { position: absolute; opacity: 0; pointer-events: none; }
  .track { width: 34px; height: 20px; border-radius: 99px; background: var(--surface-3); border: 1px solid var(--line-2); position: relative; flex-shrink: 0;
    transition: background var(--t) var(--ease), border-color var(--t) var(--ease); margin-top: 1px; }
  .knob { position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: 50%; background: #fff; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.35);
    transition: transform var(--t) var(--spring); }
  input:checked + .track { background: var(--good); border-color: transparent; }
  input:checked + .track .knob { transform: translateX(14px); }
  input:focus-visible + .track { box-shadow: var(--ring); }
  .txt { display: grid; gap: 1px; font-size: 13px; }
  small { color: var(--muted); font-size: 12px; }
</style>
