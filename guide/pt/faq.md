🇺🇸 [English](https://albertosca.github.io/moonlighter/faq/) · 🇧🇷 [Português](faq.md)

# Perguntas frequentes

Respostas diretas às perguntas que as pessoas fazem antes de confiar suas candidaturas a uma ferramenta, e depois soluções para os problemas mais comuns.

## Perguntas

### O moonlighter se candidata por mim?

Não. O moonlighter nunca envia uma candidatura. Ele escaneia, dá nota e rascunha uma folha de respostas completa; você cola as respostas no formulário do empregador e envia por conta própria. Ele nunca abre o formulário e nunca clica em enviar — a automação de browser que um dia fazia isso saiu do produto em 12/08/2026 (veja [Engenharia](engineering.md#deixamos-de-dirigir-o-browser)).

### Ele pode errar uma resposta?

Pode — qualquer LLM pode. O moonlighter reduz o espaço para isso: as respostas são rascunhadas a partir do seu perfil, e o modelo é instruído a responder UNKNOWN quando o seu perfil não lhe dá base, o que volta para você como uma lacuna; perguntas que as guardas reconhecem como de salário, compliance ou dados demográficos recebem o valor que você configurou ou ficam com você, nunca uma resposta rascunhada; e uma resposta de texto livre dirigida a você em vez do empregador vira uma lacuna. Nada disso torna uma resposta rascunhada correta por construção, e é por isso que você revisa toda folha antes de enviar.

### Funciona sem o Claude?

Em parte. As [ferramentas de linha de comando](reference/cli.md) rodam de qualquer shell ou cron job sem o Claude como cliente MCP, e `moonlighter-scan --no-eval` escaneia sem nenhuma chamada de LLM. Dar nota às vagas, rascunhar respostas e classificar respostas de recrutadores precisa de um backend de LLM: hoje é o da Anthropic, pelo Claude Code CLI (`llm_backend: cli`) ou pela API (`llm_backend: api`).

### O que sai da minha máquina?

Seu pipeline — vagas, respostas rascunhadas, histórico de candidaturas — é um arquivo SQLite local em `MOONLIGHTER_HOME`. O que sai é o que vai para os serviços que você configura. Para o LLM (Claude): descrições de vagas, um subconjunto filtrado do seu perfil, os bullets do seu banco de CV quando o [CV sob medida](guides/tailored-cv.md) está ligado e qualquer texto de página que você cole no `prepare_application_from_paste`. Além disso: requisições só de leitura aos portais de vagas e, se você ligar o [acompanhamento pelo Gmail](getting-started/gmail.md), seus e-mails recentes, lidos pela API do Gmail e enviados ao LLM para serem classificados. Não existe servidor do moonlighter nem telemetria. O [PRIVACY.md](https://github.com/albertosca/moonlighter/blob/main/PRIVACY.md) (em inglês) tem os detalhes.

## Solução de problemas

- **As ferramentas do moonlighter não aparecem no Claude** — servidores MCP são lidos no início da sessão: reinicie o Claude Code (ou abra uma sessão nova) depois de registrar.
- **`uvx moonlighter` roda uma versão velha** — o uvx faz cache de ambientes; rode `uvx --refresh moonlighter` uma vez depois de um release.
- **O scan não acha nada** — confira o `company_list.yaml`: cada entrada precisa do slug real da empresa no ATS (a parte da URL da página de vagas dela), sob a chave de fonte certa. Teste uma empresa com o `scan_company` antes de escanear tudo.
- **Erros de LLM com `llm_backend: cli`** — o backend padrão chama o [Claude Code CLI](https://claude.ai/code); ele precisa estar instalado e logado. Troque para `llm_backend: api` + `ANTHROPIC_API_KEY` se preferir pagar em créditos de API.
- **Avisos de "missing profile / CV"** — peça ao Claude para rodar o `get_pipeline`: além do funil, ele reporta exatamente qual arquivo de configuração falta e onde ele deve ficar.
- **A sincronização do Gmail não faz nada** — o acompanhamento por e-mail é opcional e fica desligado até o `setup_email` completar o fluxo OAuth; veja [Acompanhamento pelo Gmail](getting-started/gmail.md).

Continua travado? [Abra uma discussion](https://github.com/albertosca/moonlighter/discussions) — um relato que inclui o que o `get_pipeline` imprimiu é resolvido mais rápido.

[← Voltar ao README](https://github.com/albertosca/moonlighter/blob/main/README.pt.md)
