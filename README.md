# Laboratorio-03-medicao-de-software

## Lab03S01 — Card 1: seleção de repositórios

Pipeline em Python 3.10+ usando somente a biblioteca padrão. Não requer instalação
de pacotes, PyGithub ou configuração de token em arquivo. Não calcula métricas DORA.

### Execução

Na raiz deste repositório, disponibilize `GITHUB_TOKEN` no ambiente do processo.
O programa lê o token exclusivamente dessa variável e não o inclui nas saídas.
Não salve tokens no repositório. A janela deve ser definida antes do experimento;
o exemplo abaixo é apenas ilustrativo, sem garantia de tamanho da amostra.

```powershell
python -m dora_selection --start 2025-01-01T00:00:00Z --end 2025-12-31T23:59:59Z
```

Datas ISO 8601 com fuso horário, precisão de segundos e limites inclusivos são
obrigatórias. Datas são normalizadas para UTC. Opções:

- `--target`: tamanho desejado, padrão 100, mínimo 100;
- `--min-stars`: mínimo de estrelas, padrão 1001;
- `--output`: diretório de saída, padrão `outputs/card1`.

A execução para quando alcança a meta ou esgota os candidatos. Retorna código 0
quando alcança a meta e 1 quando há erro de busca ou amostra insuficiente. Erros
em um repositório geram exclusão `collection_error` e não interrompem os demais.
Erros globais de busca são registrados no funil, com persistência da amostra parcial.
Reexecutar no mesmo diretório substitui os arquivos anteriores; use diretórios
diferentes para experimentos diferentes.

### Regras e saídas

- Busca pública pela API REST oficial, ordenada por estrelas. Faixas acima de
  1000 resultados são subdivididas por estrelas e, se necessário, por criação.
  IDs removem duplicatas; nomes são alternativa quando não há ID.
- Actions é verificado pela existência de workflows registrados no endpoint
  `/actions/workflows`. Workflows desativados também indicam uso de Actions;
  workflows apagados historicamente não são reconstruídos neste card.
- Releases válidas: `draft=false`, `prerelease=false`, `published_at` na janela.
- Runs válidos: `head_branch=default_branch`, evento `push`, `created_at` na
  janela, status `completed`, conclusão `success`, `failure`, `timed_out` ou
  `startup_failure`. As demais conclusões e runs em andamento são ignorados.
- Inclusão: Actions, pelo menos 5 releases e 50 runs válidos, e coleta sem erro.
  Contagens são completas, não apenas interrompidas no limiar. Consultas de
  runs acima de 1000 resultados são subdivididas por tempo e IDs deduplicados.
  Uma faixa indivisível saturada gera erro explícito em vez de contagem truncada.
- Contribuidores: `anon=true`, `per_page=1`, quantidade pela última página do
  header `Link`; sem `last`, paginação completa se houver `next`. É a contagem
  disponibilizada pelo endpoint do GitHub, inclusive contribuidores anônimos,
  sujeita à atualização/cache do próprio serviço.
- Linguagem nula é permitida; dados essenciais ausentes impedem inclusão.

Arquivos em `outputs/card1` (ignorados pelo Git):

| Arquivo | Conteúdo |
| --- | --- |
| `repositories.json` / `.csv` | Todos os candidatos únicos avaliados, metadados, valores dos filtros, inclusão, motivo e erro |
| `selected.json` / `.csv` | Apenas os repositórios incluídos |
| `funnel.json` | Etapas cumulativas, exclusões por motivo, janela, meta, resultado e motivo de parada |

O funil conta os candidatos efetivamente percorridos, e não todos os resultados
potenciais da API. `candidates_found` inclui duplicatas recebidas nas páginas
percorridas; `unique_repositories` conta os candidatos únicos avaliados.
As etapas são cumulativas: Actions → releases suficientes → runs suficientes →
incluídos. Cada descarte recebe um motivo principal, nesta ordem; erros de coleta
prevalecem. Dados ainda não coletados são `null`, não zero. Não há números de
amostra hardcoded. Nenhum cache, retomada ou backoff foi acrescentado.

### Organização

- `dora_selection/api.py`: HTTP, autenticação, erros e paginação por `Link`;
- `dora_selection/search.py`: particionamento de busca e deduplicação;
- `dora_selection/selection.py`: coleta, classificação, filtros e funil;
- `dora_selection/output.py`: persistência JSON/CSV;
- `dora_selection/__main__.py`: execução e configuração;
- `tests/test_card1.py`: testes offline com mocks e dados sintéticos.

### Testes

```powershell
python -m unittest discover -s tests -v
```

Os testes cobrem inclusão/exclusão, conclusões de runs, branch/evento/janela,
releases, contribuidores, funil, paginação, deduplicação, faixas de estrelas/datas,
subdivisão de runs, erros HTTP, token obrigatório, saída e seleção de 100
repositórios simulados. A obtenção de 100 repositórios reais depende de uma janela
com candidatos suficientes, credenciais e limites da API; não é comprovada pelos
testes offline. Tratamento completo de rate limit pertence a outro card.

