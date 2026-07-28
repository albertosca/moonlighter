> **[Read in English](README.md)**

# moonlighter

Pipeline de candidatura a vagas com IA. Escaneia portais de emprego, avalia o fit do candidato via LLM e automatiza candidaturas via browser — tudo orquestrado pelo Claude através de um servidor [Model Context Protocol](https://modelcontextprotocol.io) (MCP).

## Como funciona

1. **Scan** — busca vagas no Greenhouse, Lever, Ashby, Recruitee, Workable e SmartRecruiters para a lista de empresas que você configura, além de portais remote-first opcionais (RemoteOK, Remotive, WeWorkRemotely, HN Who's Hiring) e Gupy, ambos desativados por padrão (config-gated). O scan/Easy Apply do LinkedIn está disponível como uma extensão separada, distribuída de forma privada — veja [Extensões (adicionando um novo ATS)](#extensões-adicionando-um-novo-ats) abaixo.
2. **Avaliação** — pontua cada vaga em relação ao seu perfil via LLM; vagas abaixo do limiar são arquivadas automaticamente.
3. **Candidatura** — preenche e envia formulários de candidatura num browser real (Playwright), com respostas geradas pelo LLM sob medida para cada vaga.
4. **Monitoramento** — monitora sua caixa do Gmail em busca de convites para entrevista e atualiza o status do pipeline.

Todas as etapas são expostas como ferramentas MCP e orquestradas pelo Claude numa conversa.

## Arquitetura

Um [workspace uv](https://docs.astral.sh/uv/concepts/workspaces/) com 5 namespace packages (`moonlighter.*`), organizados por feature:

| Package | Namespace | Propósito |
|---------|-----------|-----------|
| `moonlighter-core` | `moonlighter.core` | DB (Peewee/SQLite), config, browser driver, cliente LLM |
| `moonlighter-scan` | `moonlighter.discovery` | Scrapers de ATS e scoring de vagas via LLM |
| `moonlighter-apply` | `moonlighter.application` | Preenchedor de formulários, gerador de respostas, work-auth |
| `moonlighter-email` | `moonlighter.tracking` | Sincronização com Gmail e classificação de estágios de entrevista |
| `moonlighter` | `moonlighter.server` | Servidor FastMCP — conecta todos os pacotes |

## Requisitos

- [uv](https://docs.astral.sh/uv/) — baixa o Python 3.14 pra você; não precisa instalar separado
- Chrome, Chromium ou Brave (o moonlighter dirige um browser de verdade pra suas sessões logadas funcionarem)
- [Claude Code CLI](https://claude.ai/code) — ou `ANTHROPIC_API_KEY` para `llm_backend: api`
- Credenciais OAuth do Gmail (opcional — só para rastreamento de e-mails)

## Instalação

### Opção A — plugin do Claude Code (recomendado)

```
/plugin marketplace add albertosca/moonlighter
/plugin install moonlighter@moonlighter
```

O primeiro comando registra o marketplace; o segundo instala o plugin a partir dele.

Depois rode o assistente de configuração:

```bash
uvx moonlighter init
```

### Opção B — qualquer cliente MCP

```bash
uvx moonlighter init
```

Depois registre o servidor MCP:

```bash
claude mcp add-json --scope user moonlighter '{"command":"uvx","args":["moonlighter"]}'
```

Usa outro cliente MCP? Registre o mesmo comando e argumentos (`uvx` / `["moonlighter"]`) com o
mecanismo de registro do seu próprio cliente — o comando `claude mcp add-json` acima é específico
da CLI do Claude Code.

O assistente grava o `config.yaml` no `MOONLIGHTER_HOME` (padrão: `~/.moonlighter/`). Dois arquivos
ainda precisam da sua entrada:

| Arquivo | O que colocar |
|---------|----------------|
| `profile.yaml` | Sua experiência, skills e `criteria` (os filtros hard e soft que guiam o scoring) |
| `company_list.yaml` | As empresas a escanear e qual ATS cada uma usa |

Comece a partir de [`profile.example.yaml`](https://raw.githubusercontent.com/albertosca/moonlighter/main/profile.example.yaml) e [`company_list.example.yaml`](https://raw.githubusercontent.com/albertosca/moonlighter/main/company_list.example.yaml).

### Rastreamento por Gmail (opcional)

1. Crie um projeto no [Google Cloud Console](https://console.cloud.google.com), ative a API do
   Gmail e baixe as credenciais OAuth como `client.json`.
2. Coloque o arquivo em `~/.moonlighter/gmail-client.json`.
3. Na primeira chamada a `setup_email`, um browser abrirá para autorização e o token será salvo.

### Desenvolvendo no moonlighter

Pra trabalhar no código em vez de só usar a ferramenta, veja [CONTRIBUTING.md](CONTRIBUTING.md).

## Ferramentas MCP

| Ferramenta | Descrição |
|------------|-----------|
| `scan_and_evaluate` | Busca e pontua vagas de todas as fontes ATS configuradas |
| `list_jobs` | Lista vagas por status (`new`, `scored`, `applied`, `archived`, …) |
| `get_job` | Exibe detalhes completos e histórico de pipeline de uma vaga |
| `add_job` | Adiciona uma vaga manualmente por URL |
| `apply_jobs` | Candidata-se a uma lista de IDs de vagas em lote |
| `fill_application` | Preenche um formulário e pausa para revisão antes de enviar |
| `submit_application` | Envia uma candidatura já preenchida |
| `confirm_apply` | Preenche e envia em uma única etapa atômica |
| `retry_apply` | Retenta uma candidatura com falha |
| `login` | Abre o browser e persiste a sessão pra uma plataforma que precisa disso (só disponível se alguma extensão a registrar — veja abaixo) |
| `update_status` | Move uma vaga manualmente pelo pipeline |
| `setup_email` | Autoriza OAuth do Gmail |
| `sync_email_responses` | Busca respostas recentes e classifica estágios de entrevista |
| `get_pipeline` | Resumo completo do pipeline |

## Extensões (adicionando um novo ATS)

Toda integração de ATS que você vê acima (Greenhouse, Lever, Ashby, Recruitee, Workable, SmartRecruiters,
Gupy) é parte normal deste repositório — mas o moonlighter também suporta **extensões**: pacotes Python
separados, instalados de forma independente, que registram um novo scanner ou applier sem precisar dar
fork ou modificar este repositório de jeito nenhum. É assim que o suporte ao LinkedIn é distribuído — não
porque o mecanismo seja específico do LinkedIn, mas porque os próprios Termos de Uso do LinkedIn proíbem
automação de forma explícita e inequívoca (veja [DISCLAIMER.md](DISCLAIMER.md)), então essa integração
específica é distribuída como uma extensão opcional em vez de código embutido que qualquer um que clonar
este repo já ganha por padrão.

### Como funciona

Uma extensão é um pacote Python normal que:

1. Depende dos pacotes `moonlighter-*` que precisar (tipicamente `moonlighter-core` mais qualquer um de
   `moonlighter-scan`/`moonlighter-apply` que ele estenda), fixado numa tag lançada deste repositório.
2. Traz seus próprios módulos implementando uma subclasse de `BaseScanner` (veja
   `packages/scan/moonlighter/discovery/sources/base.py`) e/ou de `BaseApplier` (veja
   `packages/apply/moonlighter/application/appliers/base.py`).
3. Se declara via `entry_points` no próprio `pyproject.toml` — nenhum código deste repositório importa ou
   cita a extensão em nenhum momento:

```toml
[project.entry-points."moonlighter.scanners"]
minha_plataforma = "meu_pacote.meu_modulo:MeuScanner"

[project.entry-points."moonlighter.appliers"]
minha_plataforma = "meu_pacote.meu_modulo:MeuApplier"

# Opcional: uma plataforma cujo applier precisa de login de browser salvo (ferramenta MCP `login`)
[project.entry-points."moonlighter.login_urls"]
minha_plataforma = "meu_pacote.meu_modulo:URL_LOGIN_MINHA_PLATAFORMA"

# Opcional: checagem de vaga obsoleta via browser pra uma fonte sem API de listagem
[project.entry-points."moonlighter.staleness_checkers"]
minha_plataforma = "meu_pacote.meu_modulo:check_staleness"
```

4. Precisa estar presente no **mesmo** ambiente Python de onde o moonlighter roda, pra que seus entry
   points sejam descobertos em tempo de execução. Se você instalou o moonlighter via `uvx moonlighter`,
   não existe um ambiente persistente pra adicionar um pacote — use uma das opções:
   - `uvx --with meu-pacote-de-extensao moonlighter` — efêmero, por invocação
   - `uv tool install moonlighter --with meu-pacote-de-extensao` — instalação persistente da ferramenta
   Se você está desenvolvendo direto neste repositório, `uv add --editable`/`pip install` o pacote da
   sua extensão no mesmo ambiente continua funcionando como antes. Em tempo de execução,
   `moonlighter.core.plugins.discover_entry_points`/`discover_entry_points_by_name` enumeram o que estiver
   registrado em cada grupo — um ambiente sem nenhuma extensão instalada se comporta exatamente como hoje
   (lista/dict vazio, nada quebra).

Como o pacote de nível raiz `moonlighter` é um [namespace package PEP 420](https://peps.python.org/pep-0420/)
(sem `__init__.py` nesse nível), uma extensão pode até trazer seu próprio subpacote de nível raiz (ex:
`moonlighter/minha_extensao/`) que coexiste com `moonlighter.core`/`moonlighter.discovery`/etc. — só não
coloque arquivos *dentro* de um subpacote já existente como `moonlighter/discovery/sources/` ou
`moonlighter/application/appliers/`, já que esses são pacotes regulares (não-namespace) pertencentes
inteiramente às distribuições deste repositório, e uma segunda distribuição escrevendo no mesmo caminho
colide silenciosamente na instalação. Dê à sua extensão o próprio diretório de nível raiz.

### Exemplo real

A extensão privada `moonlighter-linkedin` (não publicada, pelo motivo acima) segue exatamente esse padrão —
o `LinkedInScanner`/`LinkedInApplier` dela vivem no próprio pacote `moonlighter/linkedin_ext/`, registrados
via os quatro grupos de entry_points acima. Se você for construir sua própria extensão, essa é a forma de
referência a copiar.

## Licença

AGPL-3.0 — veja [LICENSE](LICENSE).  
Veja [DISCLAIMER.md](DISCLAIMER.md) para notas importantes sobre ToS, automação e uso do backend LLM.
Veja [PRIVACY.md](PRIVACY.md) (em inglês) para o que esta ferramenta armazena e pra onde vai.
