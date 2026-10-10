<script lang="ts">
  // Estrela de favorito: acende na hora (otimista) com um "pop"; favoritos podem vir de qualquer conta.
  import { Star } from "@lucide/svelte";
  import { repos } from "../../lib/repos.svelte";
  import type { FavRepo, LocalRepo, RemoteRepo } from "../../lib/types";
  import { ui } from "../../lib/ui.svelte";

  let { repo, tags = [], size = 15 }: { repo: RemoteRepo | LocalRepo | FavRepo; tags?: string[]; size?: number } = $props();
  const on = $derived(!!repos.fav(repos.keyOf(repo)));
  let bump = $state(0);

  async function toggle(e: MouseEvent) {
    e.stopPropagation();
    bump++;
    try { await repos.setFavorite(repo, !on, tags); } catch (err) { ui.error(err); }
  }
</script>

<button class="star" class:on title={on ? "Tirar dos favoritos" : "Favoritar"} aria-pressed={on} onclick={toggle}>
  {#key bump}<span class="s"><Star {size} fill={on ? "currentColor" : "none"} /></span>{/key}
</button>

<style>
  .star { display: grid; place-items: center; width: 26px; height: 26px; border: 0; border-radius: 7px; background: none; color: var(--faint); cursor: pointer;
    transition: color var(--t), background var(--t); flex: none; }
  .star:hover { color: var(--warn); background: var(--warn-soft); }
  .star.on { color: var(--warn); }
  .s { display: grid; animation: star-pop 0.45s var(--spring); }
  @keyframes star-pop { 0% { transform: scale(0.6) rotate(-30deg); } 60% { transform: scale(1.25) rotate(8deg); } 100% { transform: none; } }
</style>
