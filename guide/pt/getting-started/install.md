🇺🇸 [English](https://albertosca.github.io/moonlighter/getting-started/install/) · 🇧🇷 [Português](install.md)

# Instalação do moonlighter

O moonlighter roda na sua própria máquina como um servidor MCP para o Claude Code (ou qualquer cliente MCP), mais uma ferramenta de linha de comando por pacote. A configuração tem três passos: rodar o assistente, preencher dois arquivos YAML e registrar o servidor.

## Requisitos

- [uv](https://docs.astral.sh/uv/) — baixa o Python 3.14 para você; não precisa instalar separado
- Chrome, Chromium ou Brave — opcional, só necessário se você instalar uma extensão de scan baseada em browser (ex.: scan do LinkedIn, veja [Extensões](../guides/extensions.md)). O produto base (escanear as APIs de ATS configuradas e preparar candidaturas) nunca abre um browser.
- Um backend de LLM, alternável no `config.yaml` a qualquer momento:
  - `llm_backend: cli` (padrão) — o [Claude Code CLI](https://claude.ai/code), cobrado na sua assinatura do Claude. Sem API key.
  - `llm_backend: api` — o SDK da Anthropic, cobrado em créditos de API. Exige `ANTHROPIC_API_KEY` no ambiente.
- Credenciais OAuth do Gmail (opcional — só para o [acompanhamento pelo Gmail](gmail.md))

## Configuração

Com pressa? O caminho inteiro é:

```bash
uvx moonlighter init                  # assistente: grava o config.yaml
# preencha profile.yaml e company_list.yaml (exemplos abaixo)
claude mcp add-json --scope user moonlighter '{"command":"uvx","args":["moonlighter"]}'
# nova sessão do Claude → "escaneia minhas empresas"
```

Os detalhes:

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

Usa outro cliente MCP? Registre o mesmo comando e argumentos (`uvx` / `["moonlighter"]`) pelo mecanismo de registro do seu próprio cliente — o comando `claude mcp add-json` acima é específico do Claude Code CLI.

### Depois de qualquer uma das opções

O assistente grava o `config.yaml` em `MOONLIGHTER_HOME` (padrão: `~/.moonlighter/`). Dois arquivos ainda precisam de você:

| Arquivo | O que vai nele |
|---------|----------------|
| `profile.yaml` | Sua experiência, suas skills e os `criteria` (os filtros duros e flexíveis que guiam a nota) |
| `company_list.yaml` | As empresas a escanear e qual ATS cada uma usa |

Comece a partir de [`profile.example.yaml`](https://raw.githubusercontent.com/albertosca/moonlighter/main/profile.example.yaml) e [`company_list.example.yaml`](https://raw.githubusercontent.com/albertosca/moonlighter/main/company_list.example.yaml).

O assistente grava um `config.yaml` mínimo; o [`config.example.yaml`](https://raw.githubusercontent.com/albertosca/moonlighter/main/config.example.yaml) documenta o resto da superfície de configuração (resumida em [Configuração](../reference/config.md)), principalmente o bloco `cv` e o bloco `email`. O bloco `cv` só é necessário para usar um currículo diferente por empresa: por padrão o `prepare_application` aponta o `cv.pdf` do `MOONLIGHTER_HOME` para a pergunta de upload de arquivo do formulário, e avisa claramente se nenhum estiver configurado. `profile.yaml`, `company_list.yaml`, `config.yaml` e `cv.pdf` (seu currículo — o moonlighter só diz o nome dele para você anexar, nunca faz o upload sozinho) ficam todos em `MOONLIGHTER_HOME` (padrão: `~/.moonlighter/`).

Reinicie o Claude Code, ou abra uma sessão nova, para que as ferramentas do moonlighter apareçam. Depois de conectado, peça ao Claude para rodar `get_pipeline` — além do funil de candidaturas, ele reporta problemas de configuração, como perfil, currículo ou browser ausentes.

Próximo passo: [rode seu primeiro scan](first-scan.md). O acompanhamento de respostas é opcional e configurado à parte — veja [Acompanhamento pelo Gmail](gmail.md).

## Desenvolvendo no moonlighter

Para trabalhar no código em vez de só usar a ferramenta, veja o [CONTRIBUTING.md](https://github.com/albertosca/moonlighter/blob/main/CONTRIBUTING.md) (em inglês).

[← Voltar ao README](https://github.com/albertosca/moonlighter/blob/main/README.pt.md)
