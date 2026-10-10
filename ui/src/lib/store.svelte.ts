import { get } from "./api";
import type { AppState, PR } from "./types";

// Estado global: o /api/state inteiro, relido a cada 15 s (mais rápido até chegar o 1º dado do Azure/GitHub).
class Store {
  s = $state<AppState | null>(null);
  error = $state<string | null>(null);
  /** contador de "não redesenhe agora" (menu aberto, diálogo, edição) */
  hold = $state(0);
  private timer: ReturnType<typeof setTimeout> | null = null;

  get ready() { return !!this.s; }
  get prsReady() { return !!this.s?.lastPoll; }
  get buildsReady() { return !!this.s?.lastBuildPoll; }
  get deploysReady() { return !!this.s?.lastDeployPoll; }

  /** PRs que esperam o MEU voto (no GitHub, só as que pediram minha revisão) */
  get inbox(): PR[] {
    return (this.s?.prs || []).filter(p => !p.archived && p.myVote === 0 && (p.provider !== "github" || p.reviewRequested));
  }
  get deploysForMe() { return (this.s?.deploys || []); }
  get open(): PR[] { return (this.s?.prs || []).filter(p => !p.archived); }
  get archived(): PR[] { return (this.s?.prs || []).filter(p => p.archived); }

  async load() {
    try {
      const s = await get<AppState>("state");
      this.s = s;
      this.error = null;
    } catch (e: any) {
      this.error = e.message || "backend fora do ar";
    }
  }

  start() {
    const tick = async () => {
      if (!this.hold) await this.load();
      const fast = !this.s || !this.s.lastPoll || !this.s.lastBuildPoll || !this.s.lastDeployPoll;
      this.timer = setTimeout(tick, fast ? 1500 : 15000);
    };
    tick();
  }

  refreshSoon(ms = 400) {
    setTimeout(() => this.load(), ms);
  }
}

export const store = new Store();
