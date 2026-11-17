🇺🇸 [English](https://albertosca.github.io/moonlighter/reference/mcp-tools/) · 🇧🇷 [Português](mcp-tools.md)

# Ferramentas MCP

O servidor MCP `moonlighter` expõe 19 ferramentas. Você raramente as chama pelo nome: peça ao Claude em linguagem natural ("escaneia minhas empresas", "prepara a candidatura da vaga 42") e ele escolhe a ferramenta. Os nomes abaixo são o que aparece nas chamadas de ferramenta do Claude.

## Escanear e dar nota

| Ferramenta | Descrição |
|------------|-----------|
| `scan_and_evaluate` | Busca e dá nota às vagas de todas as fontes de ATS configuradas (`phase1` por padrão; peça `all` para cobrir todas as fases). Uma vaga já gravada sob outra URL (mesma empresa, título e texto) é arquivada como duplicata, sem chamada ao LLM. O scan termina com a regra de sem resposta, abaixo |
| `scan_company` | Escaneia agora o portal de uma empresa e dá nota às vagas novas, sem editar o `company_list.yaml` |
| `add_job` | Adiciona uma vaga à mão, pela URL. `track=true` mantém como `reviewed` uma vaga que você já decidiu seguir, qualquer que seja a nota |
| `verify_job` | Dá nota a uma vaga deixada como `needs_review` (descrição vazia), a partir do texto que você copia da página da vaga |
| `archive_stale_jobs` | Arquiva vagas que sumiram da fonte; uma empresa cuja checagem falha é reportada e fica intocada, e uma vaga adicionada por URL (sem listagem para conferir) aparece com o link para você confirmar |

## Navegar pelo pipeline

| Ferramenta | Descrição |
|------------|-----------|
| `list_jobs` | Lista vagas por status (`new`, `needs_review`, `applied`, `rejected`, `archived`, …) |
| `get_job` | Mostra os detalhes completos e o histórico de pipeline de uma vaga |
| `get_pipeline` | Resumo completo do pipeline, uma seção por status (`no_response` e `archived` incluídos, para que as seções somem o total) — e problemas de configuração, como perfil ou CV ausentes |
| `reopen_job` | Traz uma vaga arquivada de volta para `reviewed`, para você se candidatar mesmo assim |
| `update_status` | Move pelo pipeline uma candidatura que já existe (`submitted`, `screening`, `interviews`, `offer`, `rejected`, `draft`, `no_response`) |
| `register_application` | Registra numa etapa só uma candidatura feita fora da ferramenta: cria se faltar, tira do arquivo uma vaga arquivada e nunca sobrescreve uma que já existe. Candidatou-se à vaga 42 à mão em 10/11 → `register_application(42, applied_at="2026-11-10")` |

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

## A regra de sem resposta

Ao fim de todo `scan_and_evaluate`, uma candidatura `submitted` sem sinal de vida (nenhuma mudança de status, nenhuma nota datada) por `no_response_after_days` (45 por padrão) vira `no_response`, um status próprio, separado de `rejected`. Candidaturas em `screening`, `interviews` ou `offer` além dessa idade são só listadas, para você decidir.

A regra só roda quando uma sincronização completa de e-mail terminou dentro de `email_sync_max_age_days` (7 por padrão); senão o relatório do scan diz que ela não rodou. Uma sincronização é completa quando classificou toda mensagem da sua janela e ficou abaixo do teto de 500 mensagens.

Cada sincronização completa grava o início da janela que leu, `email.lookback_days` para trás. Uma candidatura só é marcada quando uma cadeia contínua dessas janelas alcança o seu último sinal de vida; as demais são listadas, esperando: aumente `email.lookback_days` na config e rode `sync_email_responses`.

Uma candidatura cujas respostas podem cair numa caixa que a sincronização não lê fica de fora: passe `reply_mailbox_unswept=true` ao `register_application`.

Guias para os fluxos por trás dessas ferramentas: [Primeiro scan](../getting-started/first-scan.md), [Banco de respostas](../guides/answer-bank.md), [CV sob medida](../guides/tailored-cv.md), [Acompanhamento pelo Gmail](../getting-started/gmail.md).

[← Voltar ao README](https://github.com/albertosca/moonlighter/blob/main/README.pt.md)
