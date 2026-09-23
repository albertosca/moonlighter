🇺🇸 [English](https://albertosca.github.io/moonlighter/getting-started/gmail/) · 🇧🇷 [Português](gmail.md)

# Acompanhamento pelo Gmail

Opcional. Quando está ligado, o moonlighter lê as respostas de recrutadores na sua caixa do Gmail, casa cada uma com a candidatura que ela responde pelo alias de rastreio e avança essa candidatura no pipeline — assim você sabe quais candidaturas tiveram resposta sem precisar procurar na caixa de entrada.

## Como conectar o Gmail

1. Crie um projeto no [Google Cloud Console](https://console.cloud.google.com), ative a API do Gmail e baixe as credenciais OAuth como `client.json`.
2. Coloque o arquivo como `gmail-client.json` dentro de `MOONLIGHTER_HOME` (padrão `~/.moonlighter/`).
3. Defina `email.address` no `config.yaml` com o endereço do Gmail que você usa para se candidatar. Cada folha preparada gera a partir dele um alias de rastreio (`you+ref@gmail.com`), e é por esse alias que uma resposta encontra a sua candidatura.
4. A primeira chamada ao `setup_email` abre um browser para a autorização e salva o token.

A partir daí, peça ao Claude para rodar o `sync_email_responses`, ou rode `moonlighter-email sync` de um shell ou de um cron job (veja [Linha de comando](../reference/cli.md)).

## O que a sincronização lê e grava

- **Lê** seus e-mails recentes pela API do Gmail, com as suas próprias credenciais OAuth, voltando `email.lookback_days` dias (padrão 30).
- **Classifica** cada mensagem com o LLM, em memória. Só um resumo curto gerado é gravado no banco local — nunca o assunto ou o corpo brutos.
- **Casa** uma resposta com a sua candidatura pelo alias `+ref`, e só então avança essa candidatura. Uma resposta sem o alias é casada por empresa e título como sugestão: ela é reportada a você, nunca aplicada.
- **Não mexe no Gmail** por padrão: a deduplicação fica numa tabela local. Marcar com label e arquivar são opcionais (`mark_processed`, `archive_ref_matched`, `archive_all_classified` — veja [Configuração](../reference/config.md#email)) e precisam do escopo `gmail.modify`.

O [PRIVACY.md](https://github.com/albertosca/moonlighter/blob/main/PRIVACY.md) (em inglês) lista tudo o que a sincronização toca.

[← Voltar ao README](https://github.com/albertosca/moonlighter/blob/main/README.pt.md)