Referências oficiais:
[busca](https://docs.github.com/en/rest/search/search#search-repositories),
[paginação](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api),
[workflow runs](https://docs.github.com/en/rest/actions/workflow-runs#list-workflow-runs-for-a-repository),
[releases](https://docs.github.com/en/rest/releases/releases#list-releases),
[contribuidores](https://docs.github.com/en/rest/repos/repos#list-repository-contributors).

## Lab03S01 — Card 2: releases, tags e commits entre releases

Reutiliza o cliente REST, `GITHUB_TOKEN`, o paginador por `Link`, a janela UTC e
os testes com `unittest` do Card 1. Não calcula Lead Time nem outras métricas DORA.

### Execução

Após gerar a amostra do Card 1, execute na raiz do repositório:

```powershell
python -m dora_selection.deployments --input outputs/card1/selected.json --start 2025-01-01T00:00:00Z --end 2025-12-31T23:59:59Z
```

Use a mesma janela do experimento. `--input` aceita a lista JSON do Card 1;
registros com `included=false` são ignorados. Repositórios repetidos são removidos.
`--output` define a pasta base (padrão `outputs/card2`). `--tag-dates` consulta
também `commit.author.date` do commit apontado por cada tag; sem essa opção,
o SHA é coletado e `commit_author_date` permanece `null`. SHAs compartilhados
entre tags usam uma única consulta de data por repositório.

### Definição dos pares e dados

- Releases são paginadas e filtradas pelo `published_at` na janela inclusiva.
  São armazenados `release_id`, `tag_name`, `published_at`, `draft` e `prerelease`.
- Drafts são descartados e contabilizados; drafts sem publicação não têm data
  para filtragem, então `drafts_excluded` conta os drafts recebidos na listagem.
- Pré-releases da janela ficam em `prereleases`, disponíveis para análises futuras,
  e não entram nos pares nem na contagem principal.
- Releases válidas da janela são ordenadas por `published_at`, com desempate por
  ID. A primeira recebe `no_previous_release`; não há busca de release anterior
  fora da janela. Cada par seguinte associa a release anterior à atual.
- Tags de todo o repositório são paginadas e associadas ao SHA retornado pelo
  endpoint `/tags`. Releases recebem esse SHA quando a tag aparece na listagem.
- Compare usa os SHAs das tags quando disponíveis e os nomes das tags como
  alternativa. Referências são codificadas na URL, inclusive tags com `/`.
- A chamada `/compare/{base}...{head}` começa com `page=1&per_page=100`, segue
  todos os links `next` e deduplica commits pelo SHA dentro de cada par.
  Commits não são filtrados por data: todos os commits retornados pelo compare
  pertencem à coleta, inclusive os escritos antes da janela.
- Cada commit armazena `sha`, `author_date` (exatamente `commit.author.date`),
  `message`, `repository`, `release_id` e `release_tag_name`. As datas não são
  substituídas por `commit.committer.date`.
- Comparações vazias são válidas. Falhas 404 recebem `not_found`; outros erros
  recebem `error`. Ambas incrementam `releases_ignored_comparison_error`.
  Uma comparação incompleta não publica commits parciais como dados completos.
  O próximo par usa a release imediatamente anterior mesmo após erro.
- Erros são armazenados por etapa. Erro de listagem de releases impede comparação
  daquele repositório, pois a sequência poderia estar incompleta. Erros de tags
  não impedem tentar compare pelos nomes. Os demais repositórios continuam.

### Saídas e testes

Cada execução cria uma pasta exclusiva `outputs/card2/run-*`, sem sobrescrever
arquivos do Card 1 ou execuções anteriores. O caminho é informado no terminal.

| Arquivo | Conteúdo |
| --- | --- |
| `deployments.json` | Lista de repositórios com `releases`, `prereleases`, `tags`, `errors` e resumo individual; commits aninhados na release correspondente |
| `summary.json` | Janela, quantidade de repositórios, repositórios com erro e total de releases ignoradas por erro de comparação |

O comando retorna 0 quando não há erros registrados e 1 quando há erros de coleta
ou persistência. Um 404 permite continuar e salvar os dados, mas sinaliza resultado
parcial pelo código 1. Entrada ou configuração inválida retorna código 2.

Arquivos do Card 2: `dora_selection/deployments.py` (coleta e comando), extensão de
`dora_selection/output.py` (saída exclusiva) e `tests/test_card2.py`.
`APIError` passou a disponibilizar `status_code`, preservando sua mensagem e
compatibilidade com o Card 1.

Execute a mesma suíte completa:

```powershell
python -m unittest discover -s tests -v
```

Os testes do Card 2 verificam filtros, pré-releases, ordenação e pares, primeira
release, tags e datas, associação repositório/release/commit, 404, falha em página
posterior, continuidade entre repositórios e persistência sem sobrescrita.
O teste com 301 commits exercita o paginador real com respostas simuladas, incluindo
paginação de releases e tags. A integração com o GitHub real não é validada por
esses testes offline.

Referências:
[compare e paginação de commits](https://docs.github.com/en/rest/commits/commits#compare-two-commits),
[tags](https://docs.github.com/en/rest/repos/repos#list-repository-tags),
[commit e data do autor](https://docs.github.com/en/rest/commits/commits#get-a-commit).

## Lab03S01 — Card 3: coleta e classificação de workflow runs

Este card reutiliza `selection.py`, `output.py`, `__main__.py` e o cliente REST
existente. O único arquivo novo é `tests/test_card3.py`. O comando do Card 1
continua sendo o padrão; `--card 3` executa a coleta da amostra selecionada:

```powershell
python -m dora_selection --card 3 --input outputs/card1/selected.json --start 2025-01-01T00:00:00Z --end 2025-12-31T23:59:59Z
```

O token continua vindo exclusivamente de `GITHUB_TOKEN`. A entrada é a lista JSON
do Card 1, com `full_name` e `default_branch`. Repositórios excluídos são ignorados;
nomes repetidos são removidos sem diferenciar maiúsculas e minúsculas. Branch
ausente gera erro registrado para o repositório, sem escolher outro branch.
Use a janela do laboratório, com fuso e precisão de segundos.

### Coleta e classificação

- A janela é dividida em meses de calendário UTC. O primeiro/último mês pode ser
  parcial; os limites são inclusivos, sem sobreposição entre meses.
- Cada consulta filtra `branch=default_branch`, `event=push` e `created`.
  Os dados recebidos também são verificados por branch, evento e janela.
- O paginador existente percorre os links `next` com `per_page=100`.
- Períodos com 1000 ou mais resultados são subdivididos recursivamente por tempo.
  O limiar exato de 1000 também é tratado conservadoramente como saturação.
  Caso um único segundo permaneça saturado, a coleta registra erro explícito.
- A quantidade de IDs únicos em cada subconsulta é conferida contra `total_count`.
  Divergência, incluindo alteração dos dados durante a paginação, torna o mês
  incompleto e exige nova execução. Não há truncamento silencioso.
- Um mês só é publicado depois de suas páginas e subconsultas terminarem.
  Falha descarta o buffer daquele mês, preserva os meses completos e continua.
- IDs são deduplicados por repositório entre páginas, subconsultas e meses.
- Cada execução persiste `id`, `workflow_id`, `name`, `conclusion`, `status`,
  `run_started_at`, `updated_at`, `created_at`, `branch`, `event`, `repository`
  e `classification`. Nome e timestamps opcionais ausentes ficam `null`.

| Classificação persistida | Regra |
| --- | --- |
| `success` | Status `completed`, conclusão `success` |
| `failure` | Status `completed`, conclusão `failure`, `timed_out` ou `startup_failure` |
| `ignored` | `cancelled`, `skipped`, `neutral`, `action_required`, `stale`, conclusão vazia/desconhecida ou run ainda em andamento |

Runs ignorados são mantidos com sua classificação para análises futuras.
A classificação reutiliza `classify_run`, preservando os filtros do Card 1.
Não são calculados CFR, tempo de recuperação ou quaisquer métricas DORA.
Não foram acrescentados cache avançado, rate limit ou backoff.

### Persistência e testes

O diretório padrão é `outputs/card3`, alterável com `--output`.
Cada execução cria uma pasta exclusiva `run-*`, sem sobrescrever outras coletas.

| Arquivo | Conteúdo |
| --- | --- |
| `workflow_runs.json` | Repositórios → workflows → runs, com resumo por classificação, períodos, erros e indicador `complete` |
| `summary.json` | Janela, repositórios, contagens de runs/classificações, repositórios com erros e indicador global `complete` |

Contagens de resultados incompletos representam somente os meses concluídos.
Erros aparecem também no stderr. Código de saída 0 indica coleta sem erros;
1 indica coleta incompleta ou falha de persistência; 2 indica configuração inválida.

```powershell
python -m unittest discover -s tests -v
```

Testes offline validam filtros, campos e associação, todas as classificações,
paginação real com respostas simuladas, meses/ano bissexto/UTC, subdivisão de
períodos saturados, divergência de contagem, deduplicação, continuidade após erro,
comando e persistência sem sobrescrita. Integração real com o GitHub depende das
credenciais, da janela e dos limites do serviço e não é validada pelos mocks.

Referência oficial:
[listar workflow runs e limite de consultas filtradas](https://docs.github.com/en/rest/actions/workflow-runs#list-workflow-runs-for-a-repository).
