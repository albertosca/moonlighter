🇺🇸 [English](https://github.com/albertosca/moonlighter/blob/main/packages/apply/README.md) · 🇧🇷 [Português](https://github.com/albertosca/moonlighter/blob/main/packages/apply/README.pt.md)

# moonlighter-apply

A fatia de respostas do [moonlighter](https://albertosca.github.io/moonlighter/pt/): para uma vaga, ela reúne todas as perguntas do formulário de candidatura e rascunha uma resposta para cada uma a partir do seu perfil, numa folha só que você revisa e cola. **Ela nunca abre o formulário e nunca envia.**

![Como o moonlighter funciona](https://albertosca.github.io/moonlighter/assets/diagrams/how-it-works-light.svg)

## Use sozinho

```bash
uvx moonlighter-apply prepare 42                    # perguntas pela API do ATS da vaga
uvx moonlighter-apply prepare 42 --paste page.txt   # perguntas lidas de um texto que você copiou
uvx moonlighter-apply prepare --url https://...     # cadastra a vaga pela URL e prepara
uvx moonlighter-apply doctor
```

Todo comando imprime um documento JSON no stdout.

- **As perguntas de verdade** — onde o ATS publica o formulário (Greenhouse, Recruitee), as perguntas, a obrigatoriedade e as opções vêm direto da API.
- **Qualquer outro formulário** — cole o texto da página e as perguntas são lidas dele; funciona em qualquer ATS, inclusive atrás de login.
- **Lacunas em vez de chutes** — as respostas são rascunhadas a partir de uma parte filtrada do seu perfil. Uma pergunta sem base no perfil volta para você como lacuna, e perguntas que ele reconhece como de salário, compliance ou dados demográficos são preenchidas pela sua config ou deixadas para você, nunca respondidas pelo modelo.
- **Um CV sob medida, se você quiser** — um CV de uma página em LaTeX para a vaga, com bullets escolhidos de um banco que você escreveu; o `bootstrap-cv` rascunha um primeiro banco a partir do seu perfil.
- **Rastreio embutido** — cada folha leva o alias de rastreio da candidatura.

## Funciona melhor com

Com o [moonlighter-email](https://pypi.org/project/moonlighter-email/), as respostas para esse alias avançam a candidatura. Com o [moonlighter-scan](https://pypi.org/project/moonlighter-scan/), você prepara folhas direto da fila com nota.

| Pacote | O que é |
|---|---|
| [moonlighter](https://pypi.org/project/moonlighter/) | Tudo abaixo, mais o servidor MCP para o Claude — comece por aqui |
| [moonlighter-core](https://pypi.org/project/moonlighter-core/) | Armazenamento, config, perfil e o cliente de LLM que todas as fatias compartilham |
| [moonlighter-scan](https://pypi.org/project/moonlighter-scan/) | Encontra vagas em sete plataformas de ATS e dá nota a cada uma contra o seu perfil |
| **moonlighter-apply** | ← você está aqui — rascunha a folha de respostas pronta para colar de uma vaga |
| [moonlighter-email](https://pypi.org/project/moonlighter-email/) | Liga as respostas das empresas no Gmail a cada candidatura |

## Licença

[AGPL-3.0-only](https://github.com/albertosca/moonlighter/blob/main/LICENSE). Contribuições exigem assinar o [CLA](https://github.com/albertosca/moonlighter/blob/main/CLA.md). O que sai da sua máquina está no [PRIVACY.md](https://github.com/albertosca/moonlighter/blob/main/PRIVACY.md) (em inglês).
