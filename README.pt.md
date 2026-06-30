> **[Read in English](README.md)**

# gauntler

Pipeline de candidatura a vagas com IA. Escaneia portais de emprego, avalia o fit do candidato via LLM e automatiza candidaturas via browser — tudo orquestrado pelo Claude através de um servidor [Model Context Protocol](https://modelcontextprotocol.io) (MCP).

## Como funciona

1. **Scan** — busca vagas no Greenhouse, Lever, Ashby e LinkedIn para a lista de empresas que você configura.
2. **Avaliação** — pontua cada vaga em relação ao seu perfil via LLM; vagas abaixo do limiar são arquivadas automaticamente.
3. **Candidatura** — preenche e envia formulários de candidatura num browser real (Playwright), com respostas geradas pelo LLM sob medida para cada vaga.
4. **Monitoramento** — monitora sua caixa do Gmail em busca de convites para entrevista e atualiza o status do pipeline.

Todas as etapas são expostas como ferramentas MCP e orquestradas pelo Claude numa conversa.

## Arquitetura

Um [workspace uv](https://docs.astral.sh/uv/concepts/workspaces/) com 5 namespace packages (`gauntler.*`), organizados por feature:

| Package | Namespace | Propósito |
|---------|-----------|-----------|
| `gauntler-core` | `gauntler.core` | DB (Peewee/SQLite), config, browser driver, cliente LLM |
| `gauntler-scan` | `gauntler.discovery` | Scrapers de ATS e scoring de vagas via LLM |
| `gauntler-apply` | `gauntler.application` | Preenchedor de formulários, gerador de respostas, work-auth |
| `gauntler-email` | `gauntler.tracking` | Sincronização com Gmail e classificação de estágios de entrevista |
| `gauntler-full` | `gauntler.server` | Servidor FastMCP — conecta todos os pacotes |

## Requisitos

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- Chrome, Chromium ou Brave (para automação de browser)
- [Claude Code CLI](https://claude.ai/code) — ou `ANTHROPIC_API_KEY` para `llm_backend: api`
- Credenciais OAuth do Gmail (opcional — só para rastreamento de e-mails)

## Instalação

### 1. Instalar

```bash
git clone https://github.com/albertosca/gauntler
cd gauntler
uv sync --all-packages
```

### 2. Configurar

Copie os arquivos de exemplo para o `GAUNTLER_HOME` (padrão: `~/.gauntler/`) e edite:

```bash
mkdir -p ~/.gauntler
cp config.example.yaml ~/.gauntler/config.yaml
cp profile.example.yaml ~/.gauntler/profile.yaml
cp company_list.example.yaml ~/.gauntler/company_list.yaml
```

Campos principais do `config.yaml`:

| Campo | Descrição |
|-------|-----------|
| `browser_path` | Caminho para o executável do Chrome/Chromium/Brave |
| `llm_backend` | `"cli"` (sessão do Claude Code) ou `"api"` (API key da Anthropic) |
| `score_threshold` | Vagas abaixo desta pontuação (0–10) são arquivadas |
| `work_authorization` | Seu país de cidadania e as strings de resposta para os formulários ATS |

Preencha `profile.yaml` com sua experiência real, skills e `criteria` (os filtros hard/soft guiam o scoring).

Edite `company_list.yaml` para adicionar as empresas e plataformas ATS que quer escanear.

### 3. Rastreamento por Gmail (opcional)

1. Crie um projeto no [Google Cloud Console](https://console.cloud.google.com), ative a API do Gmail e baixe as credenciais OAuth como `client.json`.
2. Coloque o arquivo em `~/.gauntler/gmail-client.json`.
3. Na primeira chamada a `setup_email`, um browser abrirá para autorização e o token será salvo.

### 4. Registrar como servidor MCP

Adicione ao `~/.claude/settings.json` (ou ao `settings.json` do projeto):

```json
{
  "mcpServers": {
    "gauntler": {
      "command": "/caminho/para/gauntler/.venv/bin/python",
      "args": ["-m", "gauntler.server"]
    }
  }
}
```

Reinicie o Claude Code — as ferramentas abaixo aparecem automaticamente.

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
| `login` | Abre o browser e persiste a sessão (LinkedIn) |
| `update_status` | Move uma vaga manualmente pelo pipeline |
| `setup_email` | Autoriza OAuth do Gmail |
| `sync_email_responses` | Busca respostas recentes e classifica estágios de entrevista |
| `get_pipeline` | Resumo completo do pipeline |

## Licença

AGPL-3.0 — veja [LICENSE](LICENSE).  
Veja [DISCLAIMER.md](DISCLAIMER.md) para notas importantes sobre ToS, automação e uso do backend LLM.
