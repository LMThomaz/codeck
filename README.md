# PR Pilot

App de desktop (**macOS e Windows**) para o dia a dia de dev no Azure DevOps. Junta numa fila só as PRs, os builds,
as aprovações de release e as permissões de pipeline de várias organizações e contas, com regras de automação.
Você não precisa mais trocar de conta no navegador.

## Instalar

| | |
|---|---|
| **Windows** | baixe `PR-Pilot-<versão>-setup.exe` em `https://thomsoft.com.br/downloads/pr-pilot/latest.json` (campo `windows.url`) e rode. Instala no seu perfil, sem administrador. |
| **macOS** | baixe o `.dmg` (campo `macos.url` do mesmo `latest.json`) e arraste o PR Pilot para Aplicativos. |

Depois de instalado, o app **se atualiza sozinho**:
- Ele consulta o `latest.json`, mostra um aviso e o botão **Atualizar agora**.
- Antes de instalar, confere o SHA-256 do instalador baixado.
- Quando há uma versão obrigatória (`required`), ele bloqueia o uso até atualizar.

O app não é assinado por certificado comercial (decisão da ThomSoft):
- **Windows:** o SmartScreen pode avisar na primeira instalação. Clique em *Mais informações → Executar assim mesmo*.
- **macOS:** na primeira abertura, use *clique direito → Abrir*. As atualizações seguintes não pedem nada.

## O que faz

- **Fila**: tudo que espera você.
  - PRs aguardando o seu voto, com conflito e build em destaque.
  - Releases aguardando aprovação.
  - Pipelines travados em *"needs permission to access a resource"*.
- **Minhas PRs**: o que trava as suas PRs (conflito, build vermelho, voto contra, revisor obrigatório). Avisa quando algo acontece.
- **Builds**: execuções recentes com filtro (rodando, falharam, branch protegida, só os meus).
  - No build que falhou, mostra a task, o erro e as últimas linhas do log.
  - Botões *Tentar de novo* (só o que falhou), *Rodar de novo* e *Cancelar*.
- **Releases**: o que está parado e as releases recentes, com o status de cada estágio.
- **Automação**: regras de prioridade.
  - PR: criador → branch → aprovar, arquivar ou notificar.
  - Release: pipeline → estágio → branch, com *"só se eu já aprovei a PR de origem"*.
  - Permissão: pipeline → recurso.
  - Cada regra mostra uma prévia do que ela pegaria.
- **Análise**, **Histórico** e **Ambiente** (contas e PATs, com teste de conexão).
- **Notificações nativas** (Central de Notificações no Mac, bandeja no Windows): clicar abre o item.
- **Contador** de pendências no Dock e na barra de menus (Mac) ou na bandeja e na barra de tarefas (Windows).

## Segurança

- **O PAT nunca fica em texto.**
  - No macOS vai para o **Keychain**. A gravação é feita pelo stdin do `security`, então ele não aparece na lista de processos.
  - No Windows é cifrado com **DPAPI**: só a sua conta do Windows decifra.
  - O `config.json` guarda apenas a referência, e a tela nunca recebe o PAT de volta.
- O backend atende só em `127.0.0.1:47821` e exige uma **chave nova a cada execução**, que só o app conhece. Outros programas da máquina não leem a fila nem agem por você.
- O backend encerra junto com o app (watchdog do processo-pai; no Windows também um Job Object).
- Dados por usuário, fora do repositório:
  - macOS: `~/Library/Application Support/PR Pilot`
  - Windows: `%APPDATA%\PR Pilot`

## Como é feito

```
backend/   server.py (Python, só biblioteca padrão) + index.html — a lógica e a tela, iguais nas duas plataformas
brand/     make-logo.py gera logo.svg (marca: grafo de commit + merge formando o "P") e icon.svg; make-icons.sh gera .icns e .ico
macos/     PRPilot.swift — janela nativa (AppKit + WebKit), Dock, barra de menus, notificações, troca do .app
windows/   PRPilot (C# .NET 8, WinForms + WebView2) — janela, bandeja, notificações, atualização pelo ThomSoft Setup
scripts/   build-macos.sh · release-macos.sh · set-required.sh
.github/   release-windows.yml — gera, testa e publica o instalador do Windows
VERSION    x.y.z+N — a versão das duas plataformas
```

O app nativo sobe o backend escondido e mostra a tela dele. Não é Electron: o macOS usa o WebKit do sistema e o
Windows usa o WebView2 (Edge). O instalador do Windows leva um Python embutido (com hash fixo); no Mac o app usa o
`python3` das Command Line Tools.

## Desenvolver

No VS Code ou no Cursor, dê ▶ em **PR Pilot (dev, macOS)** ou **PR Pilot (dev, Windows)**.

- O backend sobe em depuração (porta `47822`, dados em `data-sandbox/`) e o app nativo se conecta a ele.
- Não toca no app instalado nem nas suas contas reais.
- **Instalar o app no meu Mac** (`scripts/build-macos.sh`) compila o app universal (Apple Silicon e Intel) e o instala em `/Applications`.

Requisitos:
- **macOS:** Command Line Tools (`xcode-select --install`).
- **Windows:** .NET 8 SDK e Python 3.

## Publicar uma versão

1. Suba o `+N` do arquivo `VERSION`, faça commit e push na `main`.
2. **Windows:** o GitHub Actions gera o instalador e testa: instala sem janela, abre o app, atualiza por cima e desinstala. Depois publica no site da ThomSoft (`downloads/pr-pilot/`) e no GitHub Releases. Ele só roda quando o `VERSION` muda, para não gastar a cota.
3. **macOS:** no Mac, rode `scripts/release-macos.sh`. Ele gera o `.dmg` e publica no mesmo lugar.
4. Cada plataforma atualiza só a própria parte do `latest.json`. Para obrigar quem está abaixo do build N a atualizar, rode `scripts/set-required.sh N`, só depois de N estar publicado nas duas plataformas.

As credenciais do FTP do site são as mesmas do Chefinho.
- **Mac:** `~/.config/thomsoft/downloads.env` com a senha no Keychain (`thomsoft-downloads-ftp`).
- **GitHub:** secrets `DOWNLOADS_FTP_SERVER`, `DOWNLOADS_FTP_USER` e `DOWNLOADS_FTP_PASSWORD`.
