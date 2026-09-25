🇺🇸 [English](https://albertosca.github.io/moonlighter/getting-started/first-scan/) · 🇧🇷 [Português](first-scan.md)

# Seu primeiro scan

De um pipeline vazio a uma candidatura pronta para colar, numa conversa só com o Claude. Isto supõe que você terminou a [Instalação](install.md): `config.yaml` gravado, `profile.yaml` e `company_list.yaml` preenchidos e o servidor MCP registrado.

## Como escanear as empresas que você acompanha

1. **Liste as empresas.** No `company_list.yaml`, coloque cada empresa sob o seu ATS (`greenhouse`, `lever`, `ashby`, `workable`, `recruitee`, `smartrecruiters`, `inhire`) e numa fase (`phase1`, `phase2`, `phase3`); uma lista simples, sem fases, é escaneada em todas as fases. O slug é o identificador da empresa na URL do portal de vagas dela: para `https://boards.greenhouse.io/acme`, é `acme`.
2. **Teste uma empresa primeiro.** Pergunte ao Claude "o que tem aberto na acme no Greenhouse?". Isso roda o `scan_company`, que escaneia um portal sem mexer na sua lista — um slug errado aparece aqui, e não no meio de um scan completo.
3. **Escaneie a sua lista.** Peça "escaneia minhas empresas". Isso roda o `scan_and_evaluate`, que busca todas as vagas das empresas em `phase1` e dá nota às novas. Peça a fase `all` (ou `phase2`, `phase3`) para cobrir mais.
4. **Escaneie sem gastar chamadas de LLM** (opcional). Num shell, `moonlighter-scan --no-eval` descobre e grava as vagas sem nota, como `needs_review`; dê nota a uma delas depois com `verify_job`. Veja [Linha de comando](../reference/cli.md).

```text
Você: escaneia minhas empresas

moonlighter: 3 fontes escaneadas — 41 vagas, 38 já conhecidas, 3 novas
  ✓ NOVA — Acme Robotics / Senior Backend Engineer
    Nota: 8.1/10  (limiar: 6.5)
  ✓ NOVA — Nimbus Health / Staff Engineer
    Nota: 7.4/10
  ✗ Vandelay Industries / .NET Architect — 3.2/10, arquivada (filtro duro: .NET)
```

A conversa é ilustrativa: o Claude repassa a saída da ferramenta com as próprias palavras. A ferramenta em si reporta quantas vagas processou, quantas passaram do limiar (com uma tabela delas) e quantas foram filtradas pelo título, arquivadas pela localização ou ficaram abaixo do limiar.

## Como ler as notas

1. **Cada nota vai de 0 a 10**, dada pelo LLM ao comparar a vaga com o seu `profile.yaml`, incluindo os filtros duros e flexíveis em `criteria`.
2. **Abaixo do limiar, a vaga é arquivada automaticamente.** O limiar é o `score_threshold` do `config.yaml`, 6.5 por padrão. Uma vaga que quebra um dos seus filtros duros (".NET" acima) recebe nota baixa e é arquivada com o motivo.
3. **Algumas vagas são arquivadas antes de qualquer chamada de LLM.** Um título que casa com o `title_blocklist` do `config.yaml` é gravado como `archived` com uma observação, sem receber nota. O mesmo vale para uma vaga presencial ou híbrida fora da cidade que você definir em `criteria.home_city` no `profile.yaml`; sem essa chave, nada é arquivado por localização. Uma vaga remota, ou uma cuja localização não resolve a questão, segue para receber nota.
4. **Uma descrição vazia não pode receber nota.** Essas vagas esperam como `needs_review`: peça o `list_jobs` com status `needs_review`, abra a vaga, copie a página inteira e passe o texto ao `verify_job` para dar a nota.
5. **Veja o que passou** com o `list_jobs` (status `new` por padrão) e abra uma vaga com o `get_job` para ver os detalhes completos e o histórico.

## Como preparar sua primeira candidatura

1. **Peça a folha.** "Prepara a candidatura da Acme" roda o `prepare_application`. Quando a API do ATS publica as perguntas do formulário (Greenhouse, Recruitee), o moonlighter as lê de lá.
2. **Sem API? Cole a página.** Quando as perguntas não são publicadas, ele pede que você abra a página da candidatura, selecione tudo, copie e entregue o texto — isso roda o `prepare_application_from_paste`.
3. **Revise a folha inteira.** Toda pergunta recebe uma resposta rascunhada a partir do seu perfil, ou uma marcação dizendo por que precisa de você. O trecho abaixo está no formato real da ferramenta, com os rótulos em inglês, como ela os imprime; o modelo é instruído a responder UNKNOWN quando o seu perfil não lhe dá base, e isso volta como uma lacuna:

   ```text
   [5/9] How many years have you run Elixir in production?  (required)
   !! I DON'T KNOW — no basis in your profile to answer

   1 of 9 need you
   ```

   Responda você mesmo as marcadas, e leia também as rascunhadas — o modelo ainda pode errar uma resposta.
4. **Cole e envie você mesmo.** Copie as respostas para o formulário do empregador e envie por lá. O moonlighter nunca abre o formulário e nunca clica em enviar.
5. **Registre que você enviou.** Diga ao Claude "marca a vaga 42 como submitted" — isso roda o `update_status`. Com o [acompanhamento pelo Gmail](gmail.md) ligado, o campo de e-mail da folha já leva um alias de rastreio, e a resposta do recrutador encontra esta candidatura sozinha.

[← Voltar ao README](https://github.com/albertosca/moonlighter/blob/main/README.pt.md)
