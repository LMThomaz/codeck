import { get } from "./api";
import type { Catalog, LocalRepo } from "./types";

// Repositórios locais e catálogos: carregados à parte do /api/state (o status de cada repo custa um `git status`).
class Repos {
  local = $state<LocalRepo[]>([]);
  catalogs = $state<Catalog[]>([]);
  loaded = $state(false);
  private inflight: Promise<void> | null = null;

  get pinned() { return this.local.filter(r => r.pinned); }
  byId(id: string) { return this.local.find(r => r.id === id); }

  load(withStatus = true): Promise<void> {
    if (this.inflight) return this.inflight;
    this.inflight = Promise.all([get<{ repos: LocalRepo[] }>("repos", { status: withStatus ? 1 : 0 }), get<{ catalogs: Catalog[] }>("catalogs")])
      .then(([r, c]) => { this.local = r.repos; this.catalogs = c.catalogs; this.loaded = true; })
      .finally(() => (this.inflight = null));
    return this.inflight;
  }
}

export const repos = new Repos();
