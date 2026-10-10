# PR Pilot

Fila única do Azure DevOps para o dia a dia de dev: **PRs, releases e permissões de pipeline** de várias
organizações/contas numa tela só, com regras de automação. Não precisa ficar trocando de conta no navegador.

Roda **só na sua máquina** (Python 3, sem dependências), atende em `127.0.0.1:47821` e guarda tudo em `data/`,
que fica fora do git.

## O que faz

- **Fila**: tudo que espera você, junto.
  - PRs aguardando o seu voto, com conflito e build em destaque.
  - Releases aguardando aprovação (pré/pós-deploy clássico e aprovação de ambiente YAML).
  - Pipelines travados em *"needs permission to access a resource"*.
- **Releases**: o que está parado e as releases recentes, com o status de cada estágio.
- **Automação**: regras de prioridade.
  - PR: criador → branch → aprovar, arquivar ou notificar.
  - Release: pipeline → estágio → branch → aprovar ou notificar, com a opção *"só se eu já aprovei a PR de origem"*.
  - Permissão: pipeline → recurso → liberar ou notificar.
  - Cada regra mostra uma prévia do que ela pegaria, agora e no histórico.
- **Análise** e **Histórico** do que você e o piloto fizeram.
- **Ambiente**: cadastro das organizações e dos PATs, com botão de teste.

## Rodar

**VS Code / Cursor**: abra a pasta e dê ▶ em **PR Pilot** (Run and Debug). O navegador abre sozinho; na
primeira vez ele abre direto na tela **Ambiente** para você cadastrar suas organizações.

**Terminal**:

```bash
PR_PILOT_OPEN=1 python3 server.py
```

**Sempre ligado (macOS)**: o comando abaixo instala um serviço do usuário que sobe no login e reinicia se cair.

```bash
./install.sh             # instala/reinicia
./install.sh uninstall   # remove
```

> Com o serviço instalado, o ▶ avisa que a porta está em uso e só abre a tela. Para mexer no código ao mesmo
> tempo, use **PR Pilot (sandbox)**: porta `47822` e dados em `data-sandbox/`, sem tocar nos seus.

## Configurar contas

Na aba **⚙ Ambiente**, adicione uma linha por organização:

- **Nome**: aparece na tela.
- **Organização ou URL**: `minha-org` ou `https://dev.azure.com/minha-org`.
- **PAT**: o seu token naquela organização.

Clique em **Testar** e depois em **Salvar e conectar**.

Escopos do PAT (Custom defined):

| Escopo | Para quê |
|---|---|
| Code — Read & write | ler e votar nas PRs |
| Build — Read & execute | ver runs travados, cancelar |
| Release — Read, write, execute & manage | aprovar/rejeitar releases |
| escopo do recurso (ex.: Variable Groups — Read, create & manage) | liberar permissão de recurso (sua conta precisa ser admin dele) |

## Variáveis de ambiente

| Variável | Padrão | Uso |
|---|---|---|
| `PR_PILOT_PORT` | `47821` | porta local |
| `PR_PILOT_DATA` | `./data` | pasta dos dados (config, regras, histórico) |
| `PR_PILOT_OPEN` | — | `1` abre o navegador ao subir |

## Dados locais (`data/`, fora do git)

| Arquivo | Conteúdo |
|---|---|
| `config.json` | organizações + PATs (`chmod 600`) |
| `rules.json` | regras e ajustes |
| `archive.json` / `notified.json` | PRs arquivadas e itens já notificados |
| `activity.jsonl` | histórico de ações |
| `pr-pilot.log` | log do serviço |
