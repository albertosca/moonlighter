🇺🇸 [English](https://albertosca.github.io/moonlighter/guides/tailored-cv/) · 🇧🇷 [Português](tailored-cv.md)

# CV sob medida para cada vaga

Opcional. Com um banco de bullets curado no lugar, o `prepare_application` também produz um PDF de uma página do seu CV adaptado à vaga, montado a partir de bullets que você escreveu e renderizado pelo seu próprio template LaTeX.

## Como o CV sob medida é montado

Quando existe um banco de bullets curado — `cv-pool.yaml` em `MOONLIGHTER_HOME`, ou onde quer que o `cv.pool` do `config.yaml` aponte —, o `prepare_application` também adapta o seu CV à vaga: uma chamada de LLM seleciona e ordena bullets do seu banco e escreve, a partir do seu perfil, um resumo curto e uma linha de especialidades técnicas (ele também pode responder "o CV base já serve" e não mudar nada), e o resultado renderiza pelo seu próprio template LaTeX e compila com o `pdflatex` quando ele está instalado.

- **Sempre uma página.** O prompt carrega o limite de espaço, e o orquestrador descarta os bullets menos relevantes até o pdflatex reportar uma página só.
- **Sempre texto latino simples.** Um campo do modelo que traga emoji, símbolo ou alfabeto não latino é substituído inteiro pelo seu texto curado, nunca editado.
- **Cargos agrupados.** Cargos consecutivos na mesma empresa renderizam como um bloco só, com o período total, em vez de duas entradas separadas.
- **Seus bullets, não os do modelo.** Todo bullet vem do seu banco; o modelo escolhe e ordena (traduzindo para uma vaga em português) e escreve o resumo e a linha de especialidades técnicas sob a instrução de usar só o seu perfil e nunca inflar uma afirmação. A folha sempre avisa para revisar o PDF gerado antes de fazer o upload.

Sem arquivo de banco, nenhum CV é gerado e nenhuma chamada extra de LLM acontece — mas o `prepare_application` oferece rascunhar um banco para você, devolvendo essa oferta no lugar da folha, até você criar um banco ou dispensar a oferta (veja [Como criar um banco de bullets](#como-criar-um-banco-de-bullets)).

## Configuração e cache

Chaves de config: `cv.pool`, `cv.template_dir` (com `cv-template.en.tex` e, opcionalmente, `cv-template.pt.tex` para vagas em português), `cv.generated_dir` (padrão `cv-generated` dentro de `MOONLIGHTER_HOME`). Os padrões de cada uma estão em [Configuração](../reference/config.md#cv).

O resultado de cada vaga fica em cache em `<generated_dir>/<job_id>/`, então nenhuma vaga é gerada duas vezes — depois de editar o seu banco ou o seu template, apague esse diretório para que o próximo `prepare_application` gere de novo o CV daquela vaga.

## Como criar um banco de bullets

Ainda sem arquivo de banco? O `prepare_application` oferece rascunhar um a partir do seu `profile.yaml` sempre que ele estiver faltando (ou rode `moonlighter-apply bootstrap-cv` num shell) — um primeiro rascunho que você revisa e edita. Ele é montado a partir do [banco de exemplo](https://github.com/albertosca/moonlighter/blob/main/packages/apply/moonlighter/application/cvgen/templates/cv-pool.example.yaml) e do [template de exemplo](https://github.com/albertosca/moonlighter/blob/main/packages/apply/moonlighter/application/cvgen/templates/cv-template.en.example.tex) genéricos, que também servem de referência de schema se você preferir escrever um banco à mão. Os dois também vêm dentro do pacote instalado, em `moonlighter/application/cvgen/templates/`, então você não precisa de um checkout para lê-los.

No Claude, o `bootstrap_cv_pool` rascunha o banco e o `skip_cv_bootstrap` recusa a oferta de vez (veja [Ferramentas MCP](../reference/mcp-tools.md)).

[← Voltar ao README](https://github.com/albertosca/moonlighter/blob/main/README.pt.md)
