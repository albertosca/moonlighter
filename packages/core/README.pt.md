🇺🇸 [English](https://github.com/albertosca/moonlighter/blob/main/packages/core/README.md) · 🇧🇷 [Português](https://github.com/albertosca/moonlighter/blob/main/packages/core/README.pt.md)

# moonlighter-core

A base do [moonlighter](https://albertosca.github.io/moonlighter/pt/): o armazenamento local, a configuração, o seu perfil de candidato e o cliente de LLM que as outras fatias compartilham. Não tem comando próprio; vem junto com qualquer uma delas.

![Como o moonlighter funciona](https://albertosca.github.io/moonlighter/assets/diagrams/how-it-works-light.svg)

- **Armazenamento** — um arquivo SQLite em `MOONLIGHTER_HOME` (`~/.moonlighter` por padrão), sem servidor e sem conta. O seu pipeline é um arquivo que você pode consultar.
- **Perfil** — um `profile.yaml` que diz quem você é. Toda resposta que o pipeline rascunha parte dele, e o `criteria` guarda os filtros eliminatórios e de preferência que definem a nota.
- **Cliente de LLM** — `llm_backend: cli` roda o Claude Code CLI na sua assinatura do Claude; `llm_backend: api` usa o SDK da Anthropic com a sua `ANTHROPIC_API_KEY`, lida do ambiente ou de `~/.config/anthropic/api.env`.
- **Doctor** — o comando `doctor` de cada fatia informa, em JSON, onde o estado mora, se a config carrega e quais fatias estão instaladas.
- **Driver de navegador** — o extra opcional `[browser]`, usado só por extensões de varredura baseadas em navegador. O fluxo principal nunca abre um navegador.

## Parte do moonlighter

| Pacote | O que é |
|---|---|
| [moonlighter](https://pypi.org/project/moonlighter/) | Tudo abaixo, mais o servidor MCP para o Claude — comece por aqui |
| **moonlighter-core** | ← você está aqui — armazenamento, config, perfil e o cliente de LLM que todas as fatias compartilham |
| [moonlighter-scan](https://pypi.org/project/moonlighter-scan/) | Encontra vagas em sete plataformas de ATS e dá nota a cada uma contra o seu perfil |
| [moonlighter-apply](https://pypi.org/project/moonlighter-apply/) | Rascunha a folha de respostas pronta para colar de uma vaga |
| [moonlighter-email](https://pypi.org/project/moonlighter-email/) | Liga as respostas das empresas no Gmail a cada candidatura |

## Licença

[AGPL-3.0-only](https://github.com/albertosca/moonlighter/blob/main/LICENSE). Contribuições exigem assinar o [CLA](https://github.com/albertosca/moonlighter/blob/main/CLA.md). O que sai da sua máquina está no [PRIVACY.md](https://github.com/albertosca/moonlighter/blob/main/PRIVACY.md) (em inglês).
