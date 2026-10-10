# Commitdeck

> Antes se chamava **PR Pilot**. Quem tem o PR Pilot instalado recebe o Commitdeck pela atualização automática:
> contas, regras e histórico vêm junto, e os PATs e tokens continuam no mesmo cofre.

Central de versionamento de desktop (**macOS e Windows**) para **GitHub e Azure DevOps**. Junta numa fila só as
PRs, builds/Actions, deploys, issues e work items de várias contas e organizações, com regras de automação, e traz
um cliente Git completo: catálogos de repositórios, graph de commits, stage/commit, branches, stash, cherry-pick,
criação de PR. Você não precisa mais trocar de conta no navegador nem de ferramenta.

## Instalar

| | |
|---|---|
| **Windows** | baixe `Commitdeck-<versão>-setup.exe` em `https://thomsoft.com.br/downloads/commitdeck/latest.json` (campo `windows.url`) e rode. Instala no seu perfil, sem administrador. |
| **macOS** | baixe o `.dmg` (campo `macos.url` do mesmo `latest.json`) e arraste o Commitdeck para Aplicativos. |

Os mesmos instaladores ficam em [Releases](https://github.com/LMThomaz/commitdeck/releases/latest).

Depois de instalado, o app **se atualiza sozinho**:
- Ele consulta o `latest.json`, mostra um aviso e o botão **Atualizar agora**.
- Antes de instalar, confere o SHA-256 do instalador baixado.
- Quando há uma versão obrigatória (`required`), ele bloqueia o uso até atualizar.

O app não é assinado por certificado comercial (decisão da ThomSoft):
- **Windows:** o SmartScreen pode avisar na primeira instalação. Clique em *Mais informações → Executar assim mesmo*.
- **macOS:** na primeira abertura, use *clique direito → Abrir*. As atualizações seguintes não pedem nada.

## O que faz

**Revisão e entrega**
- **Fila**: tudo que espera você — PRs aguardando o seu voto (conflito e build em destaque), deploys aguardando
  aprovação (releases clássicas, environments YAML e *pending deployments* do GitHub) e pipelines travados em
  *"needs permission to access a resource"*.
- **Pull requests** dos dois provedores: para revisar, minhas (com o que as trava), todas e arquivadas. Aprovar,
  pedir mudança e comentar sem sair do app.
- **Builds e Actions**: execuções recentes com filtros; no que falhou, o job, as anotações e o trecho do log em volta
  do erro. *Tentar de novo* (só o que falhou), *Rodar de novo* e *Cancelar*.
- **Issues e tarefas**: issues do GitHub e work items do Azure atribuídos a você ou que mencionam você.
- **Automação**: regras por prioridade — PR (criador → branch → aprovar/arquivar/notificar), deploy (pipeline →
  estágio → branch, com *"só se eu já aprovei a PR de origem"*) e permissão (pipeline → recurso), com prévia do que
  cada regra pegaria.
- **Análise** (lead time, aprovações, criadores, repositórios) e **Histórico** de tudo que você e o piloto fizeram.

**Repositórios e Git**
- **Catálogos**: nascem sozinhos ao conectar uma conta (um por projeto do Azure; no GitHub, o pessoal e um por
  organização) e ficam agrupados pela conta, com o logo do provedor, recolhíveis no painel e na barra lateral. Também dá
  para criar os seus. Filtre por clonado/não clonado e clone um ou todos de uma vez; clones que já existem na pasta
  são reconhecidos sozinhos.
- **Favoritos e tags**: favorite repositórios de qualquer conta (GitHub e Azure misturados) — pela estrela ou buscando
  em todas as contas — e organize com tags livres ("Open-Source", "Sustentação"…). Cada tag vira uma coleção; tag nova
  é criada digitando no próprio seletor.
- **Limpar repositório local** (manda para a Lixeira) — desabilitado quando há algo não commitado, stash, operação
  em andamento ou commit que não subiu.
- **Repositório**: graph de commits no estilo GitKraken (faixas coloridas, avatar do autor, branches e tags),
  alterações com diff, stage/unstage/descartar, commit/amend, pull/push/fetch, branches locais e remotas, merge,
  cherry-pick, revert, reset, stash, tags e **Criar PR** direto para o GitHub ou o Azure.
- Abrir no **VS Code/Cursor/Rider**, no **Finder/Explorer**, no terminal ou no navegador.
- **⌘K / Ctrl+K**: paleta de comandos para ir a qualquer tela, repositório ou ação.

**No sistema**
- **Notificações nativas** (Central de Notificações no Mac, bandeja no Windows): clicar abre o item.
- **Contador** de pendências no Dock e na barra de menus (Mac) ou na bandeja e na barra de tarefas (Windows).

## Contas

| Provedor | Como conectar | O que usa |
|---|---|---|
| **Azure DevOps** | PAT por organização (Configurações → Azure DevOps), com teste de cada permissão | PRs, builds, releases, environments, work items, repositórios |
| **GitHub** | *Entrar com GitHub* (device flow), o login do `gh` CLI ou um token | contas pessoais, organizações e repositórios de terceiros a que o perfil tem acesso |

O *Entrar com GitHub* usa o OAuth App **Commitdeck** (device flow), cujo client id está em `backend/pilot/github.py`
(`GITHUB_CLIENT_ID`). Ele é público: o device flow não usa client secret. Quem distribuir outro build pode trocá-lo
pela variável `COMMITDECK_GITHUB_CLIENT_ID` ou por `githubClientId` no `config.json`.

O Git local usa as mesmas credenciais (por variável de ambiente, nunca na linha de comando) para clonar, buscar e
enviar por HTTPS; remotos SSH usam as suas chaves.

## Segurança

- **O PAT nunca fica em texto.**
  - No macOS vai para o **Keychain**. A gravação é feita pelo stdin do `security`, então ele não aparece na lista de processos.
  - No Windows é cifrado com **DPAPI**: só a sua conta do Windows decifra.
  - O `config.json` guarda apenas a referência, e a tela nunca recebe o PAT de volta. Tokens do GitHub seguem o mesmo caminho.
- O backend atende só em `127.0.0.1:47821` e exige uma **chave nova a cada execução**, que só o app conhece. Outros programas da máquina não leem a fila nem agem por você.
- O backend encerra junto com o app (watchdog do processo-pai; no Windows também um Job Object).
- Dados por usuário, fora do repositório:
  - macOS: `~/Library/Application Support/Commitdeck`
  - Windows: `%APPDATA%\Commitdeck`

## Como é feito

```
backend/        server.py + pacote pilot/ (Python, só biblioteca padrão) — igual nas duas plataformas
  pilot/        http (rotas) · engine (leitura periódica) · azure · github · git · catalogs · rules · secrets · update
  static/       a interface compilada (gerada, não versionada)
ui/             interface em Svelte 5 + Vite + TypeScript (npm run build → backend/static)
brand/          make-logo.py gera logo.svg e icon.svg; make-icons.sh gera .icns e .ico
macos/          Commitdeck.swift — janela nativa (AppKit + WebKit), Dock, barra de menus, notificações, troca do .app
windows/        Commitdeck (C# .NET 8, WinForms + WebView2) — janela, bandeja, notificações, atualização pelo ThomSoft Setup
scripts/        build-macos.sh · release-macos.sh · set-required.sh
.github/        release-windows.yml — gera, testa e publica o instalador do Windows
VERSION         x.y.z+N — a versão das duas plataformas
```

O app nativo sobe o backend escondido e mostra a tela dele. Não é Electron: o macOS usa o WebKit do sistema e o
Windows usa o WebView2 (Edge). O instalador do Windows leva um Python embutido (com hash fixo); no Mac o app usa o
`python3` das Command Line Tools. O Git é o da máquina (`git` no PATH).

**Novo provedor** (GitLab, Bitbucket…): um módulo em `backend/pilot/` com a mesma forma de `github.py` — listar
repositórios, PRs, execuções e issues devolvendo itens com `provider` e `key` — registrado em `engine.py`, mais o
reconhecimento do remoto em `git.parse_remote`. A interface já trata os itens pelo `provider`.

## Desenvolver

No VS Code ou no Cursor, dê ▶ em **Commitdeck (dev, macOS)**, **Commitdeck (dev, Windows)** ou
**Commitdeck (dev, interface no navegador)** — esta última sobe o Vite (porta `47823`, recarrega ao salvar).

- O backend sobe em depuração (porta `47822`, dados em `data-sandbox/`) e o app nativo se conecta a ele.
- `cd ui && npm run check` confere os tipos; `npm run build` gera `backend/static/`.
- Não toca no app instalado nem nas suas contas reais.
- **Instalar o app no meu Mac** (`scripts/build-macos.sh`) compila o app universal (Apple Silicon e Intel) e o instala em `/Applications`.

Requisitos:
- **macOS:** Command Line Tools (`xcode-select --install`) e Node.js 20+.
- **Windows:** .NET 8 SDK, Python 3 e Node.js 20+.

## Publicar uma versão

1. Suba o `+N` do arquivo `VERSION`, faça commit e push na `main`.
2. **Windows:** o GitHub Actions gera o instalador e testa: instala sem janela, abre o app, atualiza por cima e desinstala. Depois publica no site da ThomSoft (`downloads/commitdeck/`) e no GitHub Releases. Ele só roda quando o `VERSION` muda, para não gastar a cota.
3. **macOS:** no Mac, rode `scripts/release-macos.sh`. Ele gera o `.dmg` e publica no mesmo lugar.
4. Cada plataforma atualiza só a própria parte do `latest.json`. Para obrigar quem está abaixo do build N a atualizar, rode `scripts/set-required.sh N`, só depois de N estar publicado nas duas plataformas.

As credenciais do FTP do site são as mesmas do Chefinho.
- **Mac:** `~/.config/thomsoft/downloads.env` com a senha no Keychain (`thomsoft-downloads-ftp`).
- **GitHub:** secrets `DOWNLOADS_FTP_SERVER`, `DOWNLOADS_FTP_USER` e `DOWNLOADS_FTP_PASSWORD`.

## Licença

MIT — veja [LICENSE](LICENSE).
