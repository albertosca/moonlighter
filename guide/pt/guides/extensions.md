🇺🇸 [English](https://albertosca.github.io/moonlighter/guides/extensions/) · 🇧🇷 [Português](extensions.md)

# Extensões: como adicionar um novo scanner de ATS

Toda integração de ATS embutida (Greenhouse, Lever, Ashby, Recruitee, Workable, SmartRecruiters, InHire) e todo feed de portal (RemoteOK, Remotive, WeWorkRemotely, HN Who's Hiring, Gupy) é parte normal deste repositório — mas o moonlighter também suporta **extensões de scanner**: pacotes Python separados, instalados de forma independente, que registram uma nova fonte de vagas sem precisar dar fork ou modificar este repositório de jeito nenhum.

É assim que o scan do LinkedIn é distribuído — não porque o mecanismo seja específico do LinkedIn, mas porque os próprios Termos de Uso do LinkedIn proíbem automação de forma explícita e inequívoca (veja o [DISCLAIMER.md](https://github.com/albertosca/moonlighter/blob/main/DISCLAIMER.md), em inglês), então essa integração é distribuída como uma extensão opcional em vez de código embutido que qualquer um que clonar este repositório já ganha por padrão.

Preenchimento e envio de formulário via browser não fazem parte deste repositório de jeito nenhum (veja [como funciona](../index.md)) e não são um ponto de extensão — o `prepare_application` compõe as respostas para você colar, para qualquer ATS.

## Como funciona uma extensão

Uma extensão é um pacote Python normal que:

1. Depende de `moonlighter-core` e `moonlighter-scan`, fixados numa tag publicada deste repositório.
2. Traz o próprio módulo implementando uma subclasse de `BaseScanner` (veja [`packages/scan/moonlighter/discovery/sources/base.py`](https://github.com/albertosca/moonlighter/blob/main/packages/scan/moonlighter/discovery/sources/base.py)).
3. Se declara via `entry_points` no próprio `pyproject.toml` — nenhum código deste repositório importa ou cita a extensão:

    ```toml
    [project.entry-points."moonlighter.scanners"]
    my_platform = "my_package.my_module:MyScanner"

    # Optional: a browser-based staleness check for a source with no listing API
    [project.entry-points."moonlighter.staleness_checkers"]
    my_platform = "my_package.my_module:check_staleness"
    ```

    Um scanner baseado em browser (como costumam ser as entradas de `moonlighter.scanners`) precisa de `moonlighter-core[browser]` — veja [Requisitos](../getting-started/install.md#requisitos); um scanner puramente HTTP não precisa de nada extra.

4. Precisa estar presente no **mesmo** ambiente Python de onde o moonlighter roda, para que seus entry points sejam descobertos em tempo de execução. Se você instalou o moonlighter via `uvx moonlighter`, não existe um ambiente persistente onde adicionar um pacote — use uma das opções:
    - `uvx --with my-extension-package moonlighter` — efêmero, por invocação
    - `uv tool install moonlighter --with my-extension-package` — instalação persistente da ferramenta

    Se você está desenvolvendo direto neste repositório, `uv add --editable`/`pip install` do pacote da sua extensão no mesmo ambiente continua funcionando como antes. Em tempo de execução, `moonlighter.core.plugins.discover_entry_points`/`discover_entry_points_by_name` enumeram o que estiver registrado em cada grupo — um ambiente sem nenhuma extensão instalada se comporta exatamente como antes (lista/dict vazio, nada quebra).

Como o pacote de nível raiz `moonlighter` é um [namespace package PEP 420](https://peps.python.org/pep-0420/) (sem `__init__.py` nesse nível), uma extensão pode até trazer o próprio subpacote de nível raiz (ex.: `moonlighter/my_extension/`), que convive com `moonlighter.core`/`moonlighter.discovery`/etc. Só não coloque arquivos *dentro* de um subpacote já existente, como `moonlighter/discovery/sources/`: esse é um pacote regular (não namespace) que pertence inteiramente às distribuições deste repositório, e uma segunda distribuição escrevendo no mesmo caminho colide silenciosamente na instalação. Dê à sua extensão o próprio diretório de nível raiz.

## Exemplo real

A extensão privada `moonlighter-linkedin` (não publicada, pelo motivo acima) segue exatamente esse padrão para o scan — o `LinkedInScanner` dela vive no próprio pacote `moonlighter/linkedin_ext/`, registrado pelo grupo de entry points `moonlighter.scanners` acima. Se você for construir a sua própria extensão de scanner, essa é a forma de referência a copiar.

[← Voltar ao README](https://github.com/albertosca/moonlighter/blob/main/README.pt.md)
