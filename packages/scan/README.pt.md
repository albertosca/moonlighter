> **[Read in English](https://github.com/albertosca/moonlighter/blob/main/packages/scan/README.md)**

# moonlighter-scan

A fatia de descoberta do moonlighter: ela varre os job boards que te interessam e te entrega só as vagas que valem teu tempo — cada uma com nota dada por LLM contra o **seu** perfil, com o raciocínio registrado.

- **Seis plataformas de ATS** — Greenhouse, Lever, Ashby, Recruitee (domínios de carreira customizados inclusos), Workable e SmartRecruiters, guiadas por uma lista de empresas que você configura.
- **Portais opcionais** — RemoteOK, Remotive, WeWorkRemotely e HN Who's Hiring, desligados por padrão na config, com filtro de palavras-chave.
- **Varredura avulsa** — aponta o `scan_company` pra qualquer empresa ("o que a trm-labs tem aberto no Ashby?") sem mexer na tua config.
- **Avaliação por LLM** — toda vaga nova ganha nota contra teu perfil e teus filtros duros; o que fica abaixo do corte é arquivado sozinho, com o veredito guardado pra auditoria.
- **Dedup que segura** — URL normalizada, então a mesma vaga por duas portas continua sendo uma linha só.

## Parte do moonlighter

Dificilmente você instala esta fatia sozinha — o [moonlighter](https://pypi.org/project/moonlighter/) pina ela junto das três irmãs e liga tudo num servidor MCP pro Claude (`uvx moonlighter`).

| Pacote | O que é |
|---|---|
| [moonlighter](https://pypi.org/project/moonlighter/) | O pipeline inteiro como servidor MCP — comece por aqui |
| [moonlighter-core](https://pypi.org/project/moonlighter-core/) | Banco, config, perfil, cliente de LLM — a fundação |
| **moonlighter-scan** | ← você está aqui — descoberta de vagas e nota de aderência por LLM |
| [moonlighter-apply](https://pypi.org/project/moonlighter-apply/) | Redação de respostas de formulário — você revisa, você envia |
| [moonlighter-email](https://pypi.org/project/moonlighter-email/) | Rastreio de respostas de empregador via Gmail, casado com cada candidatura |

## Licença

[AGPL-3.0-only](https://github.com/albertosca/moonlighter/blob/main/LICENSE). Contribuições exigem assinar o [CLA](https://github.com/albertosca/moonlighter/blob/main/CLA.md).
