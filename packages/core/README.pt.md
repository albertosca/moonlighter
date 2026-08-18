> **[Read in English](https://github.com/albertosca/moonlighter/blob/main/packages/core/README.md)**

# moonlighter-core

A fundação em que todas as outras fatias do moonlighter se apoiam: o armazenamento SQLite (modelos Peewee de vagas, candidaturas e e-mails processados), a camada de configuração do `MOONLIGHTER_HOME`, o seu perfil de candidato, e o cliente de LLM que o pipeline inteiro compartilha.

- **Armazenamento** — SQLite puro em `~/.moonlighter/`, sem servidor, sem conta. Teus dados ficam teus, grepáveis no teu próprio disco.
- **Perfil** — um `profile.yaml` dizendo quem você é; toda resposta que o pipeline redige é curada a partir dele, nunca inventada além dele.
- **Cliente de LLM** — chaveável por config entre o CLI do Claude Code (cobra da tua assinatura Claude, sem API key) e o SDK da Anthropic (tua `ANTHROPIC_API_KEY`).
- **Driver de browser** — extra `[browser]` opcional, usado só por extensões de varredura via browser. O produto base nunca precisa dele.

## Parte do moonlighter

Dificilmente você instala esta fatia sozinha — o [moonlighter](https://pypi.org/project/moonlighter/) pina ela junto das três irmãs e liga tudo num servidor MCP pro Claude (`uvx moonlighter`).

| Pacote | O que é |
|---|---|
| [moonlighter](https://pypi.org/project/moonlighter/) | O pipeline inteiro como servidor MCP — comece por aqui |
| **moonlighter-core** | ← você está aqui — banco, config, perfil, cliente de LLM |
| [moonlighter-scan](https://pypi.org/project/moonlighter-scan/) | Descoberta de vagas em seis ATS, com nota de aderência por LLM |
| [moonlighter-apply](https://pypi.org/project/moonlighter-apply/) | Redação de respostas de formulário — você revisa, você envia |
| [moonlighter-email](https://pypi.org/project/moonlighter-email/) | Rastreio de respostas de empregador via Gmail, casado com cada candidatura |

## Licença

[AGPL-3.0-only](https://github.com/albertosca/moonlighter/blob/main/LICENSE). Contribuições exigem assinar o [CLA](https://github.com/albertosca/moonlighter/blob/main/CLA.md).
