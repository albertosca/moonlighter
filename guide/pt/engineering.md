🇺🇸 [English](https://albertosca.github.io/moonlighter/engineering/) · 🇧🇷 [Português](engineering.md)

# Engenharia

O moonlighter rascunha candidaturas que saem com o seu nome, então a régua é confiança. Esta página registra as decisões de design por trás dessa régua, o que cada uma custou e onde conferir isso no código.

## Decisões e os custos que aceitamos

| Decisão | Custo aceito |
|---|---|
| Deixamos de dirigir o browser | Cada candidatura custa a você uma colagem e um clique |
| Guardas determinísticas em volta da etapa de redação | Elas só reconhecem formulações conhecidas |
| Texto do modelo escapado no LaTeX do CV, nunca validado | A saída do modelo não carrega formatação LaTeX além de negrito |
| Cinco fatias com fronteira de import testada e releases em lockstep | Todo release sobe a versão de cinco pacotes à mão |
| 100% de cobertura de branches como gate, gates provados por canários | Todo branch novo custa um teste |

### Deixamos de dirigir o browser

O moonlighter preenchia formulários de ATS num browser de verdade. Em 12/08/2026 ([`37b1ac2`](https://github.com/albertosca/moonlighter/commit/37b1ac2)) esses preenchedores via browser saíram da `main` para uma branch própria, e o produto passou a ser assistido: ele rascunha a folha de respostas inteira, e você a cola no formulário e envia. O custo é um passo manual em cada candidatura. O que se ganha com isso: a ferramenta não consegue enviar nada em seu nome, e não depende mais de marcação de formulário, captchas e regras de plataforma que ela não controla.

### Guardas determinísticas em volta da etapa de redação

Algumas perguntas não deveriam ser respondidas por um modelo. Antes da redação, código comum reconhece perguntas de salário (respondidas a partir da pretensão que você configurou, ou sinalizadas quando as unidades não batem — [`field_map.py`](https://github.com/albertosca/moonlighter/blob/main/packages/apply/moonlighter/application/answers/field_map.py)), declarações de compliance (sempre deixadas para você — [`compliance.py`](https://github.com/albertosca/moonlighter/blob/main/packages/apply/moonlighter/application/answers/compliance.py)) e autodeclaração demográfica (respondida só com o que você escreveu no `profile.yaml`, senão deixada para você). Depois da redação, o [`composer.py`](https://github.com/albertosca/moonlighter/blob/main/packages/apply/moonlighter/application/assisted/composer.py) transforma em lacuna qualquer resposta de texto livre dirigida ao operador ("o candidato deve informar…"); respostas de múltipla escolha não passam por essa checagem. O custo: as guardas reconhecem formulações conhecidas, então uma formulação incomum pode passar por elas — os próprios comentários da regra de salário registram versões anteriores em que isso aconteceu. É mais um motivo para toda folha ser revisada.

### Texto do modelo escapado, nunca validado, no LaTeX do CV

O CV sob medida compila com o `pdflatex` um texto escrito pelo modelo, o que faz desse texto uma superfície de injeção de código. Dois designs anteriores deixavam as traduções do modelo carregarem LaTeX e tentavam validá-lo; os dois foram contornados. O contorno mais instrutivo foi o `^^5c`: o TeX o transforma numa barra invertida durante a tokenização, então nenhuma checagem por uma barra invertida literal o enxerga, e um `\input{...}` podia então embutir um arquivo local no PDF que você envia a um empregador. Agora o [`escape_latex`](https://github.com/albertosca/moonlighter/blob/main/packages/apply/moonlighter/application/cvgen/render.py) reescreve todo caractere especial do TeX, `^` incluído, então não sobra nada para detectar. O custo: a saída do modelo não carrega formatação além de `**negrito**`.

### Cinco fatias com fronteira de import testada e releases em lockstep

Os cinco pacotes do PyPI se instalam cada um sozinho, e um `pip install moonlighter-scan` traz só as dependências que o `pyproject.toml` dele declara. Um import que alcança um pacote não declarado continua funcionando no monorepo e quebra para quem instalou uma fatia só — medido em 14/09/2026 contra o artefato publicado. O [`tests/test_package_boundaries.py`](https://github.com/albertosca/moonlighter/blob/main/tests/test_package_boundaries.py) agora percorre todo import com o módulo `ast` do Python e falha em qualquer um que atravesse uma fronteira não declarada. As versões andam juntas, à mão: o [`scripts/check_version_lockstep.py`](https://github.com/albertosca/moonlighter/blob/main/scripts/check_version_lockstep.py) é o primeiro passo do job de testes do CI, e o workflow de publicação recusa uma tag que não bate com a versão empacotada — porque um upload no PyPI não tem volta.

### 100% de cobertura de branches como gate, gates provados por canários

O `--cov-fail-under=100` está no `pyproject.toml`, então a suíte de testes falha em qualquer branch que nenhum teste executa. O custo é um teste para cada branch novo. Um gate só ganha confiança depois de ser forçado a falhar de propósito (um canário): por exemplo, o lint de segurança (as regras `S` do ruff) só passou a valer como gate bloqueante depois que o CI rejeitou uma chamada com `shell=True` injetada. Uma checagem que nunca falhou pode não estar checando nada.

## O que o modelo nunca responde

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://albertosca.github.io/moonlighter/assets/diagrams/llm-guards-dark.svg">
  <img alt="Antes da redação, perguntas reconhecidas como de salário, compliance ou dados demográficos vão para a sua config ou para você; depois da redação, uma resposta de texto livre dirigida ao operador vira uma lacuna" src="https://albertosca.github.io/moonlighter/assets/diagrams/llm-guards-light.svg">
</picture>

*Dois pontos de controle. Antes da redação, uma pergunta que as guardas reconhecem como de salário, compliance ou dados demográficos recebe o valor que você configurou ou fica como lacuna para você. Depois da redação, uma resposta de texto livre dirigida ao operador vira uma lacuna. Só o resto chega à folha. As guardas reconhecem formulações conhecidas, e no caminho da colagem o modelo ainda lê a página inteira para encontrar as perguntas.*

## Arquitetura

Um [workspace uv](https://docs.astral.sh/uv/concepts/workspaces/) com 5 namespace packages (`moonlighter.*`), organizados por feature:

| Pacote | Namespace | Propósito |
|---------|-----------|---------|
| `moonlighter-core` | `moonlighter.core` | DB (Peewee/SQLite), config, driver de browser opcional (extra `[browser]`), cliente de LLM |
| `moonlighter-scan` | `moonlighter.discovery` | Scrapers de ATS e nota das vagas via LLM |
| `moonlighter-apply` | `moonlighter.application` | Compositor de respostas (perfil curado → respostas via LLM) e resolvedor de autorização de trabalho |
| `moonlighter-email` | `moonlighter.tracking` | Sincronização com o Gmail e classificação das etapas de entrevista |
| `moonlighter` | `moonlighter.server` | Servidor FastMCP — conecta todos os pacotes |

## Gates de qualidade

- **Suíte de testes com 100% de cobertura de branches** — o número atual de testes está na [linha de prova do README](https://github.com/albertosca/moonlighter/blob/main/README.pt.md), conferida pelo CI; a cobertura é imposta como gate de CI (`--cov-fail-under=100`), não é número de dashboard.
- **mypy strict** nos nove módulos `moonlighter.*` (os alvos `--package` do mypy); **ruff** com o ruleset de segurança (`S`) ligado.
- **Releases em lockstep** — os cinco pacotes precisam concordar em versão, pins e tag antes de qualquer upload; a checagem roda antes do build, porque upload no PyPI é irreversível.
- **main protegida** — toda mudança entra por pull request, com o CLA, a suíte de testes e uma auditoria de segurança como checks obrigatórios.
- **Rascunhado do seu perfil, lacunas sinalizadas** — as respostas são rascunhadas a partir do seu perfil, e o modelo é instruído a responder UNKNOWN quando o seu perfil não lhe dá base; isso volta para você como uma lacuna. Alguns campos são decididos em código, não pelo modelo: um salário cujas unidades não batem com a pretensão configurada, ou uma pergunta de autorização de trabalho cujo país não dá para inferir, sempre volta para você como lacuna. O modelo ainda pode errar uma resposta, e é por isso que você revisa toda folha.

[← Voltar ao README](https://github.com/albertosca/moonlighter/blob/main/README.pt.md)
