🇺🇸 [English](https://albertosca.github.io/moonlighter/reference/mcp-tools/) · 🇧🇷 [Português](mcp-tools.md)

# Ferramentas MCP

O servidor MCP `moonlighter` expõe 17 ferramentas. Você raramente as chama pelo nome: peça ao Claude em linguagem natural ("escaneia minhas empresas", "prepara a candidatura da vaga 42") e ele escolhe a ferramenta. Os nomes abaixo são o que aparece nas chamadas de ferramenta do Claude.

## Escanear e dar nota

| Ferramenta | Descrição |
|------------|-----------|
| `scan_and_evaluate` | Busca e dá nota às vagas de todas as fontes de ATS configuradas (`phase1` por padrão; peça `all` para cobrir todas as fases) |
| `scan_company` | Escaneia agora o portal de uma empresa e dá nota às vagas novas, sem editar o `company_list.yaml` |
| `add_job` | Adiciona uma vaga à mão, pela URL |
| `verify_job` | Dá nota a uma vaga deixada como `needs_review` (descrição vazia), a partir do texto que você copia da página da vaga |
| `archive_stale_jobs` | Arquiva vagas que sumiram da fonte; uma empresa cuja checagem falha é reportada e fica intocada |

## Navegar pelo pipeline

| Ferramenta | Descrição |
|------------|-----------|
| `list_jobs` | Lista vagas por status (`new`, `needs_review`, `applied`, `rejected`, `archived`, …) |
| `get_job` | Mostra os detalhes completos e o histórico de pipeline de uma vaga |
| `get_pipeline` | Resumo completo do pipeline — e problemas de configuração, como perfil ou CV ausentes |
| `update_status` | Move à mão a candidatura de uma vaga pelo pipeline (`submitted`, `screening`, `interviews`, `offer`, `rejected`, `draft`) |

## Preparar candidaturas

| Ferramenta | Descrição |
|------------|-----------|
| `prepare_application` | Compõe todas as respostas do formulário de candidatura de uma vaga numa única folha revisável, para você colar e enviar |
| `prepare_application_from_paste` | O mesmo que `prepare_application`, para um formulário cujas perguntas nenhuma API publica — passe o texto que você copiou da página |
| `list_answer_bank` | Toda resposta de triagem do banco, das usadas mais recentemente para as mais antigas; as expiradas marcadas |
| `forget_answer` | Apaga uma resposta do banco para que a próxima candidatura pergunte de novo ao LLM |
| `bootstrap_cv_pool` | Rascunha um banco de CV + template a partir do seu profile.yaml — um primeiro rascunho para revisar |
| `skip_cv_bootstrap` | Recusa a oferta de bootstrap do banco de CV uma vez, de forma permanente |

## Acompanhar respostas

| Ferramenta | Descrição |
|------------|-----------|
| `setup_email` | Autoriza o OAuth do Gmail |
| `sync_email_responses` | Busca as respostas mais recentes e classifica as etapas de entrevista |

Guias para os fluxos por trás dessas ferramentas: [Primeiro scan](../getting-started/first-scan.md), [Banco de respostas](../guides/answer-bank.md), [CV sob medida](../guides/tailored-cv.md), [Acompanhamento pelo Gmail](../getting-started/gmail.md).

[← Voltar ao README](https://github.com/albertosca/moonlighter/blob/main/README.pt.md)
