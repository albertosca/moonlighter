🇺🇸 [English](https://albertosca.github.io/moonlighter/reference/cli/) · 🇧🇷 [Português](cli.md)

# Linha de comando

Toda fatia também instala um comando que você pode disparar de um shell ou de um cron job, sem nenhuma conversa com LLM envolvida. As CLIs não dependem do Claude como cliente MCP; as etapas que dão nota ou rascunham continuam chamando o backend de LLM do `config.yaml`, e `--no-eval` faz um scan sem nenhuma chamada de LLM.

## Saída e códigos de saída

Cada comando imprime exatamente um documento JSON no stdout (os logs vão para o stderr) e sai com:

| Código | Significado |
|---|---|
| `0` | sucesso |
| `1` | nada a fazer (nenhuma vaga nova, vaga não encontrada, nenhuma pergunta) |
| `2` | erro de uso ou de config |
| `3` | erro inesperado — o JSON então traz `kind: "error"` e o traceback vai para o stderr |

## Comandos

| Comando | O que faz |
|---|---|
| `moonlighter-scan [--phase all] [--keywords ...]` | Roda um scan; `--company SOURCE SLUG` escaneia um portal só. `--no-eval` descobre e grava as vagas como `needs_review` sem chamar o LLM — dê nota depois com `verify_job`. |
| `moonlighter-apply prepare JOB_ID [--paste FILE]` | Compõe a folha pronta para colar; `--paste -` lê o texto da página do stdin. |
| `moonlighter-apply prepare --url URL [--company X --title Y] [--paste FILE]` | Ingere a vaga primeiro: pela API do ATS quando a URL tem um formato conhecido, senão a partir da própria página, com `--company` e `--title` informados; grava sem nota e depois prepara. Nenhuma chamada de LLM na ingestão. |
| `moonlighter-apply bootstrap-cv [--force] [--skip]` | Rascunha um banco de CV e um template a partir do `profile.yaml` — veja [CV sob medida](../guides/tailored-cv.md). |
| `moonlighter-email sync` | Classifica respostas recentes e avança candidaturas. Sozinho, ele não alimenta o [banco de respostas](../guides/answer-bank.md); quem faz isso é o `sync_email_responses` do servidor MCP. |
| `moonlighter-email register JOB_ID` | Marca uma vaga como candidatada à mão e gera o alias de rastreio `+ref` dela, para que as respostas a ela sejam casadas pelo `sync`. |
| `moonlighter-scan doctor` · `moonlighter-apply doctor` · `moonlighter-email doctor` · `moonlighter doctor` | Onde o estado mora e se a config carrega, em JSON; sai com `1` quando a config está faltando ou é inválida. |

```sh
moonlighter-scan --no-eval | jq '.saved[] | select(.status == "needs_review") | .url'
```

O exemplo acima sai com `1` em todo dia sem novidade (nenhuma vaga nova), o que dispara `set -e`/`pipefail` num script que o encadeia com `jq` — confira o código de saída antes de tratar isso como falha do script. `--no-eval` é zero-**LLM**, não offline: o `archive_stale_jobs` continua fazendo requisições HTTP para checar se vagas já salvas fecharam.

## O que cada instalação oferece

Os cinco pacotes são fatias de uma ferramenta só. Instale as que você precisa; cada comando conta no `--help` o que consegue fazer nessa combinação e o que uma fatia faltando acrescentaria, e o `doctor` imprime o mesmo em JSON.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://albertosca.github.io/moonlighter/assets/diagrams/fitting-dark.svg">
  <img alt="Cada pacote do moonlighter funciona sozinho; instalar dois acrescenta comandos entre eles" src="https://albertosca.github.io/moonlighter/assets/diagrams/fitting-light.svg">
</picture>

*Cada pacote funciona sozinho, e instalar dois acrescenta comandos entre eles; o `moonlighter` instala os três mais o `moonlighter-core`. A saída JSON é a mesma, seja o que for que você instale.*

| Você instala | Você ganha |
|---|---|
| `moonlighter-scan` | `moonlighter-scan`: portais e feeds escaneados, vagas com nota (ou gravadas sem nota com `--no-eval`), as fechadas arquivadas |
| `moonlighter-apply` | `moonlighter-apply prepare`: a folha pronta para colar, a partir de um id de vaga ou direto de uma URL |
| `moonlighter-email` | `moonlighter-email register` e `sync`: candidaturas registradas à mão, respostas do Gmail casadas de volta com elas |
| `moonlighter-scan` + `moonlighter-apply` | um script só: escaneia, escolhe pela nota, prepara uma folha para cada uma |
| `moonlighter-apply` + `moonlighter-email` | o alias de rastreio que uma folha gera é o mesmo que o `sync` usa para casar as respostas |
| `moonlighter` (tudo) | tudo isso acima, mais o servidor MCP para o Claude Code e a promoção para o banco de respostas quando uma resposta avança uma candidatura |

```sh
moonlighter-apply doctor | jq '.slices, .capabilities.missing[].name'
```

[← Voltar ao README](https://github.com/albertosca/moonlighter/blob/main/README.pt.md)
