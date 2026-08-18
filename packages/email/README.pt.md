> **[Read in English](https://github.com/albertosca/moonlighter/blob/main/packages/email/README.md)**

# moonlighter-email

A fatia de rastreio do moonlighter: ela vigia teu Gmail atrás de respostas de empregador, casa cada uma com a candidatura que a causou e move teu pipeline adiante — pra "eles chegaram a responder?" virar consulta, não arqueologia.

- **Casada por alias de rastreio** — cada candidatura carrega seu próprio alias de resposta, então rejeição, confirmação ou convite de entrevista pousa na candidatura certa sozinho.
- **Classificada por LLM, em memória** — cada mensagem é classificada (entrevista marcada, rejeição, oferta…) e só um resumo de uma linha é persistido; **assunto e corpo crus nunca chegam ao banco local.**
- **Somente leitura por padrão** — tuas próprias credenciais OAuth do Gmail, nenhum label ou estado tocado sem opt-in.
- **Visão de funil** — os status viram um funil que você pergunta pro Claude: o que espera, o que anda, o que silenciou.

## Parte do moonlighter

Dificilmente você instala esta fatia sozinha — o [moonlighter](https://pypi.org/project/moonlighter/) pina ela junto das três irmãs e liga tudo num servidor MCP pro Claude (`uvx moonlighter`).

| Pacote | O que é |
|---|---|
| [moonlighter](https://pypi.org/project/moonlighter/) | O pipeline inteiro como servidor MCP — comece por aqui |
| [moonlighter-core](https://pypi.org/project/moonlighter-core/) | Banco, config, perfil, cliente de LLM — a fundação |
| [moonlighter-scan](https://pypi.org/project/moonlighter-scan/) | Descoberta de vagas em seis ATS, com nota de aderência por LLM |
| [moonlighter-apply](https://pypi.org/project/moonlighter-apply/) | Redação de respostas de formulário — você revisa, você envia |
| **moonlighter-email** | ← você está aqui — rastreio de respostas de empregador via Gmail |

## Licença

[AGPL-3.0-only](https://github.com/albertosca/moonlighter/blob/main/LICENSE). Contribuições exigem assinar o [CLA](https://github.com/albertosca/moonlighter/blob/main/CLA.md).
