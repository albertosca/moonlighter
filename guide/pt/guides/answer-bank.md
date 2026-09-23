🇺🇸 [English](https://albertosca.github.io/moonlighter/guides/answer-bank/) · 🇧🇷 [Português](answer-bank.md)

# Banco de respostas

O banco de respostas guarda as respostas de triagem que você aprovou, para que uma pergunta que você já respondeu numa candidatura seja respondida do mesmo jeito na próxima — sem outra chamada de LLM.

## Como as respostas são reaproveitadas

Toda resposta de triagem que não é de múltipla escolha e que você aprova — "anos de Elixir", "prazo de aviso prévio", qualquer coisa que um formulário pergunta e que não é um campo fixo do perfil — fica em cache por vaga e também é promovida para um banco compartilhado entre vagas, então uma pergunta com a mesma formulação numa candidatura futura reaproveita a resposta em vez de perguntar de novo ao LLM.

Uma resposta é promovida quando você marca a candidatura dela como enviada (`update_status` com `submitted`), ou quando o `sync_email_responses` vê uma resposta de recrutador avançar essa candidatura. As duas coisas acontecem no servidor MCP; o comando avulso `moonlighter-email sync` não alimenta o banco (veja [Linha de comando](../reference/cli.md)).

## Quando uma resposta do banco expira

Uma resposta do banco expira depois de `answer_bank_max_age_days` (padrão 90; `null` desliga a expiração — veja [Configuração](../reference/config.md)), contados a partir da última vez que ela foi enviada — assim uma resposta de prazo de aviso ou de disponibilidade que ficou velha volta a ser perguntada em vez de repetida para sempre.

## Como consultar e apagar respostas

O `list_answer_bank` mostra o que está em cache, das usadas mais recentemente para as mais antigas, com as expiradas marcadas. O `forget_answer` apaga uma, para que a próxima candidatura pergunte de novo.

[← Voltar ao README](https://github.com/albertosca/moonlighter/blob/main/README.pt.md)
