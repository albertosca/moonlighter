🇺🇸 [English](https://github.com/albertosca/moonlighter/blob/main/packages/scan/README.md) · 🇧🇷 [Português](https://github.com/albertosca/moonlighter/blob/main/packages/scan/README.pt.md)

# moonlighter-scan

A fatia de descoberta do [moonlighter](https://albertosca.github.io/moonlighter/pt/): ela confere os portais de vagas das empresas da sua lista e dá nota a cada vaga nova contra o seu perfil, para você ler só as que valem a pena.

![Como o moonlighter funciona](https://albertosca.github.io/moonlighter/assets/diagrams/how-it-works-light.svg)

## Use sozinho

```bash
uvx moonlighter-scan                          # varre o company_list.yaml e dá nota às vagas novas
uvx moonlighter-scan --company ashby trm-labs # o portal de uma empresa só
uvx moonlighter-scan --no-eval                # guarda as vagas sem nota, sem chamar o LLM
uvx moonlighter-scan doctor
```

Todo comando imprime um documento JSON no stdout e sai com `1` num dia sem novidade, então cabe num cron job e no `jq`.

- **Sete plataformas de ATS** — Greenhouse, Lever, Ashby, Recruitee (incluindo domínios de carreira próprios), Workable, SmartRecruiters e InHire.
- **Portais opcionais** — Gupy, RemoteOK, Remotive, We Work Remotely e HN Who's Hiring, desligados até você ligar, filtrados por palavra-chave.
- **Nota com o raciocínio guardado** — cada vaga recebe de 0 a 10 contra o seu perfil e os seus filtros eliminatórios; abaixo do seu limite ela é arquivada, com o veredito guardado.
- **Cortes baratos primeiro** — títulos da sua lista de bloqueio, e vagas presenciais ou híbridas fora da `criteria.home_city` que você define no perfil, são arquivados antes de qualquer chamada de LLM.
- **Vagas fechadas arquivadas** — vagas que sumiram do portal são arquivadas na próxima varredura.
- **Uma linha por vaga** — as URLs são normalizadas, então a mesma vaga achada duas vezes continua sendo uma só.

## Funciona melhor com

Com o [moonlighter-apply](https://pypi.org/project/moonlighter-apply/), um script só varre, escolhe pela nota e prepara uma folha para cada escolhida. Com o [moonlighter](https://pypi.org/project/moonlighter/), você pede ao Claude.

| Pacote | O que é |
|---|---|
| [moonlighter](https://pypi.org/project/moonlighter/) | Tudo abaixo, mais o servidor MCP para o Claude — comece por aqui |
| [moonlighter-core](https://pypi.org/project/moonlighter-core/) | Armazenamento, config, perfil e o cliente de LLM que todas as fatias compartilham |
| **moonlighter-scan** | ← você está aqui — encontra vagas em sete plataformas de ATS e dá nota a cada uma contra o seu perfil |
| [moonlighter-apply](https://pypi.org/project/moonlighter-apply/) | Rascunha a folha de respostas pronta para colar de uma vaga |
| [moonlighter-email](https://pypi.org/project/moonlighter-email/) | Liga as respostas das empresas no Gmail a cada candidatura |

## Licença

[AGPL-3.0-only](https://github.com/albertosca/moonlighter/blob/main/LICENSE). Contribuições exigem assinar o [CLA](https://github.com/albertosca/moonlighter/blob/main/CLA.md). O que sai da sua máquina está no [PRIVACY.md](https://github.com/albertosca/moonlighter/blob/main/PRIVACY.md) (em inglês).
