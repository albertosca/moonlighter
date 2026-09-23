🇺🇸 [English](https://albertosca.github.io/moonlighter/) · 🇧🇷 [Português](index.md)

# moonlighter

**O assistente de candidaturas que deixa a última palavra com você.**

Escaneia os portais de vagas que você escolhe, dá uma nota a cada vaga comparando com o seu perfil e rascunha uma folha de respostas completa a partir dos seus próprios dados, sinalizando o que não consegue responder.

<!-- facts -->1.700+ testes · 100% de cobertura de branches (gate no CI) · 5 pacotes no PyPI · mypy strict<!-- /facts -->

**[Comece aqui →](getting-started/install.md)**

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://albertosca.github.io/moonlighter/assets/diagrams/how-it-works-dark.svg">
  <img alt="o moonlighter escaneia, dá nota e rascunha; só você cola e envia a candidatura" src="https://albertosca.github.io/moonlighter/assets/diagrams/how-it-works-light.svg">
</picture>

*O moonlighter roda localmente e chama o seu LLM: escaneia os portais, dá nota ao fit e rascunha a folha. Só você cola e envia a candidatura ao empregador; a resposta volta casada pelo seu `+alias`.*

## O que ele não faz

- **Ele nunca envia uma candidatura.** Ele rascunha a folha; você cola as respostas no formulário do empregador e envia por conta própria.
- **Seu pipeline mora num arquivo SQLite local.** Vagas, rascunhos e histórico de candidaturas são guardados em `MOONLIGHTER_HOME`. O que sai da sua máquina é só o que vai para o LLM e para as APIs que você configura — Claude, Gmail, os portais de vagas. O [PRIVACY.md](https://github.com/albertosca/moonlighter/blob/main/PRIVACY.md) (em inglês) tem os detalhes.
- **O modelo nunca responde uma pergunta que as guardas reconhecem como de salário, compliance ou dados demográficos.** Essas respostas vêm da sua config ou ficam com você. As guardas reconhecem formulações conhecidas, e no caminho da colagem o modelo ainda lê a página inteira para encontrar as perguntas.

O modelo ainda pode errar uma resposta — e é por isso que toda folha passa pela sua revisão.

## Por onde seguir

- [Instalação](getting-started/install.md) — requisitos, o assistente de configuração e o registro do servidor MCP
- [CV sob medida](guides/tailored-cv.md) — um CV LaTeX de uma página por vaga, montado a partir dos bullets que você curou
- [Banco de respostas](guides/answer-bank.md) — respostas de triagem que você aprovou, reaproveitadas na próxima candidatura
- [Linha de comando](reference/cli.md) — uma CLI em JSON por pacote, para shells e cron jobs
- [Ferramentas MCP](reference/mcp-tools.md) — as 17 ferramentas que o Claude chama por você
- [Extensões](guides/extensions.md) — adicione uma fonte de vagas como um pacote separado

As decisões por trás do design, e o que cada uma custou, estão na página de [Engenharia](engineering.md). Objeções e soluções estão nas [Perguntas frequentes](faq.md).

---

Feito por Alberto Cavalcanti — [LinkedIn](https://www.linkedin.com/in/albertosca/)
