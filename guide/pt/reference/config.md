🇺🇸 [English](https://albertosca.github.io/moonlighter/reference/config/) · 🇧🇷 [Português](config.md)

# Configuração

O `config.yaml` fica em `MOONLIGHTER_HOME` (padrão `~/.moonlighter/`); o `uvx moonlighter init` grava um mínimo. Esta página cobre as chaves que os guias citam. A superfície completa, comentada, está no [`config.example.yaml`](https://github.com/albertosca/moonlighter/blob/main/config.example.yaml) do repositório. Caminhos relativos em qualquer chave são resolvidos dentro de `MOONLIGHTER_HOME`; um caminho absoluto ou iniciado com `~` é usado como está. Uma chave desconhecida ou um valor de tipo errado é rejeitado na inicialização, com o nome da chave, em vez de ignorado em silêncio.

## Chaves de nível raiz

| Chave | Padrão | O que faz |
|---|---|---|
| `llm_backend` | `cli` | `cli` chama o Claude Code CLI (sua assinatura do Claude); `api` usa o SDK da Anthropic e precisa de `ANTHROPIC_API_KEY` |
| `score_threshold` | `6.5` | Vagas com nota abaixo disso são arquivadas depois de um scan |
| `title_blocklist` | `[]` | Trechos de título (sem diferenciar maiúsculas) descartados antes de qualquer chamada de LLM |
| `answer_bank_max_age_days` | `90` | Dias, contados do último envio, depois dos quais uma resposta do banco deixa de ser reaproveitada; `null` desliga a expiração — veja [Banco de respostas](../guides/answer-bank.md) |
| `portal_max_age_days` | `30` | Idade a partir da qual as vagas de feeds de portal (RemoteOK, Remotive, WeWorkRemotely, HN Who's Hiring, Gupy), que não podem ser checadas na fonte, são arquivadas; `0` desliga |

## cv

| Chave | Padrão | O que faz |
|---|---|---|
| `cv.default` | `cv.pdf` | O currículo que o `prepare_application` indica para a pergunta de upload de arquivo do formulário |
| `cv.by_company` | `{}` | Um currículo diferente por empresa, casado pelo nome da empresa sem diferenciar maiúsculas |
| `cv.pool` | `cv-pool.yaml` | O banco de bullets curado; o [CV sob medida](../guides/tailored-cv.md) liga quando esse arquivo existe |
| `cv.template_dir` | `cv-templates` | Guarda o `cv-template.en.tex` e, opcionalmente, o `cv-template.pt.tex` |
| `cv.generated_dir` | `cv-generated` | Onde fica o cache do CV sob medida de cada vaga, um diretório por id de vaga |

## email

Só para o [acompanhamento pelo Gmail](../getting-started/gmail.md).

| Chave | Padrão | O que faz |
|---|---|---|
| `email.address` | nenhum | O endereço do Gmail com que você se candidata; os aliases de rastreio (`you+ref@gmail.com`) são gerados a partir dele, e a sincronização precisa dele |
| `email.credentials_path` | `gmail-client.json` | O arquivo de cliente OAuth do Google Cloud Console |
| `email.token_path` | `gmail-token.json` | Onde o `setup_email` salva (e sobrescreve) o token |
| `email.lookback_days` | `30` | Quantos dias para trás a sincronização lê, lidos ou não lidos |
| `email.mark_processed` | `false` | `true` marca com label no Gmail os e-mails processados; por padrão a deduplicação fica numa tabela local |
| `email.processed_label` | `moonlighter/processed` | O label usado quando `mark_processed` está ligado |
| `email.archive_ref_matched` | `false` | Arquiva as respostas casadas pelo alias que avançaram uma candidatura |
| `email.archive_all_classified` | `false` | Arquiva também os e-mails classificados como casamento aproximado ou incerto; e-mail sem relação nunca é tocado |
| `email.interview_stages` | `[]` | Nomes de etapa que uma resposta classificada pode definir; o arquivo de exemplo lista quatro, e uma sincronização acrescenta, enquanto durar aquela execução, as etapas novas que o classificador propuser |

Marcar com label e arquivar precisam do escopo `gmail.modify`; o `setup_email` pede o seu consentimento de novo se o seu token for só de leitura.

[← Voltar ao README](https://github.com/albertosca/moonlighter/blob/main/README.pt.md)
