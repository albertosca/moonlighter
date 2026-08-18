> **[Read in English](https://github.com/albertosca/moonlighter/blob/main/packages/full/README.md)**

# moonlighter

O pipeline inteiro de busca de emprego, comandado de dentro de uma conversa com o Claude. O moonlighter varre job boards, dá nota em cada vaga contra o **seu** perfil usando LLM, redige todas as respostas que um formulário de candidatura pedir e acompanha as respostas dos empregadores na sua caixa de entrada — tudo exposto ao Claude como ferramentas [MCP](https://modelcontextprotocol.io), a um `uvx moonlighter` de distância.

Duas coisas que ele **nunca** faz: abrir browser pra preencher formulário, ou enviar candidatura por você. Ele monta uma folha de respostas revisável — a candidatura inteira, pergunta por pergunta — e quem cola e aperta enviar é **você**. O nome na candidatura é o seu; o controle também.

```bash
uvx moonlighter        # sobe o servidor MCP
```

Depois é registrar no Claude Code e conversar: *"varre minhas empresas"*, *"o que chegou acima de 7?"*, *"prepara a candidatura da vaga 42"*. Setup, configuração e a lista completa de ferramentas estão no [README do repositório](https://github.com/albertosca/moonlighter#readme).

## O que vem dentro

Esta é a distribuição guarda-chuva: ela pina as quatro fatias abaixo em versão travada e soma o servidor FastMCP, o wizard `moonlighter init` e o manifesto de plugin do Claude Code.

| Pacote | O que é |
|---|---|
| **moonlighter** | ← você está aqui — tudo abaixo, ligado num servidor MCP |
| [moonlighter-core](https://pypi.org/project/moonlighter-core/) | Banco, config, perfil e o cliente de LLM — a fundação |
| [moonlighter-scan](https://pypi.org/project/moonlighter-scan/) | Descoberta de vagas em seis ATS, com nota de aderência por LLM |
| [moonlighter-apply](https://pypi.org/project/moonlighter-apply/) | Redação de respostas de formulário — você revisa, você envia |
| [moonlighter-email](https://pypi.org/project/moonlighter-email/) | Rastreio de respostas de empregador via Gmail, casado com cada candidatura |

Tudo roda na sua máquina, com os seus dados e as suas chaves — não existe servidor nem conta do moonlighter. Ver [PRIVACY.md](https://github.com/albertosca/moonlighter/blob/main/PRIVACY.md) e [DISCLAIMER.md](https://github.com/albertosca/moonlighter/blob/main/DISCLAIMER.md).

## Licença

[AGPL-3.0-only](https://github.com/albertosca/moonlighter/blob/main/LICENSE). Contribuições exigem assinar o [CLA](https://github.com/albertosca/moonlighter/blob/main/CLA.md).
