<script lang="ts">
  import { onMount } from "svelte";
  import CommandPalette from "./components/CommandPalette.svelte";
  import DialogHost from "./components/DialogHost.svelte";
  import Sidebar from "./components/Sidebar.svelte";
  import Toaster from "./components/Toaster.svelte";
  import OfflineBanner from "./components/OfflineBanner.svelte";
  import TopProgress from "./components/TopProgress.svelte";
  import UpdateBanner from "./components/UpdateBanner.svelte";
  import { repos } from "./lib/repos.svelte";
  import { go, router } from "./lib/router.svelte";
  import { store } from "./lib/store.svelte";
  import Analytics from "./views/Analytics.svelte";
  import Automation from "./views/Automation.svelte";
  import Builds from "./views/Builds.svelte";
  import Deploys from "./views/Deploys.svelte";
  import History from "./views/History.svelte";
  import Inbox from "./views/Inbox.svelte";
  import Issues from "./views/Issues.svelte";
  import PullRequests from "./views/PullRequests.svelte";
  import RepoDetail from "./views/RepoDetail.svelte";
  import Repositories from "./views/Repositories.svelte";
  import Settings from "./views/Settings.svelte";

  const views: Record<string, any> = {
    inbox: Inbox, prs: PullRequests, builds: Builds, deploys: Deploys, issues: Issues, repos: Repositories, repo: RepoDetail,
    automation: Automation, analytics: Analytics, history: History, settings: Settings,
  };
  const View = $derived(views[router.view] || Inbox);

  // Notificação clicada no app nativo: "rota/chave" (formatos antigos continuam valendo).
  window.openTarget = (target: string) => {
    const [t, ...rest] = (target || "").split("/");
    const key = encodeURIComponent(rest.join("/"));
    const map: Record<string, string> = { fila: "/inbox/", minhas: "/prs/mine/", todas: "/prs/all/", builds: "/builds/", historico: "/history", deploys: "/deploys/" };
    go((map[t] ?? `/${t}/`) + (map[t] === "/history" ? "" : key));
  };

  onMount(() => {
    store.start();
    repos.load();
    const t = setInterval(() => { if (!store.hold) repos.load(); }, 30000);
    return () => clearInterval(t);
  });
  $effect(() => {
    // 1ª execução sem nenhuma conta: vai direto para Contas
    if (store.s && !store.s.configured && router.view !== "settings") go("/settings/accounts");
  });
</script>

<div class="shell">
  <Sidebar />
  <main>
    <TopProgress />
    <OfflineBanner />
    <UpdateBanner />
    <div class="page">
      {#key router.view}
        <View />
      {/key}
    </div>
  </main>
</div>

<CommandPalette />
<DialogHost />
<Toaster />

<style>
  .shell { display: flex; height: 100%; }
  main { flex: 1; min-width: 0; display: flex; flex-direction: column; height: 100%; }
  .page { flex: 1; min-height: 0; view-transition-name: page; }
</style>
