🇺🇸 [English](https://albertosca.github.io/moonlighter/getting-started/install/) · 🇧🇷 [Português](install.md)

# Instalação do moonlighter

O moonlighter roda na sua própria máquina como um servidor MCP para o Claude Code, o opencode ou qualquer outro cliente MCP, mais uma ferramenta de linha de comando por pacote. A configuração tem três passos: rodar o assistente, preencher dois arquivos YAML e registrar o servidor.

## Requisitos

- [uv](https://docs.astral.sh/uv/) — baixa o Python 3.14 para você; não precisa instalar separado
- Chrome, Chromium ou Brave — opcional, só necessário se você instalar uma extensão de scan baseada em browser (ex.: scan do LinkedIn, veja [Extensões](../guides/extensions.md)). O produto base (escanear as APIs de ATS configuradas e preparar candidaturas) nunca abre um browser.
- Um backend de LLM, alternável no `config.yaml` a qualquer momento:
  - `llm_backend: cli` (padrão) — o [Claude Code CLI](https://claude.ai/code), cobrado na sua assinatura do Claude. Sem API key.
  - `llm_backend: api` — o SDK da Anthropic, cobrado em créditos de API. Exige `ANTHROPIC_API_KEY`: do ambiente ou, quando ela não estiver lá, de uma linha `ANTHROPIC_API_KEY=...` em `~/.config/anthropic/api.env`.
  - `llm_backend: cursor` — a [CLI do Cursor](https://cursor.com/docs/cli/overview) (`agent`, ou `cursor-agent`), depois de `agent login`. Sem API key. `cursor_model` é opcional; sem ele, vale o modelo padrão da conta.
  - `llm_backend: codex` — a [CLI do Codex](https://developers.openai.com/codex/cli) (`codex`), depois de `codex login` com uma conta ChatGPT. Sem API key. Defina `llm_model` (e, se quiser, `eval_model`) com um modelo que não seja do Claude e que a conta consiga rodar.
  - `llm_backend: opencode` — a [CLI do opencode](https://opencode.ai) (`opencode`), com qualquer provedor em que você entrou por `opencode auth login`. Nenhuma API key vai na configuração do moonlighter. Defina `llm_model` (e, se quiser, `eval_model`) como `provedor/modelo`, do jeito que `opencode models` lista. As chamadas rodam numa configuração isolada, então um provedor que você declarou à mão no seu próprio `opencode.json` (Ollama e afins) não fica disponível para elas.
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

Usa outro cliente MCP? Registre o mesmo comando e argumentos (`uvx` / `["moonlighter"]`) pelo mecanismo de registro do seu próprio cliente — o comando `claude mcp add-json` acima é específico do Claude Code CLI. Para o opencode, veja a Opção C.

### Opção C — opencode

```bash
uvx moonlighter init
```

Quando o `opencode` está no seu PATH, o assistente oferece registrar o servidor na configuração global do opencode: `~/.config/opencode/opencode.json`, ou o mesmo arquivo em `$XDG_CONFIG_HOME/opencode/` ou em `$OPENCODE_CONFIG_DIR` quando essas variáveis existem. Antes de mudar o arquivo, ele faz uma cópia em `opencode.json.bak` (`.bak.1`, `.bak.2` e assim por diante quando já existe um backup). Um arquivo que é link simbólico é editado no destino do link, e o link continua. Um arquivo que ele não consegue editar com segurança (JSONC, um formato que ele não reconhece, ou o moonlighter já registrado) fica como está, e o assistente imprime o bloco para você adicionar à mão:

```json
{
  "mcp": {
    "servers": {
      "moonlighter": {
        "type": "local",
        "command": ["uvx", "moonlighter"],
        "protocol": "2026-07-28",
        "codemode": false
      }
    }
  }
}
```

`protocol` fixa o handshake, porque o padrão do opencode (`auto`) falha com este servidor. `codemode: false` oferece as ferramentas do moonlighter direto ao modelo: no Code Mode, padrão do opencode, elas ficam atrás da ferramenta `execute`. Confira a conexão com `opencode mcp list`, que deve mostrar `✓ moonlighter connected`.

### Depois de qualquer uma das opções

O assistente grava o `config.yaml` em `MOONLIGHTER_HOME` (padrão: `~/.moonlighter/`). Dois arquivos ainda precisam de você:

| Arquivo | O que vai nele |
|---------|----------------|
| `profile.yaml` | Sua experiência, suas skills e os `criteria` (os filtros duros e flexíveis que guiam a nota) |
| `company_list.yaml` | As empresas a escanear e qual ATS cada uma usa |

Comece a partir de [`profile.example.yaml`](https://raw.githubusercontent.com/albertosca/moonlighter/main/profile.example.yaml) e [`company_list.example.yaml`](https://raw.githubusercontent.com/albertosca/moonlighter/main/company_list.example.yaml).

O assistente grava um `config.yaml` mínimo; o [`config.example.yaml`](https://raw.githubusercontent.com/albertosca/moonlighter/main/config.example.yaml) documenta o resto da superfície de configuração (resumida em [Configuração](../reference/config.md)), principalmente o bloco `cv` e o bloco `email`. O bloco `cv` só é necessário para usar um currículo diferente por empresa: por padrão o `prepare_application` aponta o `cv.pdf` do `MOONLIGHTER_HOME` para a pergunta de upload de arquivo do formulário, e avisa claramente se nenhum estiver configurado. `profile.yaml`, `company_list.yaml`, `config.yaml` e `cv.pdf` (seu currículo — o moonlighter só diz o nome dele para você anexar, nunca faz o upload sozinho) ficam todos em `MOONLIGHTER_HOME` (padrão: `~/.moonlighter/`).

Reinicie o seu cliente MCP (Claude Code, opencode), ou abra uma sessão nova, para que as ferramentas do moonlighter apareçam. Depois de conectado, peça ao seu agente para rodar `get_pipeline` — além do funil de candidaturas, ele reporta problemas de configuração, como perfil, currículo ou browser ausentes.

Próximo passo: [rode seu primeiro scan](first-scan.md). O acompanhamento de respostas é opcional e configurado à parte — veja [Acompanhamento pelo Gmail](gmail.md).

## Desenvolvendo no moonlighter

Para trabalhar no código em vez de só usar a ferramenta, veja o [CONTRIBUTING.md](https://github.com/albertosca/moonlighter/blob/main/CONTRIBUTING.md) (em inglês).

[← Voltar ao README](https://github.com/albertosca/moonlighter/blob/main/README.pt.md)
