> **[Read in English](README.md)**

# moonlighter

[![PyPI](https://img.shields.io/pypi/v/moonlighter)](https://pypi.org/project/moonlighter/)
[![Python](https://img.shields.io/pypi/pyversions/moonlighter)](https://pypi.org/project/moonlighter/)
[![CI](https://github.com/albertosca/moonlighter/actions/workflows/ci.yml/badge.svg)](https://github.com/albertosca/moonlighter/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)

Pipeline de candidatura a vagas com IA. Escaneia portais de emprego, avalia o fit do candidato via LLM e compõe todas as respostas que um formulário de candidatura pede — tudo orquestrado pelo Claude através de um servidor [Model Context Protocol](https://modelcontextprotocol.io) (MCP). O moonlighter nunca abre um browser pra preencher ou enviar um formulário, e nunca envia uma candidatura em seu nome — veja [Como funciona](#como-funciona) abaixo e [DISCLAIMER.md](DISCLAIMER.md) (em inglês).

## Como funciona

1. **Scan** — busca vagas no Greenhouse, Lever, Ashby, Recruitee, Workable e SmartRecruiters para a lista de empresas que você configura, além de portais remote-first opcionais (RemoteOK, Remotive, WeWorkRemotely, HN Who's Hiring) e Gupy, ambos desativados por padrão (config-gated). O scan do LinkedIn está disponível como uma extensão separada, distribuída de forma privada — veja [Extensões (adicionando um novo scanner de ATS)](#extensões-adicionando-um-novo-scanner-de-ats) abaixo.
2. **Avaliação** — pontua cada vaga em relação ao seu perfil via LLM; vagas abaixo do limiar são arquivadas automaticamente.
3. **Preparo** — `prepare_application` lê as perguntas do formulário (via API do ATS quando ela publica isso, ex: Greenhouse/Recruitee) e compõe uma resposta pra cada pergunta que conseguir, com base no seu perfil. Ele renderiza uma única folha revisável — a candidatura inteira, não um screenshot de uma fração dela — com qualquer pergunta que não conseguiu responder sinalizada pra você. Quando nenhuma API publica as perguntas, `prepare_application_from_paste` faz o mesmo a partir de um texto que você mesmo copia da página. Nos dois casos, você é quem cola as respostas no formulário e envia — o moonlighter nunca toca o formulário nem clica em enviar.
4. **Monitoramento** — monitora sua caixa do Gmail em busca de convites para entrevista e atualiza o status do pipeline.

Todas as etapas são expostas como ferramentas MCP e orquestradas pelo Claude numa conversa.

## Arquitetura

Um [workspace uv](https://docs.astral.sh/uv/concepts/workspaces/) com 5 namespace packages (`moonlighter.*`), organizados por feature:

| Package | Namespace | Propósito |
|---------|-----------|-----------|
| `moonlighter-core` | `moonlighter.core` | DB (Peewee/SQLite), config, browser driver opcional (extra `[browser]`), cliente LLM |
| `moonlighter-scan` | `moonlighter.discovery` | Scrapers de ATS e scoring de vagas via LLM |
| `moonlighter-apply` | `moonlighter.application` | Compositor de respostas (perfil curado → respostas via LLM) e work-auth |
| `moonlighter-email` | `moonlighter.tracking` | Sincronização com Gmail e classificação de estágios de entrevista |
| `moonlighter` | `moonlighter.server` | Servidor FastMCP — conecta todos os pacotes |

## Requisitos

- [uv](https://docs.astral.sh/uv/) — baixa o Python 3.14 pra você; não precisa instalar separado
- Chrome, Chromium ou Brave — opcional, só necessário se você instalar uma extensão de scan baseada em browser (ex: scan do LinkedIn, veja [Extensões](#extensões-adicionando-um-novo-scanner-de-ats) abaixo). O produto base (escanear as APIs de ATS configuradas e preparar candidaturas) nunca abre um browser.
- Um backend de LLM, alternável no `config.yaml` a qualquer momento:
  - `llm_backend: cli` (padrão) — o [Claude Code CLI](https://claude.ai/code), cobrado na sua
    assinatura do Claude. Sem API key.
  - `llm_backend: api` — o SDK da Anthropic, cobrado em créditos de API. Exige `ANTHROPIC_API_KEY`
    no ambiente.
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

### Depois de qualquer uma das opções

O assistente grava o `config.yaml` no `MOONLIGHTER_HOME` (padrão: `~/.moonlighter/`). Dois arquivos
ainda precisam da sua entrada:

| Arquivo | O que colocar |
|---------|----------------|
| `profile.yaml` | Sua experiência, skills e `criteria` (os filtros hard e soft que guiam o scoring) |
| `company_list.yaml` | As empresas a escanear e qual ATS cada uma usa |

Comece a partir de [`profile.example.yaml`](https://raw.githubusercontent.com/albertosca/moonlighter/main/profile.example.yaml) e [`company_list.example.yaml`](https://raw.githubusercontent.com/albertosca/moonlighter/main/company_list.example.yaml).

O assistente grava um `config.yaml` mínimo; o [`config.example.yaml`](https://raw.githubusercontent.com/albertosca/moonlighter/main/config.example.yaml) documenta o resto da superfície de configuração, principalmente o bloco `cv` (só é necessário para usar um currículo diferente por empresa — por
padrão o `prepare_application` aponta o `cv.pdf` do `MOONLIGHTER_HOME` pra pergunta de upload de arquivo
do formulário, e avisa claramente se nenhum estiver configurado) e o bloco `email`. `profile.yaml`,
`company_list.yaml`, `config.yaml` e `cv.pdf` (seu currículo — o moonlighter só te diz o nome dele pra
você anexar, nunca faz o upload sozinho) ficam todos em `MOONLIGHTER_HOME` (padrão: `~/.moonlighter/`).

Depois de conectado, peça ao Claude para rodar `get_pipeline` — além do funil de candidaturas, ele reporta problemas de configuração como perfil, currículo ou navegador ausentes.

Reinicie o Claude Code, ou inicie uma nova sessão, para que as ferramentas do moonlighter apareçam.

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
| `prepare_application` | Compõe todas as respostas do formulário de candidatura de uma vaga numa única folha revisável, pra você colar e enviar |
| `prepare_application_from_paste` | O mesmo que `prepare_application`, pra um formulário cujas perguntas nenhuma API publica — passe o texto que você copiou da página |
| `update_status` | Move uma vaga manualmente pelo pipeline |
| `setup_email` | Autoriza OAuth do Gmail |
| `sync_email_responses` | Busca respostas recentes e classifica estágios de entrevista |
| `get_pipeline` | Resumo completo do pipeline |

## Extensões (adicionando um novo scanner de ATS)

Toda integração de ATS que você vê acima (Greenhouse, Lever, Ashby, Recruitee, Workable, SmartRecruiters,
Gupy) é parte normal deste repositório — mas o moonlighter também suporta **extensões de scanner**:
pacotes Python separados, instalados de forma independente, que registram uma nova fonte de vagas sem
precisar dar fork ou modificar este repositório de jeito nenhum. É assim que o scan do LinkedIn é
distribuído — não porque o mecanismo seja específico do LinkedIn, mas porque os próprios Termos de Uso do
LinkedIn proíbem automação de forma explícita e inequívoca (veja [DISCLAIMER.md](DISCLAIMER.md)), então
essa integração é distribuída como uma extensão opcional em vez de código embutido que qualquer um que
clonar este repo já ganha por padrão.

Preenchimento e envio de formulário via browser não fazem parte deste repositório de jeito nenhum (veja
[Como funciona](#como-funciona) acima) e não é um ponto de extensão — `prepare_application` compõe as
respostas pra você colar, pra qualquer ATS.

### Como funciona

Uma extensão é um pacote Python normal que:

1. Depende de `moonlighter-core` e `moonlighter-scan`, fixado numa tag lançada deste repositório.
2. Traz seu próprio módulo implementando uma subclasse de `BaseScanner` (veja
   `packages/scan/moonlighter/discovery/sources/base.py`).
3. Se declara via `entry_points` no próprio `pyproject.toml` — nenhum código deste repositório importa ou
   cita a extensão em nenhum momento:

```toml
[project.entry-points."moonlighter.scanners"]
minha_plataforma = "meu_pacote.meu_modulo:MeuScanner"

# Opcional: checagem de vaga obsoleta via browser pra uma fonte sem API de listagem
[project.entry-points."moonlighter.staleness_checkers"]
minha_plataforma = "meu_pacote.meu_modulo:check_staleness"
```

Um scanner baseado em browser (como costumam ser as entradas de `moonlighter.scanners`) precisa de
`moonlighter-core[browser]` — veja [Requisitos](#requisitos) acima; um scanner puramente HTTP não precisa
de nada extra.

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
coloque arquivos *dentro* de um subpacote já existente como `moonlighter/discovery/sources/`, já que esse
é um pacote regular (não-namespace) pertencente inteiramente às distribuições deste repositório, e uma
segunda distribuição escrevendo no mesmo caminho colide silenciosamente na instalação. Dê à sua extensão
o próprio diretório de nível raiz.

### Exemplo real

A extensão privada `moonlighter-linkedin` (não publicada, pelo motivo acima) segue exatamente esse padrão
pro scan — o `LinkedInScanner` dela vive no próprio pacote `moonlighter/linkedin_ext/`, registrado via o
grupo de entry_points `moonlighter.scanners` acima. Se você for construir sua própria extensão de scanner,
essa é a forma de referência a copiar.

## Licença

AGPL-3.0 — veja [LICENSE](LICENSE).  
Veja [DISCLAIMER.md](DISCLAIMER.md) para notas importantes sobre ToS, automação e uso do backend LLM.
Veja [PRIVACY.md](PRIVACY.md) (em inglês) para o que esta ferramenta armazena e pra onde vai.
