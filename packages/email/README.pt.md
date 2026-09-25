🇺🇸 [English](https://github.com/albertosca/moonlighter/blob/main/packages/email/README.md) · 🇧🇷 [Português](https://github.com/albertosca/moonlighter/blob/main/packages/email/README.pt.md)

# moonlighter-email

A fatia de acompanhamento do [moonlighter](https://albertosca.github.io/moonlighter/pt/): ela lê o seu Gmail atrás de respostas das empresas, liga cada uma à candidatura que ela responde e avança essa candidatura, para "eles chegaram a responder?" ter resposta.

![Como o moonlighter funciona](https://albertosca.github.io/moonlighter/assets/diagrams/how-it-works-light.svg)

## Use sozinho

```bash
uvx moonlighter-email register 42   # marca a vaga 42 como candidatada e cria o alias de rastreio
uvx moonlighter-email sync          # lê as respostas recentes e avança as candidaturas
uvx moonlighter-email doctor
```

Todo comando imprime um documento JSON no stdout.

- **Ligado pelo alias de rastreio** — cada candidatura ganha um endereço `+ref` próprio, então uma recusa, uma confirmação de recebimento ou um convite de entrevista cai na candidatura certa.
- **Classificado, não guardado** — o LLM classifica cada resposta em memória e só um resumo de uma linha é guardado; o assunto e o corpo nunca chegam ao banco local.
- **Só leitura por padrão** — as suas próprias credenciais OAuth do Gmail; nada é marcado nem arquivado a menos que você ligue.

## Funciona melhor com

Com o [moonlighter-apply](https://pypi.org/project/moonlighter-apply/), a folha que você cola já leva o alias da candidatura. Com o [moonlighter](https://pypi.org/project/moonlighter/), uma resposta que avança uma candidatura também guarda as respostas dela no banco de respostas.

| Pacote | O que é |
|---|---|
| [moonlighter](https://pypi.org/project/moonlighter/) | Tudo abaixo, mais o servidor MCP para o Claude — comece por aqui |
| [moonlighter-core](https://pypi.org/project/moonlighter-core/) | Armazenamento, config, perfil e o cliente de LLM que todas as fatias compartilham |
| [moonlighter-scan](https://pypi.org/project/moonlighter-scan/) | Encontra vagas em sete plataformas de ATS e dá nota a cada uma contra o seu perfil |
| [moonlighter-apply](https://pypi.org/project/moonlighter-apply/) | Rascunha a folha de respostas pronta para colar de uma vaga |
| **moonlighter-email** | ← você está aqui — liga as respostas das empresas no Gmail a cada candidatura |

## Licença

[AGPL-3.0-only](https://github.com/albertosca/moonlighter/blob/main/LICENSE). Contribuições exigem assinar o [CLA](https://github.com/albertosca/moonlighter/blob/main/CLA.md). O que sai da sua máquina está no [PRIVACY.md](https://github.com/albertosca/moonlighter/blob/main/PRIVACY.md) (em inglês).
