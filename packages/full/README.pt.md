🇺🇸 [English](https://github.com/albertosca/moonlighter/blob/main/packages/full/README.md) · 🇧🇷 [Português](https://github.com/albertosca/moonlighter/blob/main/packages/full/README.pt.md)

# moonlighter

**O assistente de candidaturas que deixa a última palavra com você.**

O moonlighter varre os portais de vagas que você escolhe, dá nota a cada vaga contra o seu perfil e rascunha uma folha de respostas completa a partir dos seus próprios dados, sinalizando o que não consegue responder. Ele nunca abre o formulário e nunca clica em enviar: você revisa a folha, cola e envia.

![Como o moonlighter funciona](https://albertosca.github.io/moonlighter/assets/diagrams/how-it-works-light.svg)

## Comece

```bash
uvx moonlighter          # o servidor MCP, para o Claude Code
uvx moonlighter init     # um assistente curto que escreve o config.yaml
```

Registre no Claude Code e converse com ele: *"varre minhas empresas"*, *"o que tem de novo acima de 7?"*, *"prepara a candidatura da vaga 42"*. Instalação, configuração e todas as tools estão na [documentação](https://albertosca.github.io/moonlighter/pt/).

## O que você ganha

- **Uma fila com nota** — sete plataformas de ATS mais portais opcionais, cada vaga com nota de 0 a 10 contra o seu perfil e seus filtros eliminatórios, com o raciocínio guardado.
- **Uma folha por candidatura** — todas as perguntas do formulário, respondidas a partir do seu perfil; uma pergunta sem base no perfil volta para você como lacuna, não como chute. Perguntas que ele reconhece como de salário, compliance ou dados demográficos são preenchidas pela sua config ou deixadas para você, nunca respondidas pelo modelo.
- **Um CV sob medida, se você quiser** — um CV de uma página em LaTeX por vaga, com bullets escolhidos entre os que você escreveu.
- **Respostas que acham a sua candidatura** — cada folha leva um alias de rastreio, e as respostas no Gmail para esse alias avançam aquela candidatura.
- **Um banco de respostas** — quando uma candidatura é marcada como enviada, as respostas dela voltam a ser oferecidas quando a mesma pergunta aparece de novo.

## O que vem dentro

Este pacote fixa as quatro fatias abaixo na mesma versão e acrescenta o servidor MCP, o assistente `moonlighter init` e o manifesto do plugin do Claude Code. Cada fatia também instala sozinha, com uma ferramenta de linha de comando que imprime JSON — veja [o que cada instalação oferece](https://albertosca.github.io/moonlighter/pt/reference/cli/#o-que-cada-instalacao-oferece).

| Pacote | O que é |
|---|---|
| **moonlighter** | ← você está aqui — tudo abaixo, mais o servidor MCP para o Claude — comece por aqui |
| [moonlighter-core](https://pypi.org/project/moonlighter-core/) | Armazenamento, config, perfil e o cliente de LLM que todas as fatias compartilham |
| [moonlighter-scan](https://pypi.org/project/moonlighter-scan/) | Encontra vagas em sete plataformas de ATS e dá nota a cada uma contra o seu perfil |
| [moonlighter-apply](https://pypi.org/project/moonlighter-apply/) | Rascunha a folha de respostas pronta para colar de uma vaga |
| [moonlighter-email](https://pypi.org/project/moonlighter-email/) | Liga as respostas das empresas no Gmail a cada candidatura |

O moonlighter roda localmente e chama o seu LLM; não existe servidor nem conta do moonlighter. O seu pipeline é um arquivo SQLite em `~/.moonlighter`.

## Licença

[AGPL-3.0-only](https://github.com/albertosca/moonlighter/blob/main/LICENSE). Contribuições exigem assinar o [CLA](https://github.com/albertosca/moonlighter/blob/main/CLA.md). O que sai da sua máquina está no [PRIVACY.md](https://github.com/albertosca/moonlighter/blob/main/PRIVACY.md) (em inglês).
