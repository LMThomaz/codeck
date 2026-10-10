import { get, post } from "./api";
import type { Catalog, FavRepo, LocalRepo, RemoteRepo, Tag } from "./types";

// Repositórios locais, catálogos e favoritos: carregados à parte do /api/state (o status de cada repo custa um `git status`).
class Repos {
  local = $state<LocalRepo[]>([]);
  catalogs = $state<Catalog[]>([]);
  favorites = $state<FavRepo[]>([]);
  tags = $state<Tag[]>([]);
  loaded = $state(false);
  private inflight: Promise<void> | null = null;

  get pinned() { return this.local.filter(r => r.pinned); }
  byId(id: string) { return this.local.find(r => r.id === id); }

  load(withStatus = true): Promise<void> {
    if (this.inflight) return this.inflight;
    this.inflight = Promise.all([get<{ repos: LocalRepo[] }>("repos", { status: withStatus ? 1 : 0 }), get<{ catalogs: Catalog[] }>("catalogs"),
      get<{ repos: FavRepo[]; tags: Tag[] }>("library")])
      .then(([r, c, l]) => { this.local = r.repos; this.catalogs = c.catalogs; this.favorites = l.repos; this.tags = l.tags; this.loaded = true; })
      .finally(() => (this.inflight = null));
    return this.inflight;
  }
  async loadLibrary() {
    const l = await get<{ repos: FavRepo[]; tags: Tag[] }>("library");
    this.favorites = l.repos;
    this.tags = l.tags;
  }

  // ---------------------------------------------------------------- favoritos
  /** Chave do favorito: a do remoto normalizado (casa catálogo, busca e clone local); sem remoto, "local:<id>". */
  keyOf(r: RemoteRepo | LocalRepo | FavRepo): string {
    if ("tags" in r && r.key) return r.key;
    if ("remoteKey" in r && r.remoteKey) return r.remoteKey;
    if ("path" in r) return "local:" + r.id;
    return (r as RemoteRepo).key;
  }
  fav(key: string) { return this.favorites.find(f => f.key === key); }
  tag(name: string) { return this.tags.find(t => t.name === name); }

  async setFavorite(r: RemoteRepo | LocalRepo | FavRepo, on: boolean, tags: string[] = []) {
    const key = this.keyOf(r);
    // otimista: a estrela acende na hora; a resposta do backend confirma (ou desfaz)
    const before = this.favorites;
    if (!on) this.favorites = this.favorites.filter(f => f.key !== key);
    else if (!this.fav(key)) this.favorites = [...this.favorites, { ...(r as any), key, tags, cloned: !!(r as any).cloned || "path" in r, local: (r as any).local ?? null } as FavRepo];
    try {
      const snap = "path" in r ? { key: r.remoteKey ? undefined : key, remoteKey: r.remoteKey || undefined, provider: r.provider, name: r.name,
        fullName: r.slug || r.name, remoteUrl: r.remoteUrl, webUrl: r.webUrl, owner: r.slug?.split("/").slice(0, -1).join("/") } : r;
      await post("library/favorite", { repo: snap, on, tags });
      await this.loadLibrary();
    } catch (e) { this.favorites = before; throw e; }
  }

  async setTags(key: string, tags: string[]) {
    const f = this.fav(key);
    if (f) f.tags = tags;   // otimista
    try { await post("library/tags", { key, tags }); }
    finally { await this.loadLibrary(); }
  }
}

export const repos = new Repos();
