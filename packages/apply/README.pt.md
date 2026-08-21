> **[Read in English](https://github.com/albertosca/moonlighter/blob/main/packages/apply/README.md)**

# moonlighter-apply

A fatia de respostas do moonlighter: ela lê cada pergunta que um formulário de candidatura faz e redige uma resposta pra cada uma, curada do teu perfil — e entrega tudo numa folha única revisável. Você lê, você cola, você aperta enviar. **Ela nunca abre browser, nunca toca no formulário, nunca envia.**

- **Perguntas direto da fonte** — onde o ATS publica o schema do formulário (Greenhouse, Recruitee), o `prepare_application` busca as perguntas reais, obrigatoriedades e opções direto da API.
- **Qualquer outro formulário** — o `prepare_application_from_paste` faz o mesmo a partir do texto que você copia da página; funciona em qualquer ATS, inclusive atrás de login.
- **Curado, não inventado** — as respostas saem de um subconjunto filtrado do teu perfil; o que o perfil não responde honestamente vira lacuna sinalizada pra você, nunca improviso.
- **Recusa em vez de converter** — campo ambíguo (salário em moeda errada, pergunta de visto confusa) volta pra tua revisão em vez de virar chute silencioso.
- **Rastreio embutido** — cada folha carrega o alias de rastreio da candidatura, então a resposta do empregador pousa de volta no teu pipeline (ver [moonlighter-email](https://pypi.org/project/moonlighter-email/)).

## Parte do moonlighter

Dificilmente você instala esta fatia sozinha — o [moonlighter](https://pypi.org/project/moonlighter/) pina ela junto das três irmãs e liga tudo num servidor MCP pro Claude (`uvx moonlighter`).

| Pacote | O que é |
|---|---|
| [moonlighter](https://pypi.org/project/moonlighter/) | O pipeline inteiro como servidor MCP — comece por aqui |
| [moonlighter-core](https://pypi.org/project/moonlighter-core/) | Banco, config, perfil, cliente de LLM — a fundação |
| [moonlighter-scan](https://pypi.org/project/moonlighter-scan/) | Descoberta de vagas em seis ATS, com nota de aderência por LLM |
| **moonlighter-apply** | ← você está aqui — redação de respostas; você revisa, você envia |
| [moonlighter-email](https://pypi.org/project/moonlighter-email/) | Rastreio de respostas de empregador via Gmail, casado com cada candidatura |

## Licença

[AGPL-3.0-only](https://github.com/albertosca/moonlighter/blob/main/LICENSE). Contribuições exigem assinar o [CLA](https://github.com/albertosca/moonlighter/blob/main/CLA.md).
