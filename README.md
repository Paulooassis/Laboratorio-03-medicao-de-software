# Laboratorio-03-medicao-de-software

![Testes](https://github.com/Paulooassis/Laboratorio-03-medicao-de-software/actions/workflows/tests.yml/badge.svg)

## Como executar

Do zero até o dataset final com as métricas DORA dos 300 repositórios. As seções dos
cards, mais abaixo, detalham as regras de cada etapa; aqui está só o necessário para rodar.

### 1. Instalação

Requer Python 3.10 ou superior. PyYAML lê a configuração do pipeline; as demais
dependências servem aos testes, à validação da amostra-ouro (statsmodels,
scikit-learn e ijson) e às análises estatísticas da Sprint 3 (`pandas`, `scipy` e
`matplotlib`, para `python -m analise`).

```bash
git clone https://github.com/Paulooassis/Laboratorio-03-medicao-de-software.git
cd Laboratorio-03-medicao-de-software
python -m venv .venv
source .venv/bin/activate          # Windows (PowerShell): .venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

### 2. Token do GitHub

O token é lido exclusivamente da variável de ambiente `GITHUB_TOKEN`. Ele não é
aceito por argumento nem por arquivo de configuração e não aparece em saídas, cache
ou log.

1. Crie um token em <https://github.com/settings/tokens>. Só são lidos dados
   públicos: um token clássico sem nenhum escopo marcado é suficiente.
2. Exporte-o no terminal em que o pipeline será executado:

```bash
export GITHUB_TOKEN=ghp_seu_token      # Linux/macOS
```

```powershell
$env:GITHUB_TOKEN = "ghp_seu_token"    # Windows (PowerShell)
```

Para não digitar o token a cada sessão, copie `.env.example` para `.env`, preencha e
carregue com `set -a; source .env; set +a`. O `.env` está no `.gitignore`, assim como
`outputs/`; nunca coloque um token em arquivo versionado.

### 3. Pipeline

Um único comando executa seleção, metadados, releases e commits, workflow runs,
métricas em todas as variantes, classificação e a gravação do dataset final:

```bash
python -m pipeline --config config.yaml
```

A seção `coleta` do `config.yaml` guarda as decisões do experimento, que devem ser as
mesmas para todo o grupo:

| Chave | Valor | Efeito |
| --- | --- | --- |
| `inicio`, `fim` | 2025-01-01 a 2025-12-31 (UTC) | Janela inclusiva, ISO 8601 com fuso e precisão de segundos |
| `alvo` | `300` | Quantidade de repositórios a selecionar |
| `min_estrelas` | `1001` | Mínimo de estrelas dos candidatos |
| `saida` | `outputs/pipeline` | Dados brutos, cache e diários (fora do Git) |
| `processados` | `data/processed` | Dataset final em CSV |
| `tipo_projeto` | `validacao/resultados/tipo_projeto.csv` | Tipo do projeto consensual da amostra-ouro (S2-06) |
| `workers` | `4` | Consultas simultâneas dentro de cada repositório |
| `variantes` | `true` | Coleta também as unidades de deploy da RQ 07 (release + pré-release e tag) e grava `variantes.csv` e `deploys_variantes.csv`; `false` pula a etapa |

A seção `heuristica_corretiva` registra a versão aprovada em S2-08, usada no CFR (b).
Caminhos relativos valem a partir da pasta em que o comando é executado (a raiz do
repositório). Com o cache já preenchido o mesmo comando não faz nenhuma chamada à API
e regrava os mesmos CSVs em cerca de dois minutos para os 300 repositórios, usando
perto de 11 GB de memória; `GITHUB_TOKEN` ainda precisa estar definido.

`python -m pipeline` repassa as demais opções a `python -m dora_selection.pipeline`,
e o que vier na linha de comando prevalece sobre o arquivo. Nesse comando `--start` e
`--end` são obrigatórios e as outras opções têm padrão:

| Opção | Padrão | Efeito |
| --- | --- | --- |
| `--target` | `100` | Quantidade de repositórios a selecionar |
| `--min-stars` | `1001` | Mínimo de estrelas dos candidatos |
| `--output` | `outputs/pipeline` | Pasta de saída, com cache e diários |
| `--processed` | `<output>/processed` | Pasta do dataset final em CSV |
| `--project-types` | nenhum | CSV `repository,project_type` da amostra-ouro |
| `--tag-dates` | desligado | Consulta também a data do commit de cada tag |
| `--workers` | `4` | Consultas simultâneas dentro de cada repositório; `1` desliga o paralelismo |
| `--variants` | desligado | Coleta também as unidades de deploy da RQ 07 (veja [#41](#lab03s03--41-unidades-de-deploy-da-rq-07)) |
| `--state` | `<output>/state` | Pasta dos diários de retomada, um por etapa |

As opções de cache, retry e rate limit do Card 4 (`--cache-dir`, `--no-cache`,
`--cache-ttl`, `--no-resume`, `--max-attempts`, `--backoff`, `--max-backoff`,
`--max-wait`, `--rate-limit-reserve`, `--log-file`) valem aqui com os mesmos padrões.

Etapas, na ordem:

1. **Seleção e metadados** (Card 1): percorre os repositórios públicos por estrelas
   até reunir `--target` que atendam aos critérios.
2. **Releases, tags e commits** (Card 2) dos selecionados.
3. **Workflow runs** (Card 3) dos selecionados.
4. **Métricas, classificação DORA e dataset final** (Cards 5 e 6, S2-07 e S2-10), sem rede.

A coleta dos 300 repositórios fez cerca de 32 mil chamadas, levou perto de 6 horas e
ocupa 40 GB de cache. Confira o espaço em disco antes de começar. O
limite é a cota da API, de 5000 chamadas por hora: quando ela acaba, o programa
aguarda sozinho o reset e continua. Para chegar perto desse limite sem desperdício:

- cada filtro da seleção só é consultado se o anterior passou (sem Actions não se
  consultam releases; com menos de 5 releases não se consultam runs);
- os workflow runs são baixados uma única vez: a seleção faz as mesmas consultas
  mensais da etapa 3, que então vem inteira do cache;
- dentro de um repositório, os meses de runs e as comparações entre releases são
  consultados em paralelo (`--workers`), sempre poucos por vez, como o GitHub pede;
- as respostas trafegam comprimidas (gzip).

Na coleta de commits, pares de releases com as mesmas referências compartilham
uma única comparação, preservando os identificadores de cada release na saída.
Tags com SHA idêntico não precisam consultar compare: o conjunto de commits entre
elas é vazio. O log informa o número de pares e de consultas únicas por repositório.
O ganho depende da quantidade de referências repetidas; pares distintos ainda
exigem paginação completa para calcular as métricas corretamente.

Cache e diários serializam cada registro JSON em bloco, sem espaços entre campos,
reduzindo o custo de escrita. As respostas completas e as garantias de escrita
atômica do cache são preservadas; os arquivos antigos continuam compatíveis.
Isso melhora o processamento local, sem reduzir a quantidade de chamadas à API.

O progresso aparece no console e em `collection.log`, uma linha por repositório
concluído. A coleta pode ser interrompida com `Ctrl+C` a qualquer momento: repetir
**o mesmo comando** retoma do ponto em que parou, sem refazer chamadas já
respondidas. Para validar a instalação antes da coleta completa, use uma amostra
pequena em outra pasta (cerca de dois minutos):

```bash
python -m pipeline --config config.yaml --target 3 --output outputs/smoke --processed outputs/smoke/processed
```

O comando termina com código 0 quando a meta é atingida e a coleta de todos os
repositórios está completa. Termina com 1 quando a amostra fica abaixo da meta, há
erro de busca, algum repositório ficou com coleta incompleta ou a execução foi
interrompida; `summary.json` informa qual foi o caso em `status` e `stage`. Com
amostra abaixo da meta as métricas são calculadas mesmo assim, sobre o que foi
selecionado. Falha ao comparar duas releases (tag apagada, por exemplo) não conta
como coleta incompleta: é o caso especial `comparison_unavailable` do Card 6.

### 4. Testes e cobertura

```bash
python -m pytest
```

Os testes são offline: não usam rede nem token real. O comando já mede a cobertura
de `dora_selection/metrics.py`, `dora_selection/rating.py`, `dora_selection/cfr.py`,
`dora_selection/dataset.py`
e `validacao/`, lista as linhas não
cobertas e **falha se a cobertura ficar abaixo de 80%** (configuração em
`pyproject.toml`). Variações úteis:

```bash
python -m pytest tests/test_card7.py            # só métricas e classificação
python -m pytest --cov=dora_selection           # cobertura do pacote inteiro
python -m pytest --cov-report=html              # relatório navegável em htmlcov/
python -m pytest --no-cov -k recovery           # um subconjunto, sem o limite de cobertura
```

O limite vale para a execução inteira; rodar um arquivo isolado que não exercita as
métricas reprova por cobertura, e `--no-cov` evita isso. As fixtures compartilhadas
ficam em `tests/conftest.py`: uma amostra pequena cujos resultados são calculáveis à
mão (1 release por semana, Lead Time mediano de 24 h por commit e 36 h por release,
Change Failure Rate de 0,5, recuperação mediana de 4 h e uma falha não recuperada).

O workflow `.github/workflows/tests.yml` executa o mesmo `python -m pytest` em todo
`push` e `pull_request`, em Python 3.10 e 3.12; cobertura abaixo de 80% reprova o job.

### 5. Dados e cache

O dataset final fica em `data/processed`, com cada coluna documentada no
[dicionário de dados](docs/dicionario_de_dados.md) e descrito na seção
[S2-10](#lab03s02--s2-10-métricas-em-todas-as-variantes-e-dataset-final). Os dados
brutos ficam na pasta de saída (`outputs/pipeline` por padrão), ignorada pelo Git:

| Caminho | Conteúdo |
| --- | --- |
| `selection/repositories.json` / `.csv` | Todos os candidatos avaliados, com metadados, filtros e motivo de exclusão |
| `selection/selected.json` / `.csv` | Os repositórios incluídos na amostra |
| `selection/funnel.json` | Funil da seleção |
| `deployments.json` | Por repositório: `releases` (cada uma com seus `commits`), `prereleases`, `tags`, `errors` |
| `workflow_runs.json` | Por repositório: `workflows` (cada um com seus `runs` classificados), `periods`, `errors` |
| `metrics.json` | Resultado de `repository_metrics` de cada repositório (Card 5) |
| `classification.json` | Resultado de `classify_repository` de cada repositório (Card 6) |
| `dora.csv` | Uma linha por repositório: metadados, valor de cada métrica e classificações |
| `summary.json` | Janela, situação da execução, totais por etapa, medianas da amostra, distribuição das classificações, censura (`dataset.censoring`), casos de escala (`collection_checks`) e uso da API |
| `collection.log` | Erros, esperas por cota e novas tentativas |
| `state/<etapa>.jsonl` | Diários de retomada: uma linha por unidade concluída |
| `cache/<2 hex>/<sha256>.json` | Uma resposta da API por arquivo |

- `dora.csv` é a tabela para análise: `releases_per_week`, `commit_lead_time_hours`,
  `release_lead_time_hours`, `change_failure_rate`, `recovery_hours`, o nível de cada
  métrica (`*_level`) e a classificação geral (`overall`). Célula vazia significa
  métrica sem amostra, não zero; o motivo está em `classification.json`.
  `collection_complete` indica se releases e workflow runs do repositório foram
  coletados sem erro.
- Cada arquivo do cache guarda `url` (normalizada, sem o token), `stored_at`, `data`
  e o header `Link`. A chave é o SHA-256 da URL, e as etapas compartilham o mesmo
  cache: releases e runs lidos na seleção não são pedidos de novo depois. Respostas
  de erro não são gravadas. O cache não expira por padrão (`--cache-ttl`).
- Os diários guardam o resultado de cada candidato ou repositório já concluído e
  pertencem a uma janela: usar outra janela na mesma pasta é recusado. Para um novo
  experimento, use outro `--output`; para recoletar tudo, apague a pasta ou use
  `--no-resume --no-cache`.
- Os arquivos de dados são regravados a cada execução na mesma pasta.

Os comandos por etapa (`python -m dora_selection` e `python -m dora_selection.deployments`),
descritos nas seções a seguir, continuam disponíveis e gravam em `outputs/card1` a
`outputs/card3`.

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
Reexecutar no mesmo diretório substitui os arquivos anteriores e retoma a coleta
pelo diário do Card 4; use diretórios diferentes para experimentos diferentes.

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
  Os filtros são consultados nessa ordem e a coleta do candidato para no primeiro
  que falha: os valores não consultados ficam `null`. Contagens feitas são
  completas, não apenas interrompidas no limiar. Os runs são consultados mês a mês,
  com as mesmas consultas do Card 3 e a contagem conferida com a da API. Consultas
  acima de 1000 resultados são subdivididas por tempo e IDs deduplicados.
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
amostra hardcoded. Cache, retomada, rate limit e backoff estão no Card 4 e
valem para este comando sem alterar as regras de seleção.

### Organização

- `dora_selection/api.py`: HTTP, autenticação, erros e paginação por `Link`;
- `dora_selection/search.py`: particionamento de busca e deduplicação;
- `dora_selection/selection.py`: coleta, classificação, filtros e funil;
- `dora_selection/output.py`: persistência JSON/CSV;
- `dora_selection/__main__.py`: execução e configuração;
- `tests/test_card1.py`: testes offline com mocks e dados sintéticos.

### Testes

```powershell
python -m pytest
```

Os testes cobrem inclusão/exclusão, conclusões de runs, branch/evento/janela,
releases, contribuidores, funil, paginação, deduplicação, faixas de estrelas/datas,
subdivisão de runs, erros HTTP, token obrigatório, saída e seleção de 100
repositórios simulados. A obtenção de 100 repositórios reais depende de uma janela
com candidatos suficientes, credenciais e limites da API; não é comprovada pelos
testes offline. O tratamento de rate limit e de erros temporários está no Card 4.

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
  ID. Cada uma é comparada com a release anterior, que para a primeira da janela é
  a última release (não draft, não pré-release) publicada antes dela, mesmo fora da
  janela, como define o enunciado. Só recebe `no_previous_release` a primeira
  release da história do repositório.
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
python -m pytest
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
Cache, retomada, rate limit e backoff são fornecidos pelo Card 4.

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
python -m pytest
```

Testes offline validam filtros, campos e associação, todas as classificações,
paginação real com respostas simuladas, meses/ano bissexto/UTC, subdivisão de
períodos saturados, divergência de contagem, deduplicação, continuidade após erro,
comando e persistência sem sobrescrita. Integração real com o GitHub depende das
credenciais, da janela e dos limites do serviço e não é validada pelos mocks.

Referência oficial:
[listar workflow runs e limite de consultas filtradas](https://docs.github.com/en/rest/actions/workflow-runs#list-workflow-runs-for-a-repository).

## Lab03S01 — Card 4: cache, retomada, rate limit e tratamento de erros

Infraestrutura de resiliência da coleta, aplicada aos três comandos anteriores sem
mudar nenhuma regra de seleção, classificação ou pareamento. Continua usando apenas
a biblioteca padrão e `GITHUB_TOKEN`. Não calcula métricas DORA.

### Execução

As mesmas opções existem em `python -m dora_selection` (Cards 1 e 3) e em
`python -m dora_selection.deployments` (Card 2). Os padrões já ativam cache,
retomada e log; nada precisa ser informado para obter o comportamento resiliente:

```powershell
python -m dora_selection --card 3 --input outputs/card1/selected.json --start 2025-01-01T00:00:00Z --end 2025-12-31T23:59:59Z
```

| Opção | Padrão | Efeito |
| --- | --- | --- |
| `--cache-dir` | `<output>/cache` | Diretório das respostas gravadas |
| `--no-cache` | desligado | Não consulta nem grava cache |
| `--cache-ttl` | `0` | Validade em segundos; `0` não expira |
| `--state` | `<output>/state.jsonl` | Diário de retomada |
| `--no-resume` | desligado | Recoleta tudo, ignorando o diário |
| `--max-attempts` | `5` | Tentativas por chamada, incluindo a primeira |
| `--backoff` | `1.0` | Base do backoff exponencial em segundos |
| `--max-backoff` | `60.0` | Teto de cada espera do backoff |
| `--max-wait` | `3600.0` | Espera máxima aceita por reset de cota |
| `--rate-limit-reserve` | `0` | Chamadas mantidas de reserva na cota |
| `--log-file` | `<output>/collection.log` | Arquivo de log, além do stderr |

Apontar `--cache-dir` para o mesmo diretório em execuções e cards diferentes
reaproveita as respostas já obtidas. O diário, ao contrário, é por experimento.

### Cache local

- A consulta ao cache acontece antes de qualquer chamada; o acerto devolve os
  mesmos `(dados, headers)` e não consome cota nem tempo de rede.
- A chave é o SHA-256 da URL normalizada, com os parâmetros ordenados, de modo que
  a ordem em que a consulta foi montada não cria entradas duplicadas.
- O token viaja em header e nunca entra na chave nem no arquivo gravado.
- Só o header `Link` é guardado, o que preserva a paginação a partir do cache.
  Cota e datas de uma resposta antiga não são reaproveitadas como se fossem atuais.
- A gravação é feita em arquivo temporário no mesmo diretório e concluída com
  `os.replace`, operação atômica: uma interrupção não deixa entrada pela metade.
- Entrada ausente, ilegível, truncada ou expirada conta como ausência, é registrada
  em log e provoca nova chamada. Respostas de erro não são gravadas.

### Retomada

- Cada unidade concluída é gravada como uma linha JSON no diário, com `flush` e
  `fsync`, antes de a execução seguir para a próxima. O arquivo é append-only.
- A unidade é o repositório, em minúsculas: a mesma granularidade das três coletas.
  Card 1 considera concluído o repositório avaliado sem erro; Card 2, o repositório
  sem erro em nenhuma etapa; Card 3, o repositório com todos os meses completos.
- Na retomada, unidades concluídas são reaproveitadas e suas chamadas não são
  repetidas. Unidades com erro são refeitas, aproveitando o cache das chamadas que
  já tinham terminado, de forma que a repetição custa pouco e nada é perdido.
- Resultados gravados na execução atual não substituem a coleta em andamento;
  apenas o diário lido no início vale como retomada.
- A primeira linha guarda a configuração (card, janela e `--min-stars` no Card 1).
  Um diário de outra configuração é recusado com erro, em vez de misturar amostras.
- Uma interrupção só pode truncar a última linha, que é descartada com aviso e
  removida do arquivo; as anteriores continuam válidas.
- `Ctrl+C` é tratado: a coleta para, o parcial é persistido normalmente e o código
  de saída é 1. A execução seguinte continua de onde parou.

### Rate limit, erros e log

- `X-RateLimit-Remaining` e `X-RateLimit-Reset` são lidos em toda resposta,
  inclusive nas de erro, sem distinção de maiúsculas no nome do header.
- Quando o restante chega a `--rate-limit-reserve`, a próxima chamada espera até o
  reset informado, com um segundo de margem, e só então é enviada.
- `403` e `429` com `Retry-After` ou com cota esgotada são esperas, não falhas: a
  chamada é repetida depois do tempo pedido. `403` sem sinal de cota, como falta de
  permissão, é erro definitivo e não é repetido.
- Espera maior que `--max-wait` gera erro explícito em vez de travar a execução.
- Erros `5xx` e falhas de conexão, timeout ou DNS são repetidos com backoff
  exponencial `--backoff * 2 ** (tentativa - 1)`, limitado por `--max-backoff`.
- `--max-attempts` conta a primeira tentativa. Esgotadas as tentativas, a chamada
  falha com `APIError`, que os cards já tratam por repositório sem parar os demais.
- Demais erros `4xx` e JSON inválido falham na hora, porque repetir não muda a
  resposta.
- Esperas, novas tentativas e erros vão para o stderr e para o arquivo de log.
  O log é aberto antes da coleta, de modo que um erro de configuração já aparece.

### Saídas e testes

`funnel.json` (Card 1) e `summary.json` (Cards 2 e 3) passam a trazer o bloco
`api` com `requests`, `cache_hits`, `cache_misses`, `cache_entries_written`,
`cache_directory`, `retries`, `rate_limit_waits`, `rate_limit_remaining`,
`rate_limit_reset` e `resumed_units`. O Card 1 ganha o motivo de parada
`interrupted`. Os demais arquivos e campos continuam iguais aos dos cards anteriores.

Arquivos do Card 4: `dora_selection/resilience.py` (cache, diário, log e opções),
extensão de `dora_selection/api.py` (cota, retry e backoff), uso do diário em
`selection.py`, `deployments.py` e `__main__.py`, bloco `api` em `output.py` e
`tests/test_card4.py`.

```powershell
python -m pytest
```

Os testes offline cobrem acerto de cache na mesma execução e em execução posterior,
chave independente da ordem dos parâmetros, paginação a partir do cache, expiração,
entrada corrompida, resposta de erro não gravada, leitura dos headers de cota,
espera até o reset, reserva, `403` de cota, `Retry-After`, `403` definitivo, teto de
espera, backoff exponencial com teto, limite de tentativas, falha de conexão, `404`
sem repetição, log em arquivo, diário com unidade concluída e com erro, linha
truncada, configuração divergente, retomada nos três cards e interrupção com dados
preservados. Um teste executa o Card 3 inteiro com o cliente real e apenas o
transporte HTTP simulado: repete um `503`, grava o cache e, na segunda execução sem
diário, refaz a coleta sem nenhuma chamada. Relógio e espera são injetados nos
testes, que não dormem nem usam rede. O comportamento diante dos limites reais do
GitHub não é validado por mocks.

Referências oficiais:
[rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api),
[boas práticas de uso da API](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api).

## Lab03S01 — Card 5: métricas DORA

As quatro métricas DORA são calculadas em `dora_selection/metrics.py`, o único
arquivo novo além de `tests/test_card5.py`. São funções puras: sem rede, sem CLI,
sem persistência e sem estado compartilhado. Cada uma recebe listas simples e pode
ser chamada isoladamente, com os dados dos Cards 2 e 3 ou com dados sintéticos.
A coleta permanece nos Cards 1 a 3; este card não faz requisições nem grava arquivos.

### Uso

```python
import json
from pathlib import Path
from dora_selection.metrics import aggregate_metrics, repository_metrics
from dora_selection.selection import Window, timestamp

window = Window(timestamp("2026-01-05T00:00:00Z"), timestamp("2026-02-01T23:59:59Z"))
deployments = json.loads(Path("outputs/card2/run-X/deployments.json").read_text())
runs = json.loads(Path("outputs/card3/run-Y/workflow_runs.json").read_text())
metrics = [repository_metrics(window, d["releases"], r["workflows"], d["full_name"])
           for d, r in zip(deployments, runs)]
print(aggregate_metrics(metrics))
```

Use a mesma janela da coleta. `repository_metrics` apenas encaminha os dados para as
funções abaixo, que continuam utilizáveis separadamente; `aggregate_metrics` resume a
amostra por medianas. Nenhuma função altera a entrada.

| Função | Métrica | Entrada | Resultado principal |
| --- | --- | --- | --- |
| `deployment_frequency(releases, window)` | Deployment Frequency | releases válidas do Card 2 | `releases_per_week`, `weekly_counts`, `median_releases_per_week` |
| `lead_time_per_release(releases)` | Lead Time por release | releases com commits do Card 2 | `lead_time_hours` por release e `median_hours` |
| `lead_time_per_commit(releases)` | Lead Time por commit | releases com commits do Card 2 | `lead_time_hours` por commit e `median_hours` |
| `change_failure_rate(runs)` | Change Failure Rate | workflow runs do Card 3 | `change_failure_rate`, `considered` |
| `recovery_time_by_workflow(workflows, observed_until)` | Tempo de recuperação | workflows do Card 3 | `median_recovery_hours` por workflow e da amostra |
| `failure_episodes(runs, observed_until)` | Episódios de falha | runs de um workflow | `episodes`, `recovered`, `censored` |

### Definições

- Deployment Frequency: releases com `published_at` na janela inclusiva divididas
  pela duração exata da janela em semanas (o último segundo conta). `weekly_counts`
  cobre todas as semanas ISO de segunda a domingo em UTC, inclusive as sem release,
  e a mediana é calculada sobre elas. Semanas parciais nas pontas da janela ficam
  marcadas com `complete: false`, pois reduzem a contagem daquela semana.
- Lead Time por release: da data do commit mais antigo do intervalo entre a release
  anterior e a atual até o `published_at` da release. `median_commit_lead_time_hours`
  resume os commits daquela release.
- Lead Time por commit: `published_at` da release menos o `commit.author.date` do
  commit, exatamente o campo coletado no Card 2, sem substituir pelo committer.
- Change Failure Rate: `failure / (success + failure)` sobre os runs classificados
  no Card 3. Runs `ignored` (cancelados, em andamento, conclusões desconhecidas)
  são contados, mas ficam fora do denominador.
- Tempo de recuperação: duração de cada episódio de falha, do `run_started_at` da
  primeira falha ao `updated_at` do sucesso que o encerra (`created_at` como
  alternativa para ambos). Os runs são ordenados por `created_at`. Cada workflow é uma série independente, porque é o próximo sucesso
  do mesmo workflow que evidencia a recuperação.

### Episódios de falha, censura e dados ausentes

- Os runs são ordenados por `created_at`, com desempate por `id`; a ordem da entrada
  não altera o resultado. Runs sem data utilizável não entram na série e aparecem
  em `runs_without_date`.
- Falhas consecutivas pertencem ao mesmo episódio, contadas em `failures`. Um
  episódio começa na primeira falha e termina no primeiro sucesso posterior.
  Runs `ignored` não abrem, não estendem e não encerram episódios.
- Episódios sem sucesso posterior ficam censurados (`censored: true`): `recovery_hours`
  permanece `null` e `observed_hours` registra apenas o limite inferior observado até
  `observed_until` (normalmente o fim da janela) ou até o último run. Censurados não
  entram em nenhuma mediana e não são tratados como recuperação instantânea.
- Recuperação com datas contraditórias (fim antes do início) recebe
  `inconsistent: true` e também fica fora da mediana, em vez de ser corrigida.
- Medianas usam `statistics.median` sobre os valores existentes e retornam `null`
  quando não há amostra. `change_failure_rate` retorna `null` sem runs considerados,
  nunca zero por divisão vazia.
- Datas ausentes ou inválidas nunca interrompem o cálculo nem são estimadas: ficam em
  `ignored_missing_date`, `commits_without_date`, `runs_without_date` ou no motivo
  correspondente de `releases_ignored`.
- Releases sem intervalo confiável são separadas por motivo em `releases_ignored`:
  `no_previous_release` (primeira release da história), `no_comparison` (comparação com
  erro ou 404 no Card 2), `no_date`, `no_commits` (comparação vazia e válida) e
  `no_commit_dates`. Lead Times negativos, possíveis com rebase ou cherry-pick, são
  mantidos e contados em `negative`.

### Testes
## Lab03S01 — Card 4: cache, retomada, rate limit e tratamento de erros

Infraestrutura de resiliência da coleta, aplicada aos três comandos anteriores sem
mudar nenhuma regra de seleção, classificação ou pareamento. Continua usando apenas
a biblioteca padrão e `GITHUB_TOKEN`. Não calcula métricas DORA.

### Execução

As mesmas opções existem em `python -m dora_selection` (Cards 1 e 3) e em
`python -m dora_selection.deployments` (Card 2). Os padrões já ativam cache,
retomada e log; nada precisa ser informado para obter o comportamento resiliente:

```powershell
python -m dora_selection --card 3 --input outputs/card1/selected.json --start 2025-01-01T00:00:00Z --end 2025-12-31T23:59:59Z
```

| Opção | Padrão | Efeito |
| --- | --- | --- |
| `--cache-dir` | `<output>/cache` | Diretório das respostas gravadas |
| `--no-cache` | desligado | Não consulta nem grava cache |
| `--cache-ttl` | `0` | Validade em segundos; `0` não expira |
| `--state` | `<output>/state.jsonl` | Diário de retomada |
| `--no-resume` | desligado | Recoleta tudo, ignorando o diário |
| `--max-attempts` | `5` | Tentativas por chamada, incluindo a primeira |
| `--backoff` | `1.0` | Base do backoff exponencial em segundos |
| `--max-backoff` | `60.0` | Teto de cada espera do backoff |
| `--max-wait` | `3600.0` | Espera máxima aceita por reset de cota |
| `--rate-limit-reserve` | `0` | Chamadas mantidas de reserva na cota |
| `--log-file` | `<output>/collection.log` | Arquivo de log, além do stderr |

Apontar `--cache-dir` para o mesmo diretório em execuções e cards diferentes
reaproveita as respostas já obtidas. O diário, ao contrário, é por experimento.

### Cache local

- A consulta ao cache acontece antes de qualquer chamada; o acerto devolve os
  mesmos `(dados, headers)` e não consome cota nem tempo de rede.
- A chave é o SHA-256 da URL normalizada, com os parâmetros ordenados, de modo que
  a ordem em que a consulta foi montada não cria entradas duplicadas.
- O token viaja em header e nunca entra na chave nem no arquivo gravado.
- Só o header `Link` é guardado, o que preserva a paginação a partir do cache.
  Cota e datas de uma resposta antiga não são reaproveitadas como se fossem atuais.
- A gravação é feita em arquivo temporário no mesmo diretório e concluída com
  `os.replace`, operação atômica: uma interrupção não deixa entrada pela metade.
- Entrada ausente, ilegível, truncada ou expirada conta como ausência, é registrada
  em log e provoca nova chamada. Respostas de erro não são gravadas.

### Retomada

- Cada unidade concluída é gravada como uma linha JSON no diário, com `flush` e
  `fsync`, antes de a execução seguir para a próxima. O arquivo é append-only.
- A unidade é o repositório, em minúsculas: a mesma granularidade das três coletas.
  Card 1 considera concluído o repositório avaliado sem erro; Card 2, o repositório
  sem erro em nenhuma etapa; Card 3, o repositório com todos os meses completos.
- Na retomada, unidades concluídas são reaproveitadas e suas chamadas não são
  repetidas. Unidades com erro são refeitas, aproveitando o cache das chamadas que
  já tinham terminado, de forma que a repetição custa pouco e nada é perdido.
- Resultados gravados na execução atual não substituem a coleta em andamento;
  apenas o diário lido no início vale como retomada.
- A primeira linha guarda a configuração (card, janela e `--min-stars` no Card 1).
  Um diário de outra configuração é recusado com erro, em vez de misturar amostras.
- Uma interrupção só pode truncar a última linha, que é descartada com aviso e
  removida do arquivo; as anteriores continuam válidas.
- `Ctrl+C` é tratado: a coleta para, o parcial é persistido normalmente e o código
  de saída é 1. A execução seguinte continua de onde parou.

### Rate limit, erros e log

- `X-RateLimit-Remaining` e `X-RateLimit-Reset` são lidos em toda resposta,
  inclusive nas de erro, sem distinção de maiúsculas no nome do header.
- Quando o restante chega a `--rate-limit-reserve`, a próxima chamada espera até o
  reset informado, com um segundo de margem, e só então é enviada.
- `403` e `429` com `Retry-After` ou com cota esgotada são esperas, não falhas: a
  chamada é repetida depois do tempo pedido. `403` sem sinal de cota, como falta de
  permissão, é erro definitivo e não é repetido.
- Espera maior que `--max-wait` gera erro explícito em vez de travar a execução.
- Erros `5xx` e falhas de conexão, timeout ou DNS são repetidos com backoff
  exponencial `--backoff * 2 ** (tentativa - 1)`, limitado por `--max-backoff`.
- `--max-attempts` conta a primeira tentativa. Esgotadas as tentativas, a chamada
  falha com `APIError`, que os cards já tratam por repositório sem parar os demais.
- Demais erros `4xx` e JSON inválido falham na hora, porque repetir não muda a
  resposta.
- Esperas, novas tentativas e erros vão para o stderr e para o arquivo de log.
  O log é aberto antes da coleta, de modo que um erro de configuração já aparece.

### Saídas e testes

`funnel.json` (Card 1) e `summary.json` (Cards 2 e 3) passam a trazer o bloco
`api` com `requests`, `cache_hits`, `cache_misses`, `cache_entries_written`,
`cache_directory`, `retries`, `rate_limit_waits`, `rate_limit_remaining`,
`rate_limit_reset` e `resumed_units`. O Card 1 ganha o motivo de parada
`interrupted`. Os demais arquivos e campos continuam iguais aos dos cards anteriores.

Arquivos do Card 4: `dora_selection/resilience.py` (cache, diário, log e opções),
extensão de `dora_selection/api.py` (cota, retry e backoff), uso do diário em
`selection.py`, `deployments.py` e `__main__.py`, bloco `api` em `output.py` e
`tests/test_card4.py`.

```powershell
python -m pytest
```

Os testes do Card 5 validam releases por semana com semanas vazias e parciais,
janela e datas ausentes, Lead Time por release e por commit, CFR com e sem runs
considerados, classificação recalculada a partir de `status`/`conclusion`, episódios
com falhas consecutivas e runs ignorados no meio, entrada fora de ordem, episódios
censurados e excluídos da mediana, datas contraditórias, séries independentes por
workflow, medianas com amostra par e composição com agregação. Também verificam que
cada função funciona com dicionários mínimos, sem os campos do restante do pipeline.
Os valores dependem da coleta real dos Cards 1 a 3, que não é exercitada aqui.

Referências:
[DORA — métricas](https://dora.dev/guides/dora-metrics-four-keys/),
[semana ISO 8601](https://docs.python.org/3/library/datetime.html#datetime.date.isocalendar).

## Lab03S01 — Card 6: classificação DORA e casos especiais

A classificação em Elite, High, Medium e Low está em `dora_selection/rating.py`, o
único arquivo novo além de `tests/test_card6.py`. Como no Card 5, são funções puras:
sem rede, sem CLI e sem persistência. A entrada é o resultado de `repository_metrics`;
nenhuma métrica é recalculada aqui e nenhuma regra dos Cards 1 a 5 muda.

### Uso

```python
from dora_selection.metrics import repository_metrics
from dora_selection.rating import classify_repository, classify_sample
from dora_selection.selection import Window, timestamp

window = Window(timestamp("2026-01-05T00:00:00Z"), timestamp("2026-02-01T23:59:59Z"))
metrics = [repository_metrics(window, d["releases"], r["workflows"], d["full_name"])
           for d, r in zip(deployments, runs)]
classifications = [classify_repository(row) for row in metrics]
print(classify_sample(classifications)["by_overall"])
```

`classify_repository` devolve `ratings` (uma entrada por métrica, com `value`, `level`,
`score`, `basis` e `reason`), a mediana (`median_score`), a classificação geral
(`overall_score` e `overall`) e o bloco `special_cases`. `classify_sample` resume a
amostra: distribuição por métrica, distribuição geral, classificação geral da amostra
e a soma dos casos especiais. As funções por métrica
(`deployment_frequency_rating`, `lead_time_rating`, `change_failure_rate_rating`,
`recovery_time_rating`) continuam utilizáveis isoladamente, assim como `score`,
`level_from_score` e `overall_classification`.

### Limites

Os limites ficam em um único lugar, o dicionário `SCALES`, com uma `Scale` por métrica.
`higher_is_better` define o sentido da comparação e `inclusive` se o limite pertence à
faixa, de modo que alterar um limite não exige mexer na lógica de classificação.

| Métrica | Elite | High | Medium | Low |
| --- | --- | --- | --- | --- |
| Deployment Frequency (releases/semana) | ≥ 7 (uma por dia) | ≥ 1 (uma por semana) | ≥ 0,23 (uma por mês) | < 0,23 |
| Lead Time (horas) | < 24 (um dia) | < 168 (uma semana) | < 720 (30 dias) | ≥ 720 |
| Change Failure Rate | ≤ 15% | ≤ 30% | ≤ 45% | > 45% |
| Tempo de recuperação (horas) | < 1 | < 24 | < 168 | ≥ 168 |

Deployment Frequency usa limites inferiores inclusivos; Lead Time e tempo de
recuperação, limites superiores exclusivos; Change Failure Rate, limites superiores
inclusivos. "Uma por mês" é convertida em semanas pelo mês médio do calendário
gregoriano (365,2425 / 12 dias), o que dá ≈ 0,23 release por semana. Lead Time é
classificado pela mediana por release (variante (a): do commit mais antigo do
intervalo até a publicação), a combinação de referência da disciplina; a mediana por
commit é usada apenas quando a por release está ausente, e `basis` registra qual das
duas foi usada.

### Classificação geral

Cada nível vale Elite = 4, High = 3, Medium = 2 e Low = 1. A classificação geral é a
mediana das quatro notas arredondada para baixo: `[4, 3, 2, 1]` tem mediana 2,5 e
resulta em Medium. `median_score` guarda a mediana exata, `overall_score` o valor
arredondado e `overall` o nível correspondente.

Métrica sem amostra não vale zero nem Elite: fica com `level: null`, registra o motivo
em `reason` e não entra na mediana, que é calculada sobre as métricas disponíveis
(`classified_metrics` informa quantas foram). Sem nenhuma métrica classificável,
a classificação geral é `null`. A mesma regra vale na amostra: a classificação geral
do conjunto é a mediana arredondada das classificações gerais dos repositórios.

### Casos especiais

- Release sem commits novos: a comparação do Card 2 terminou vazia e válida. A release
  continua contando como deployment na frequência e aparece em
  `releases_without_new_commits`, mas não produz Lead Time. Se nenhuma release do
  repositório tiver commits, o Lead Time fica sem classificação com o motivo
  `releases_without_new_commits`.
- Repositório com apenas uma release: não existe par consecutivo, então o Lead Time
  fica sem classificação com o motivo `single_release` e o caso é sinalizado em
  `single_release`. A frequência continua medida normalmente, pois a release ocorreu.
- Falha nunca recuperada: o episódio censurado do Card 5 não é recuperação instantânea
  nem dado inexistente. Fica fora da mediana e é contado em `failures_never_recovered`.
  Quando não há nenhum episódio recuperado, o tempo observado serve de limite inferior
  e classifica a métrica apenas se já for suficiente para Low (`basis`
  `censored_lower_bound`); caso contrário o motivo é `never_recovered`. Repositório sem
  nenhuma falha recebe o motivo `no_failures`, não Elite por omissão. `censored_majority`
  avisa quando os censurados superam os recuperados e a mediana tende a ser otimista.
- Workflow runs ignoráveis: cancelados, pulados, neutros, com conclusão desconhecida ou
  ainda em andamento ficam fora do denominador do CFR e não abrem, não estendem e não
  encerram episódios de falha. Se todos os runs do repositório forem ignoráveis, o CFR
  fica sem classificação com o motivo `only_ignored_runs`, em vez de virar 0% e Elite.
- Zero release na janela é medição, não ausência: a frequência vale 0 e classifica Low.
- `special_cases` também traz releases sem data, commits sem data, Lead Times negativos
  (possíveis com rebase ou cherry-pick), runs sem data, episódios com datas
  contraditórias e o mapa `unclassified_metrics` com o motivo de cada métrica sem nível.

### Testes

```powershell
python -m pytest
```

Os testes do Card 6 verificam cada limite nas bordas das quatro faixas, valores não
numéricos, a conversão para notas e a volta, a mediana das quatro classificações com
arredondamento para baixo, medianas com métricas faltando, as quatro métricas
classificadas em conjunto, a distribuição da amostra e os casos especiais: release sem
commits novos, repositório com uma só release, comparação indisponível, falha nunca
recuperada, censura classificada por limite inferior, censura fora da mediana dos
recuperados, runs ignoráveis sem CFR e sem efeito nos episódios, runs classificados por
`status`/`conclusion` sem o campo do Card 3, datas ausentes, Lead Time negativo e
entradas vazias ou incompletas. Os valores de uma amostra real dependem da coleta dos
Cards 1 a 3, que não é exercitada aqui.

Referências:
[DORA — níveis de desempenho](https://dora.dev/guides/dora-metrics-four-keys/),
[State of DevOps — faixas de classificação](https://dora.dev/research/).
Os testes offline cobrem acerto de cache na mesma execução e em execução posterior,
chave independente da ordem dos parâmetros, paginação a partir do cache, expiração,
entrada corrompida, resposta de erro não gravada, leitura dos headers de cota,
espera até o reset, reserva, `403` de cota, `Retry-After`, `403` definitivo, teto de
espera, backoff exponencial com teto, limite de tentativas, falha de conexão, `404`
sem repetição, log em arquivo, diário com unidade concluída e com erro, linha
truncada, configuração divergente, retomada nos três cards e interrupção com dados
preservados. Um teste executa o Card 3 inteiro com o cliente real e apenas o
transporte HTTP simulado: repete um `503`, grava o cache e, na segunda execução sem
diário, refaz a coleta sem nenhuma chamada. Relógio e espera são injetados nos
testes, que não dormem nem usam rede. O comportamento diante dos limites reais do
GitHub não é validado por mocks.

Referências oficiais:
[rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api),
[boas práticas de uso da API](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api).

## Lab03S02 — S2-05: concordância entre avaliadores

Antes de usar os rótulos humanos como referência, o script mede o quanto os três
avaliadores concordam entre si, separadamente para cada dimensão rotulada.

### Execução

Com as três planilhas preenchidas em `validacao/rotulos/rotulos_{X}.csv` (S2-04):

```bash
python -m validacao.concordancia
python -m validacao.concordancia caminho/a.csv caminho/b.csv caminho/c.csv   # outras planilhas
```

O resultado vai para `validacao/resultados/kappa.csv` (`--output` muda o destino).
Termina com erro, sem gravar nada, se alguma planilha tiver célula vazia, valor fora
dos permitidos, release duplicada ou itens diferentes das demais.

### Entrada

As planilhas seguem o formato gerado por `python -m dora_selection.gold_sample`: uma
linha por release, com as colunas do repositório repetidas. Os valores permitidos são
os de `MANUAL_VALUES` em `dora_selection/gold_sample.py`; maiúsculas e espaços nas
pontas são ignorados, e arquivos salvos pelo Excel com `;` como separador também são
aceitos. Colunas extras, como `observacao`, são ignoradas.

| Dimensão | Itens | Valores |
|---|---|---|
| `project_type` | 1 por repositório (60) | `library/framework`, `application/service`, `cli`, `other` |
| `releases_represent_deliveries` | 1 por repositório (60) | `yes`, `no`, `uncertain` |
| `is_corrective` | 1 por release (300) | `yes`, `no` |

As duas dimensões do repositório podem ser preenchidas em apenas uma das linhas dele;
valores diferentes entre as linhas do mesmo repositório são erro.

### Saída

| Coluna | Descrição |
|---|---|
| `dimension`, `level` | Dimensão e nível do item (`repository` ou `release`) |
| `items`, `raters` | Número de itens e de avaliadores |
| `categories_used` | Categorias que aparecem em pelo menos um rótulo |
| `fleiss_kappa` | Kappa de Fleiss (`aggregate_raters` + `fleiss_kappa` do `statsmodels`); vazio quando indefinido |
| `interpretation` | Faixa de Landis & Koch (1977): pobre (< 0), leve (≤ 0,20), razoável (≤ 0,40), moderada (≤ 0,60), substancial (≤ 0,80), quase perfeita |
| `unanimous_agreement` | Fração de itens em que todos os avaliadores deram o mesmo rótulo |
| `pairwise_agreement` | Concordância média entre pares de avaliadores (o P̄ de Fleiss) |

As duas concordâncias brutas servem de contraste com o kappa, que desconta a
concordância esperada por acaso. Quando todos usam uma única categoria em uma dimensão,
a concordância esperada é 1 e o kappa fica indefinido (0/0): a coluna fica vazia e a
interpretação é `indefinido`, em vez de um valor numérico enganoso.

### Testes

`tests/test_concordancia.py` usa uma amostra com kappa calculado à mão: 4 releases e
3 avaliadores com κ = 1/3, concordância perfeita com κ = 1, discordância sistemática
com κ = −1 e uma dimensão com categoria única (kappa indefinido). Também cobre as
bordas da escala de Landis & Koch, planilhas do Excel com `;`, rótulos do repositório
em uma só linha, e cada erro de validação.

Referências:
[Fleiss (1971)](https://doi.org/10.1037/h0031619),
[Landis & Koch (1977)](https://doi.org/10.2307/2529310),
[`statsmodels.stats.inter_rater`](https://www.statsmodels.org/stable/generated/statsmodels.stats.inter_rater.fleiss_kappa.html).

## Lab03S02 — S2-06: consenso e protocolo de desempate

Consolida `validacao/rotulos/rotulos_grupo.csv` em um rótulo por item, usado como
referência da avaliação da heurística (S2-08) e como fator "tipo do projeto" da RQ 06.
O fluxo de maioria e desempate continua disponível quando várias planilhas são
passadas explicitamente.

### Execução

Com a planilha coletiva completa:

```bash
python -m validacao.consenso
```

| Arquivo | Quando | Conteúdo |
|---|---|---|
| `validacao/resultados/pendencias.csv` | Sempre | Pauta: votos, motivo (`tie`, `uncertain_majority`, `uncertain_vote`), maioria e rótulo decidido |
| `validacao/consenso.csv` | Sem células vazias | Rótulo final de cada item, `method` (`group`), voto e justificativa |
| `validacao/resultados/tipo_projeto.csv` | Sem itens pendentes | `repository`, `project_type` consensual, para a RQ 06 |

Uma célula obrigatória vazia ou inválida encerra a execução com erro. `--output`,
`--pending` e `--project-type` mudam os caminhos.

### Regras

- Maioria simples: o rótulo com mais da metade dos votos é o final.
- Empate 1-1-1 (`tie`) e maioria `uncertain` (`uncertain_majority`) ficam sem rótulo
  até a reunião; um voto `uncertain` isolado (`uncertain_vote`) mantém a maioria, mas
  entra na pauta para revisão.
- `validacao/decisoes.csv` (`dimension`, `repository`, `release_id`, `label`,
  `justification`) prevalece sobre a maioria. Cada linha precisa de justificativa, de um
  item existente nas planilhas e de um valor permitido; `release_id` fica vazio nas
  dimensões do repositório. As planilhas individuais nunca são editadas, então o
  consenso é sempre regenerável a partir dos arquivos versionados.

### Testes

`tests/test_consenso.py` cobre maioria, unanimidade, empate 1-1-1, maioria `uncertain`,
voto `uncertain` isolado, decisões que resolvem a pauta, decisão que revisa uma maioria,
cada erro do arquivo de decisões e as duas execuções da linha de comando (com e sem
pendências).

## Lab03S02 — S2-08: avaliação da heurística

Após gerar o consenso humano completo:

```powershell
py -3.13 validacao/avaliar_heuristica.py
```

O script avalia as 300 releases, calcula precisão, recall e F1, gera a matriz de
confusão e lista falsos positivos/negativos. O histórico e a ameaça à validade do
refinamento estão em [validacao/heuristica_versoes.md](validacao/heuristica_versoes.md).
`--approve` registra a versão oficial no `config.yaml` quando F1 >= 0,70, ou com
justificativa documentada para uma exceção. Sem consenso, `--predict-only` produz
somente previsões e mantém a aprovação pendente.

## Lab03S02 — S2-09: coleta completa da amostra

A amostra final tem pelo menos 300 repositórios que atendem aos critérios de inclusão
(5 ou mais releases e 50 ou mais workflow runs válidos no branch padrão, dentro da
janela). A coleta usa o comando único com `alvo: 300`; nenhuma regra dos Cards 1 a 4
mudou. O que a escala exige já estava no pipeline e passou a ser registrado em
`summary.json`, no bloco `collection_checks`:

| Problema de escala | Tratamento | Onde fica registrado |
| --- | --- | --- |
| Busca limitada a 1000 resultados | `CandidateSearch` divide a faixa de estrelas ao meio até cada consulta caber; uma faixa de um só valor é dividida pela data de criação | `selection.candidates_found` e `unique_repositories` |
| Mês com 1000 ou mais workflow runs | O período é dividido ao meio, recursivamente, e a contagem de cada parte é conferida com a da API | `months_at_run_limit` e a lista `months_at_run_limit_detail` |
| Compare com mais de 250 commits | Todas as páginas são seguidas pelo header `Link`; a comparação só é publicada completa | `releases_over_250_commits` |
| Compare com 404 (tag apagada) | A release fica fora do Lead Time e continua contando na frequência | `compare_not_found`; outros erros em `compare_error` |
| Primeira release da história | Sem release anterior, não há intervalo de commits | `releases_without_previous` |
| Release sem commits novos | Comparação vazia e válida | `releases_without_new_commits` |
| Rate limit e interrupções | Espera pelo reset, cache por resposta e diário por etapa (Card 4) | bloco `api`: `rate_limit_waits`, `cache_hits`, `resumed_units` |

As mesmas contagens aparecem por repositório em `data/processed/repositorios.csv`. O
funil da seleção é regravado a cada execução em `data/processed/funil.md`.

### Resultado da coleta

Janela de 2025-01-01 a 2025-12-31 (UTC), candidatos com 1001 estrelas ou mais,
percorridos em ordem decrescente de estrelas. A coleta foi interrompida com `Ctrl+C`
uma vez e retomada pelo mesmo comando, que reaproveitou o diário e seguiu do
candidato seguinte; uma nova execução a partir do cache não fez nenhuma chamada à API
e regravou CSVs idênticos.

| Etapa | Repositórios |
| --- | ---: |
| Candidatos recebidos da busca | 1025 |
| Repositórios únicos avaliados | 1021 |
| Com GitHub Actions | 917 |
| Com 5 ou mais releases na janela | 406 |
| Com 50 ou mais workflow runs válidos | 300 |
| Incluídos na amostra | 300 |

Descartes: 511 por releases insuficientes, 106 por workflow runs insuficientes, 103 sem
GitHub Actions e 1 por erro de coleta (`torvalds/linux`, cujo endpoint de
contribuidores responde 403).

| Dado coletado | Total |
| --- | ---: |
| Releases válidas na janela | 18.389 |
| Workflow runs (sucesso / falha / ignorados) | 668.276 / 62.156 / 60.959 |
| Meses com 1000 ou mais runs, subdivididos | 163 |
| Releases com mais de 250 commits no compare | 1.403 |
| Compare com 404 / com outro erro | 2 / 1 |
| Primeira release da história | 23 |
| Releases sem commits novos | 3.026 |
| Releases censuradas no CFR (b) | 246 (1,3%) |
| Episódios de falha censurados | 196 de 20.117 (1,0%) |

Os dois 404 são de `harness/harness` e o outro erro é um 422 de `docling-project/docling`;
as três releases ficam fora do Lead Time e continuam na frequência.

## Lab03S02 — S2-10: métricas em todas as variantes e dataset final

`dora_selection/dataset.py` achata os resultados de `metrics.py`, `cfr.py` e `rating.py`
em três tabelas, sem recalcular nada. Célula vazia significa métrica sem amostra, nunca
zero.

Nome, tipo, unidade, fórmula e origem na API de cada coluna estão no
[dicionário de dados](docs/dicionario_de_dados.md).

| Arquivo em `data/processed` | Uma linha por | Uso |
| --- | --- | --- |
| `repositorios.csv` | repositório | Base das RQs: métricas, contagens e fatores da RQ 06 |
| `releases.csv` | release válida da janela | Sensibilidade (RQ 07) e replicação cruzada |
| `episodios_falha.csv` | episódio de falha de um workflow | Censura da RQ 04 e bônus (RQ 08) |
| `funil.md` | etapa da seleção | Tabela do funil |

Colunas de `repositorios.csv`:

| Grupo | Colunas |
| --- | --- |
| Fatores da RQ 06 | `stars`, `language`, `contributors`, `created_at`, `age_days` (idade no fim da janela), `project_type` e `gold_sample` (tipo consensual, só para a amostra-ouro) |
| Deployment Frequency | `releases`, `deployment_frequency_per_week`, `median_releases_per_week` |
| Lead Time (a), por release | `lead_time_a_hours` (mediana, do commit mais antigo do intervalo até a publicação), `lead_time_a_releases` |
| Lead Time (b), por commit | `lead_time_b_hours` (mediana de publicação menos `commit.author.date`), `lead_time_b_commits` |
| Releases ignoradas no Lead Time | `releases_ignored` (total), `releases_no_previous`, `releases_compare_not_found`, `releases_compare_error`, `releases_no_new_commits`, `releases_no_commit_dates` |
| CFR (a), por workflow run | `cfr_a`, `cfr_a_runs` (denominador), `cfr_a_failures`, `runs_ignored` |
| CFR (b), por release corretiva | `cfr_b`, `cfr_b_version`, `cfr_b_evaluated` (denominador), `cfr_b_failed`, `cfr_b_corrective`, `cfr_b_censored` (releases dos últimos 7 dias da janela) |
| Tempo de recuperação | `recovery_hours` (mediana dos episódios recuperados), `recovery_episodes`, `recovery_recovered`, `recovery_censored`, `recovery_censored_share` (proporção censurada, RQ 04), `recovery_inconsistent` |
| Classificação DORA | `*_level` de cada métrica, `median_score`, `overall` |

`collection_complete` indica se releases e workflow runs do repositório foram coletados
sem erro. `releases_compare_not_found` e `releases_compare_error` somam o motivo
`no_comparison` do Card 5. `releases.csv` traz, por release, `comparison_status`,
`lead_time_status`, os dois Lead Times e o resultado da heurística (`corrective`,
`cfr_b_censored`, `cfr_b_failed`, `fixed_by_tag_name`); `episodios_falha.csv` traz os
campos de `failure_episodes` com o repositório e o workflow. Os totais de censura da
amostra ficam em `summary.json`, em `dataset.censoring`.

`tests/test_dataset.py` cobre as três tabelas com a amostra de `tests/conftest.py`, as
contagens de escala, o funil e a execução de `python -m pipeline --config` com a API
simulada, inclusive a segunda execução, que regrava o dataset sem nenhuma chamada.

## Como reproduzir as análises

Com os três CSVs do estudo em `data/processed/` (`repositorios.csv`,
`releases.csv` e `episodios_falha.csv`), instale as dependências e execute:

```bash
python -m pip install -r requirements-dev.txt
python -m analise
```

No PowerShell, também é possível usar diretamente o ambiente virtual existente:

```powershell
.\.venv\Scripts\python.exe -m analise
```

O comando executa todas as análises registradas em `ANALISES`, de
`analise/__main__.py`, usando somente os CSVs, sem token ou cache da API.
Gera tabelas `.csv` e `.tex` em `resultados/tabelas/` (prontas para `\input{}`)
e figuras PDF vetoriais em `resultados/figuras/`. `--dados` e `--saida` mudam os
diretórios; `--listar` mostra as análises e `--analise NOME` seleciona uma delas.

As RQs reutilizam `analise.comum`: `carregar`, `resumo`, `kruskal_wallis`,
`mann_whitney`, `epsilon_quadrado`, `cliffs_delta`, `interpretar_cliffs_delta`,
`holm` e `landis_koch`. Os quartis usam interpolação linear, ausentes são
excluídos das amostras e resultados sem observações ficam indefinidos.
`holm` retorna `p`, `p_holm` e `rejeita`, preservando ordem e índice; p ausente
não participa da família. A interpretação de kappa reutiliza a validação existente.

O contrato de tipos e unidades está em
[`docs/contrato_csv_analise.md`](docs/contrato_csv_analise.md). O padrão visual de
`analise.estilo` fixa tamanho, fontes e paleta; use `aplicar()` antes de criar
figuras e `salvar()` para exportá-las. Eixos logarítmicos usam apenas valores
positivos, com zeros e ausentes contabilizados separadamente.

Para registrar uma análise, implemente `executar(dados, saida)` e adicione-a a
`ANALISES`. Execute `python -m pytest` para validar a base comum, as contas manuais
e a reprodução das saídas a partir dos CSVs em um diretório temporário limpo.

## Lab03S03 — RQ 01 a RQ 04: estatística descritiva (mediana, IQR e censura)

Responde "quanto valem as métricas DORA nos repositórios populares que usam CI/CD" a
partir dos CSVs do pipeline, sem nenhuma coleta nova. Toda métrica é resumida por
**mediana e IQR** — nunca por média e desvio-padrão — e as RQ 02 e 03 trazem as duas
variantes obrigatórias lado a lado. O que ficou de fora é publicado junto: releases
ignoradas por motivo (incluindo o `compare` com 404), releases censuradas nos últimos
7 dias e a proporção de episódios censurados por repositório.

### Execução

```bash
python -m analise                                    # todas as análises registradas
python -m analise --listar                           # nomes disponíveis
python -m analise --dados data/processed --saida resultados --analise rq01_04
```

| Opção | Padrão | Efeito |
| --- | --- | --- |
| `--dados` | `data/processed` | Diretório dos três CSVs de entrada |
| `--saida` | `resultados` | Destino das tabelas, figuras e rascunhos |
| `--analise` | todas | Executa só a análise indicada; pode repetir |
| `--listar` | — | Lista as análises registradas e termina |

Termina com 2 quando algum CSV falta ou está sem as colunas obrigatórias, sem gravar
nada. As análises são regeneráveis: rodar de novo reescreve todas as saídas a partir
dos CSVs.

### Entrada

Três CSVs em `data/processed/`. Em todos eles só `repository` é obrigatória; as demais
colunas, quando faltam, entram como vazio e a análise recalcula o valor a partir da
tabela detalhada ou o registra como ausente — nunca como zero. Datas são lidas em UTC e
`True`/`False` são aceitos em qualquer caixa.

`repositorios.csv`, uma linha por repositório:

| Coluna | Uso |
| --- | --- |
| `releases_per_week` | RQ 01 |
| `release_lead_time_hours`, `commit_lead_time_hours` | RQ 02, variantes (a) e (b) |
| `releases_no_previous`, `releases_compare_not_found`, `releases_compare_error`, `releases_no_new_commits`, `releases_no_commit_dates`, `releases_no_date` | Releases fora do Lead Time, por motivo |
| `considered_runs`, `ignored_runs`, `change_failure_rate` | RQ 03, variante (a) |
| `delivery_change_failure_rate` (apelido: `cfr_entrega`) | RQ 03, variante (b), quando `releases.csv` não traz o veredito |
| `recovery_hours`, `censored_episodes` | RQ 04, quando `episodios_falha.csv` não existe |
| `deployment_frequency_level`, `lead_time_level`, `change_failure_rate_level`, `recovery_time_level`, `median_score`, `overall` | Classificação gravada pelo pipeline, conferida pela C1 |
| `stars`, `language`, `created_at`, `contributors`, `collection_complete`, `window_start`, `window_end` | Metadados, usados pelas RQ 05 a 07 |

`releases.csv`, uma linha por release:

| Coluna | Uso |
| --- | --- |
| `published_at`, `status`, `comparison_status` | Releases fora do Lead Time quando o resumo não as conta |
| `lead_time_hours`, `median_commit_lead_time_hours`, `first_commit_author_date`, `last_commit_author_date`, `commits` | Inspeção do commit antigo "esquecido" da RQ 02 |
| `censored`, `failed`, `corrective`, `fixed_by_tag_name` | RQ 03, variante (b) |

`episodios_falha.csv`, uma linha por episódio de falha:

| Coluna | Uso |
| --- | --- |
| `recovery_hours`, `recovered`, `inconsistent` | Mediana da RQ 04 |
| `observed_hours`, `censored` | Limite inferior do viés da censura |

### Saídas

| Arquivo | Conteúdo |
| --- | --- |
| `resultados/tabelas/sintese_rq01_04.{csv,tex}` | Tabela-síntese: métrica × variante × (n, mediana, Q1, Q3, IQR, unidade) |
| `resultados/tabelas/rq02_releases_ignoradas.{csv,tex}` | Releases fora do Lead Time por motivo, com a origem da contagem |
| `resultados/tabelas/rq02_razao_lead_time.{csv,tex}` | Os 5 repositórios com maior razão (a)/(b) e a release que explica a divergência |
| `resultados/tabelas/rq03_cobertura.{csv,tex}` | Runs considerados e ignorados; releases avaliadas, que falharam e censuradas |
| `resultados/tabelas/rq03_cfr_entrega_por_repositorio.{csv,tex}` | CFR (b) por repositório, para as RQ 05 a 07 |
| `resultados/tabelas/rq04_censura.{csv,tex}` | Episódios por desfecho, proporção censurada e tamanho do viés |
| `resultados/tabelas/rq04_recuperacao_por_repositorio.{csv,tex}` | Recuperação mediana, censura e limite inferior por repositório |
| `resultados/figuras/rq01_deployment_frequency.pdf` | Histograma e boxplot das releases por semana, em escala log |
| `resultados/figuras/rq02_lead_time_variantes.pdf` | Boxplots (a) × (b) e dispersão com a diagonal a = b |
| `resultados/figuras/rq03_cfr_variantes.pdf` | Boxplots das duas variantes do CFR e dispersão a × b |
| `resultados/figuras/rq04_tempo_de_recuperacao.pdf` | Recuperação com e sem os censurados e a censura por repositório |
| `resultados/texto/notas_rq01_04.md` | Rascunhos da seção de Resultados, com os números já no texto |
| `resultados/rq01_04.json` | Todos os números da análise, inclusive as tabelas por repositório |

Os `.tex` são `tabular` em LaTeX puro, prontos para o `\input{}` do template da SBC, com
vírgula decimal e travessão no valor ausente. As figuras são PDF vetorial no tamanho de
uma coluna do template, com o padrão visual de `analise/estilo.py`.

### Regras

- **RQ 01, Deployment Frequency.** Repositório sem release na janela entra na mediana
  com zero — é um valor medido, não um dado ausente — e é contado à parte.
- **RQ 02, Lead Time.** A variante (a), por release, vai do commit mais antigo do
  intervalo até a publicação; a (b), por commit, de cada commit até a publicação. Basta
  um commit antigo "esquecido" para (a) subir sem que o ritmo tenha mudado, então a
  análise publica a razão (a)/(b) por repositório e inspeciona em `releases.csv`, nos 5
  maiores, a release de maior intervalo: quando ela cobre pelo menos o dobro da mediana
  dos seus próprios commits, o intervalo é dominado por um commit antigo.
- **RQ 03, Change Failure Rate.** A variante (a) é proxy de CI (falhas sobre runs
  considerados) e a (b), proxy de entrega (releases seguidas em até 7 dias por uma
  corretiva da mesma linha). Falha de pipeline não é falha em produção: o rascunho em
  `resultados/texto/` explica por que as duas divergem e por que comparar qualquer uma
  delas direto com as faixas do relatório DORA superestima a taxa de falha.
- **RQ 04, tempo de recuperação.** A mediana usa apenas episódios recuperados e
  consistentes, o que **subestima** o tempo real: justamente os episódios mais longos
  são os que não terminaram dentro da janela. O viés é quantificado por um limite
  inferior que trata cada censurado como recuperado no fim da observação
  (`observed_hours`); o valor real fica acima da primeira mediana.
- Releases e episódios excluídos nunca são estimados nem tratados como zero: cada
  exclusão aparece em uma tabela, com o motivo.

### Testes

`tests/test_analise_comum.py` cobre a leitura dos três CSVs (datas em UTC, vazio como
ausente, coluna opcional faltando, apelido de coluna, arquivo e coluna obrigatória
ausentes), `resumo` com quartis calculados à mão (amostra ímpar, par, com ausentes e
vazia) e as saídas (`.tex` com escape e vírgula decimal, JSON com `null` no ausente).

`tests/test_rq01_04.py` usa uma amostra de quatro repositórios com cada estatística
calculável à mão — mediana 1,5 release por semana; Lead Time (a) 48 h e (b) 12 h, razão
mediana 2×; CFR (a) 0,5 e (b) 0,5; recuperação 10 h contra 30 h no limite inferior — e
cobre as duas variantes de cada RQ, a contagem de releases ignoradas por motivo (com e
sem as colunas do resumo), o `compare` com 404 separado dos demais erros, o episódio
inconsistente fora das duas medianas, o viés da censura, a amostra sem nenhuma linha e
os quatro caminhos da linha de comando.

## Lab03S03 — C1: classificação DORA de referência

A combinação **C1** é o ponto de comparação da análise de sensibilidade (RQ 07) e o
resultado que resume as RQ 01 a 04 no artigo. Esta análise fixa a definição da C1,
mostra que ela é reproduzível a partir do CSV e produz a distribuição das categorias.

| Métrica | Definição na C1 | Coluna do CSV |
| --- | --- | --- |
| Deployment Frequency | deployment = release publicada | `releases_per_week` |
| Lead Time | variante **(a) por release** | `release_lead_time_hours` |
| Change Failure Rate | variante **(a) proxy de CI** | `change_failure_rate` |
| Tempo de recuperação | primeira falha até o primeiro sucesso do mesmo workflow | `recovery_hours` |

As faixas são as da tabela de referência do enunciado, implementadas em
`dora_selection/rating.py`: a análise importa de lá em vez de reescrevê-las, para que
exista uma definição só no repositório.

### Execução

```bash
python -m analise --analise classificacao_c1
```

### As duas decisões que a C1 torna explícitas

**1. O fallback do Lead Time.** `lead_time_rating` classifica pela variante (a) e, na
falta dela, cai para a (b) por commit — e um repositório classificado assim não está, a
rigor, na C1. **Decisão do grupo: opção (2)**, a C1 usa só a variante (a); sem ela o Lead
Time fica sem classificação e o nível geral sai da mediana das outras três métricas. O
motivo está na RQ 07, que compara a C1 com a C4 (release + (b) + (b)) justamente para
separar o efeito de trocar a unidade de deploy do de trocar a variante da métrica: aceitar
o fallback na referência colocaria repositórios híbridos C1/C4 dentro dela e contaminaria
essa comparação. As duas leituras continuam lado a lado no CSV, com a contagem de quantos
repositórios a escolha afeta.

| Colunas | Leitura |
| --- | --- |
| `lead_time_level`, `median_score`, `overall_score`, `overall` | C1 **estrita**: só a variante (a); sem ela o Lead Time fica sem classificação |
| `lead_time_level_com_fallback`, `overall_com_fallback` | A regra de hoje do pipeline |
| `lead_time_apenas_com_b`, `overall_mudou_sem_fallback` | Os repositórios afetados pela escolha |

A tabela e a figura da distribuição seguem a decisão acima. O rascunho em
`resultados/texto/notas_classificacao_c1.md` registra a decisão e os números dos dois
cenários; reproduzir a regra do pipeline na RQ 07 é trocar de coluna, sem refazer a
análise.

**2. Métrica sem classificação.** O nível geral é a **mediana das notas das métricas
disponíveis** (Elite = 4 a Low = 1), arredondada para baixo. O repositório só fica sem
nível geral quando nenhuma das quatro métricas foi classificada: uma métrica ausente não
vira zero nem Elite e não entra na mediana, então um repositório com três métricas ainda
recebe nível geral, calculado sobre essas três. Quantos repositórios caem em cada caso
está em `classificacao_c1_cobertura.csv`.

### Conferência com o pipeline

Os níveis são recalculados a partir das colunas do CSV e comparados com os `*_level` e o
`overall` que o pipeline gravou; a coluna `divergencias` nomeia cada diferença. A
comparação usa a leitura com fallback, que é a regra implementada no pipeline. O tempo de
recuperação de um repositório sem nenhum episódio recuperado é reconstruído do limite
inferior dos censurados em `episodios_falha.csv`, como faz `recovery_time_rating` — sem
isso o CSV sozinho não reproduziria esse caso. Um `repositorios.csv` sem as colunas do
pipeline é reportado como **não verificável**, não como divergente.

### Saídas

| Arquivo | Conteúdo |
| --- | --- |
| `resultados/classificacao_c1.csv` | Uma linha por repositório: valores, níveis da C1, leitura com fallback, colunas do pipeline e `divergencias`; reaproveitado pela RQ 07 |
| `resultados/tabelas/classificacao_c1_distribuicao.{csv,tex}` | Elite / High / Medium / Low / sem classificação, por métrica e no geral (contagem) |
| `resultados/tabelas/classificacao_c1_distribuicao_percentual.{csv,tex}` | A mesma distribuição em proporção |
| `resultados/tabelas/classificacao_c1_cobertura.{csv,tex}` | Repositórios com 4, 3, 2, 1 ou nenhuma métrica classificada |
| `resultados/tabelas/classificacao_c1_divergencias.{csv,tex}` | Repositórios cujo recálculo não bateu com o pipeline (vazia quando tudo bate) |
| `resultados/figuras/classificacao_c1_distribuicao.pdf` | Barras empilhadas da distribuição por métrica e no geral |
| `resultados/texto/notas_classificacao_c1.md` | As duas decisões, a conferência e a distribuição, com os números no texto |
| `resultados/classificacao_c1.json` | Todos os números da análise |

### Testes

`tests/test_classificacao_c1.py` não inventa níveis: monta um repositório com as funções
do pipeline (`repository_metrics` e `classify_repository`), grava os três CSVs a partir
dessas estruturas e confere que a classificação recalculada bate métrica a métrica e no
nível geral — inclusive no caso em que a recuperação só pode ser classificada pelo limite
inferior dos censurados. Cobre também os casos de borda do enunciado (notas 4, 3, 3 e 1
têm mediana 3 e dão High; 4, 3, 2 e 1 têm mediana 2,5, arredondada para baixo, e dão
Medium), a métrica ausente fora da mediana, zero release como medição e não como ausência,
as duas leituras do Lead Time, a distribuição com contagem e proporção, a cobertura por
número de métricas, o nível trocado no CSV detectado como divergência e o CSV sem as
colunas do pipeline tratado como não verificável.

## Lab03S03 — RQ 05: frequência de deploy e CFR

```powershell
.\.venv\Scripts\python.exe -m analise --analise rq05
```

A RQ 05 também é executada por `python -m analise`, junto das demais análises
registradas. `--dados DIRETORIO` permite informar outra localização dos três CSVs.
O script usa somente esses arquivos, sem coleta, preenchimento manual ou imputação.

Calcula Spearman bilateral para DF × CFR (a) e DF × CFR (b), com um par por
repositório, exclusão de ausentes par a par e `n` efetivo separado. O CFR (b)
reutiliza a agregação da RQ 03 a partir dos vereditos das releases; usa o resumo por
repositório quando os vereditos não estão disponíveis. Se faltam vereditos necessários
de um repositório no detalhamento, o CFR (b) dele fica ausente. Variável constante
ou menos de dois pares produz correlação indefinida, sem interpretar isso como zero.

A força usa o valor absoluto de ρ: desprezível `< 0,10`, fraca `< 0,40`, moderada
`< 0,70`, forte `< 0,90` e muito forte nos demais casos, seguindo a convenção de
[Schober, Boer e Schwarte (2018)](https://doi.org/10.1213/ANE.0000000000002864).
Os p-valores são os retornados por `scipy.stats.spearmanr`, sem ajuste por
multiplicidade; a discussão registra seu caráter aproximado nesta amostra.

Cada dispersão mantém CFR entre 0 e 1 e DF em `symlog` de base 10, com limiar de
0,1 release/semana: zeros ficam no trecho linear e entram normalmente em Spearman,
sem somar constantes. A escala logarítmica se aplica acima do limiar.

O diagnóstico do artefato compara os quartis extremos de DF na amostra válida de
DF × CFR (b): baixa DF ≤ Q1 e alta DF ≥ Q3. Compara a mediana e o IQR dos intervalos
medianos por repositório, além da mediana da fração de intervalos de até sete dias.
Releases simultâneas têm intervalo zero; menos de duas datas válidas implica ausência
de intervalo. Quartis coincidentes não formam grupos sobrepostos. O contraste é
descritivo e não quantifica a parcela da correlação causada pela construção do CFR.

| Saída | Conteúdo |
| --- | --- |
| `resultados/tabelas/rq05_correlacoes.{csv,tex}` | Variante, n, ρ, p e força |
| `resultados/tabelas/rq05_artefato_cfr_b.{csv,tex}` | Comparação dos intervalos entre baixa e alta DF |
| `resultados/figuras/rq05_df_cfr_a.pdf`, `rq05_df_cfr_b.pdf` | Dispersões vetoriais, uma por variante |
| `resultados/texto/notas_rq05.md` | Rascunho calculado da discussão, achado do artefato e limitações |
| `resultados/rq05_por_repositorio.csv`, `rq05.json` | Dados auditáveis da análise e estatísticas completas |

`tests/test_rq05.py` usa amostras sintéticas exclusivamente para verificar contas
manuais, ausentes, empates, constantes, censura, quartis e geração dos artefatos.
Os resultados do artigo devem ser gerados com os CSVs da coleta do estudo.

Referências: [documentação do SciPy](https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.stats.spearmanr.html)
e [DORA: métricas de desempenho de entrega](https://dora.dev/guides/dora-metrics/).

## Lab03S03 — RQ 06: fatores associados ao desempenho DORA

```powershell
.\.venv\Scripts\python.exe -m analise --analise rq06
```

Também executada por `python -m analise`. Usa os CSVs de `data/processed/`
ou do diretório informado por `--dados`, sem API ou imputação.

Linguagem mantém até seis categorias com ao menos 15 repositórios e agrupa as
demais conhecidas em Outras, absorvendo a menor categoria se necessário para
atingir esse mínimo. Ausentes ficam fora. Estrelas, contribuidores e idade usam
`pd.qcut(..., q=4, duplicates='drop')`, sem separar empates. Idade é medida
entre `created_at` e `window_end`. Os cortes são fixados antes de excluir
métricas ausentes e documentados em `rq06_grupos.csv` e `notas_rq06.md`.

Holm é aplicado separadamente aos 16 testes principais (4 fatores × DF, LT (a),
CFR (a) e recuperação), aos 8 suplementares (LT (b) e CFR (b)) e aos 4 exploratórios
por tipo. Usa KW com ε² = H/(n−1), ou MW com Cliff para dois grupos. Só KW
significativo após Holm abre post-hoc MW, com Holm dentro de cada fator/família.
Testes sem dados suficientes ficam indefinidos; cada teste informa seu n efetivo.

Tipo do projeto usa `validacao/resultados/tipo_projeto.csv`; se ausente, usa
`validacao/rotulos/rotulos_grupo.csv`, identificado como coletivo e provisório.
Rótulos repetidos por release contam uma vez por repositório; conflitos geram erro.
Se algum tipo tiver menos de 5 valores válidos, comparam-se os dois maiores por MW.
Sem rótulos, somente a família exploratória fica indefinida.

| Saída | Conteúdo |
| --- | --- |
| `resultados/tabelas/rq06_testes_principal.{csv,tex}` | 16 testes, n, H/U, p, p Holm, ε²/δ e interpretação |
| `resultados/tabelas/rq06_testes_suplementar.{csv,tex}` | Variantes (b), família de Holm separada |
| `resultados/tabelas/rq06_testes_exploratoria.{csv,tex}` | Tipo do projeto, amostra e restrições próprias |
| `resultados/tabelas/rq06_posthoc.{csv,tex}` | Pares, Holm por fator/família, Cliff e direção (CSV) |
| `resultados/tabelas/rq06_grupos.{csv,tex}` | Grupos, limites dos quartis, unidades e contagens |
| `resultados/figuras/rq06_*.pdf` | Boxplots vetoriais das combinações significativas após Holm |
| `resultados/texto/notas_rq06.md` | Cortes, discussão calculada, proveniência dos tipos e limitações |

Os CSVs mantêm precisão completa; LaTeX mostra H/ε² para KW e U/δ para MW.
O post-hoc pode ser ajustado com `\resizebox{\textwidth}{!}{\input{...}}` (`graphicx`).
Os PDFs seguem `analise/estilo.py`: CFR entre 0 e 1; DF e durações em `symlog`
com limiares de 0,1 release/semana e 1 hora, preservando zeros e Lead Times negativos
do pipeline. Figuras que perderam significância são removidas na reexecução.
As convenções de efeito, referências e limitações estão em `notas_rq06.md`.
`tests/test_rq06.py` usa dados sintéticos somente para verificar as contas e a execução.

## Final — Replicação cruzada: executar o pipeline de outro grupo

Primeira parte da replicação cruzada: executar o pipeline do grupo sorteado pelo
professor **usando apenas o README dele**, sobre uma subamostra de 30 repositórios do
dataset original, sem pedir ajuda ao grupo autor. Travar não é fracasso — é resultado, e
precisa de evidência: cada falha de execução ou documentação faltante vira uma Issue no
repositório do grupo autor.

### Subamostra

```bash
python -m replicacao.subamostra --csv <csv-do-outro-grupo>
```

| Opção | Padrão | Efeito |
| --- | --- | --- |
| `--csv` | — | CSV original do outro grupo, com a lista de repositórios (obrigatório) |
| `--coluna` | detectada | Coluna do repositório, quando o CSV usa um nome fora dos conhecidos |
| `--tamanho` | 30 | Tamanho da subamostra |
| `--semente` | 42 | Semente do sorteio |
| `--saida` | `replicacao` | Destino de `subamostra.csv` e `subamostra.json` |

Termina com 2 quando o CSV não existe, está sem linhas ou não tem nenhuma coluna de
repositório reconhecida — nesse caso a mensagem lista as colunas encontradas, para que
`--coluna` resolva.

O sorteio é reproduzível por qualquer pessoa, inclusive pelo grupo autor ao responder as
Issues, porque três coisas ficam registradas:

- a **semente** (42), publicada no código e repetida em `subamostra.json`;
- a **ordenação do universo antes do sorteio**: a lista é ordenada e deduplicada, então o
  resultado depende só do *conjunto* de repositórios e da semente, nunca da ordem das
  linhas no CSV do outro grupo — dois clones do mesmo dataset dão a mesma subamostra;
- o **sha256 do CSV de origem**, que amarra a subamostra ao arquivo exato de onde saiu.

O sorteio usa `random.Random(semente).sample` da biblioteca padrão, e não o `sample` do
pandas, para não depender da versão da biblioteca: o módulo inteiro é stdlib, porque a
subamostra é sorteada antes de instalar qualquer coisa do ambiente do outro grupo.

### Diário e evidências

| Arquivo | Conteúdo |
| --- | --- |
| `replicacao/diario_execucao.md` | Grupo replicado, commit/tag, ambiente, cada comando com tempo, saída, erro e contorno (marcando se o contorno exigiu sair do README), links das Issues abertas e o resumo para o artigo |
| `replicacao/subamostra.csv` | A lista de 30 repositórios efetivamente usada |
| `replicacao/subamostra.json` | Semente, coluna, sha256 do CSV de origem e tamanho do universo |
| `replicacao/resultados_obtidos/` | Os CSVs produzidos pela execução, como saíram do pipeline do outro grupo, sem edição |

Os CSVs obtidos entram sem nenhuma edição, renomeação de coluna ou reordenação: a
comparação com os resultados publicados pelo grupo autor parte do arquivo original.

### Testes

`tests/test_subamostra.py` cobre as propriedades que fazem o sorteio valer como
evidência: 30 repositórios distintos, mesma semente e mesmo conjunto dando sempre a mesma
lista, a ordem das linhas do CSV não alterando o resultado, semente diferente dando lista
diferente, universo menor que 30 tomado inteiro e registrado como tal, repetidos e vazios
descartados, cada grafia conhecida da coluna de repositório, CSV com `;` do Excel, e os
códigos de saída do comando.

## Final — Fragilidade da classificação perto dos limites das faixas

Uma replicação independente do nosso dataset reclassificou `FuelLabs/sway` de Low para
Medium ([#62](https://github.com/Paulooassis/Laboratorio-03-medicao-de-software/issues/62)).
O cálculo dos dois lados estava correto: a métrica estava a 1,10% do limite da faixa.
Esta análise mede essa distância para todos os repositórios, para que uma divergência de
categoria possa ser respondida com número em vez de opinião.

### Execução

```bash
python -m analise --analise fragilidade
```

### O que ela mede

Para cada repositório e cada métrica da C1: o nível atual, o **limite de faixa mais
próximo** da tabela de referência, a margem até ele em valor absoluto e em fração do
valor, e se mover aquela métrica **um degrau** — para melhor ou para pior — mudaria a
classificação geral. A classificação geral é a mediana das quatro notas arredondada para
baixo, então uma única métrica pode decidir o resultado.

| Arquivo | Conteúdo |
| --- | --- |
| `resultados/tabelas/fragilidade_limites.{csv,tex}` | Uma linha por repositório: métrica mais frágil, margem, se muda o geral e quantas métricas mudariam |
| `resultados/figuras/fragilidade_limites.pdf` | Distribuição das margens em escala log, com a faixa de risco de 5% destacada |
| `resultados/texto/notas_fragilidade.md` | Os cinco mais frágeis, o caso da #62 com a posição dele no ranking, e o rascunho das ameaças à validade |
| `resultados/fragilidade.json` | Todos os números |

### Resultado na nossa amostra

Em **259 dos 300 repositórios (86,3%)** mover uma única métrica um degrau muda a
classificação geral; em **53** a métrica mais próxima está a 5% ou menos do limite; e em
**31** as duas coisas valem ao mesmo tempo. O mais frágil é `ultralytics/ultralytics`, a
0,06% do limite de 24 h do Lead Time (a). O `FuelLabs/sway` da #62 é o 25º de 300, a
1,10%.

A consequência para o artigo está no rascunho: **uma divergência de categoria entre duas
execuções não implica erro de cálculo em nenhuma delas**, e comparações de categoria
(RQ 07 inclusive) deveriam reportar quantos repositórios estavam perto de um limite.

### Testes

`tests/test_fragilidade.py` usa o caso da #62 como referência, com os números conferidos
à mão: recuperação de 169,87 h contra o limite de 168 h dá margem de 1,87 h e 1,10% do
valor, e as notas (2, 3, 1, 1) com mediana 1,5 viram (2, 3, 1, 2) com mediana 2,0 quando
a recuperação sobe um degrau. Cobre também a escolha do limite mais próximo (e não do
primeiro), métrica ausente sem margem, os vizinhos de cada nível, a métrica que não decide
nada, e três propriedades do rascunho: ele cita a posição do caso no ranking em vez de
afirmar que é o mais frágil, e avisa quando o repositório não está na amostra.

## Dados publicados do estudo

Os CSVs do estudo estão versionados em `data/processed/`, de modo que
`python -m analise` roda a partir de um clone limpo, sem token e sem refazer a coleta:

| Arquivo | Conteúdo |
| --- | --- |
| `data/processed/repositorios.csv` | 300 repositórios, uma linha cada, com as métricas DORA e a classificação |
| `data/processed/releases.csv` | 18.389 releases, uma linha cada |
| `data/processed/episodios_falha.csv` | 20.117 episódios de falha, um por linha |
| `data/processed/funil.md` | Funil das etapas de seleção |

Esses arquivos foram produzidos pela coleta dos 300 repositórios e trazem os nomes de
coluna do pipeline, que em alguns casos diferem dos do contrato de leitura — a
correspondência está em [`docs/contrato_csv_analise.md`](docs/contrato_csv_analise.md) e a
leitura aceita os dois nomes. As colunas reais de cada CSV estão no
[dicionário de dados](docs/dicionario_de_dados.md).

### Replicar sobre uma subamostra

Para executar a coleta sobre uma lista dada de repositórios, em vez da busca por
estrelas:

```bash
python -m dora_selection.pipeline --start 2025-01-01T00:00:00Z --end 2025-12-31T23:59:59Z \
    --repos replicacao/subamostra.csv
```

`--repos` aceita um CSV com a coluna `repository` ou `full_name` (ou uma única coluna sem
cabeçalho) e **substitui a busca**, não os critérios de inclusão: um repositório da lista
que não passe nos critérios continua aparecendo no funil como excluído, com o motivo. A
execução é considerada completa quando toda a lista foi avaliada, porque exclusão pelos
critérios é resultado do estudo e não falha de execução.

## Lab03S03 — #41: unidades de deploy da RQ 07

A análise de sensibilidade (RQ 07) compara a classificação DORA sob unidades de deploy
diferentes da definição principal. Esta etapa coleta o que faltava para calculá-las,
sem alterar nenhuma regra da definição principal:

| Unidade | Deploy | Data do deploy |
| --- | --- | --- |
| `release` | Release publicada (definição principal) | `published_at` |
| `release_prerelease` | Release ou pré-release publicada na janela, numa só sequência | `published_at` |
| `tag` | Commit apontado por uma ou mais tags da janela | `commit.author.date` do commit |

Ligada por `variantes: true` na seção `coleta` do `config.yaml` (ou `--variants`), roda
depois da coleta de workflow runs e grava `data/processed/variantes.csv` (uma linha por
repositório e unidade) e `data/processed/deploys_variantes.csv` (uma linha por deploy).
As colunas estão em [docs/dicionario_de_dados.md](docs/dicionario_de_dados.md).

### Decisões

- **Datas das tags pela API GraphQL.** O REST só devolve a data de uma tag com uma
  chamada por commit. O GraphQL lista as tags ordenadas pela data do commit, 100 por
  consulta, e a paginação para na primeira página anterior à janela; um repositório com
  milhares de tags antigas custa poucas consultas. A cota do GraphQL é separada da REST
  e o cliente respeita cada uma por conta própria.
- **Tags no mesmo commit são um só deploy.** Um monorepo que marca vários pacotes de
  uma vez multiplicaria a frequência. Na amostra, 36.264 tags da janela formam 24.564
  deploys (32% das tags foram agrupadas); a coluna `tags` preserva a contagem original.
- **Cada deploy é comparado com o anterior da própria unidade**, pela mesma função de
  `compare` e com o mesmo cache da definição principal: pares já consultados não
  geram nova chamada.
- **Falha de coleta não vira "zero deploys".** Se as datas das tags de um repositório
  não puderem ser lidas, a linha da unidade `tag` fica com `collection_complete = False`.
- **CFR (a) e tempo de recuperação não mudam** com a unidade, pois usam workflow runs.

### Custo da coleta completa (300 repositórios)

Estimado antes de rodar, a partir de `deployments.json` e das datas das tags:

| Item | Quantidade |
| --- | ---: |
| Consultas GraphQL (datas das tags) | 1.003 |
| Deploys em `release_prerelease` | 21.778 (18.389 releases + 3.389 pré-releases) |
| Deploys em `tag` | 24.564 |
| Comparações novas, `release_prerelease` | 4.180 |
| Comparações novas, `tag` | 8.583 |

Cada comparação nova custa em média até 2,3 chamadas REST (a média observada nas
comparações da definição principal), ou seja, até cerca de 29 mil chamadas, o que são
6 horas de cota com 5.000 chamadas por hora. Os maiores custos são `pytorch/pytorch`
(1.039 comparações novas), `vercel/next.js` (672), `metabase/metabase` (560),
`zed-industries/zed` (554) e `electron/electron` (547). Interrompida por cota ou
`Ctrl+C`, a coleta continua de onde parou com o mesmo comando. Sem `variantes`, o
custo da definição principal não muda.

### Testes

`tests/test_variants.py` usa a API simulada do Card 8 e cobre: tags anotadas e tags que
não apontam para commit; paginação do GraphQL que para na janela; tags no mesmo commit;
tag base anterior à janela; sequência combinada de release e pré-release; primeiro
deploy sem base; compare com 404 e com erro; SHA idêntico sem chamada; repositório com
uma única release; falha das datas das tags sem perder a outra unidade; retomada pelo
diário; e o cliente GraphQL (corpo e token, cache, erro não gravado, espera do reset,
desistência quando o reset está longe, cotas REST e GraphQL separadas). O teste de
ponta a ponta confere que a segunda execução reconstrói `variantes.csv` sem nenhuma
chamada à API.

## Lab03S03 — RQ 07: sensibilidade da classificação DORA

Mede o quanto a classificação de um repositório (Elite/High/Medium/Low) depende da
definição operacional. Cada repositório é classificado sob quatro combinações, com as
mesmas faixas e a mesma mediana de notas da C1 (`dora_selection/rating.py`):

| Combinação | Unidade de deploy | Lead time | CFR |
| --- | --- | --- | --- |
| C1 (referência) | release | (a) por release | (a) proxy de CI |
| C2 | release + pré-release | (b) por commit | (b) proxy de entrega |
| C3 | tag | (b) por commit | (a) proxy de CI |
| C4 | release | (b) por commit | (b) proxy de entrega |

A C4 é a combinação adicional que o enunciado deixa a critério do grupo. Ela muda só as
variantes das métricas e mantém a unidade, e por isso separa dois efeitos que C1 × C2
mistura: **C1 × C4** mede o efeito de trocar as variantes, e **C2 × C4**, o de trocar a
unidade (release → release + pré-release).

```bash
python -m analise --analise rq07
```

Entrada: `data/processed/variantes.csv` (veja [#41](#lab03s03--41-unidades-de-deploy-da-rq-07))
mais os três CSVs de sempre. Sem `variantes.csv` a análise não falha: grava
`resultados/texto/notas_rq07.md` dizendo que está indisponível.

| Saída | Conteúdo |
| --- | --- |
| `resultados/tabelas/rq07_pares.{csv,tex}` | Para cada um dos 6 pares e para o nível geral e cada métrica: n comparado, quantos mudaram, % que mudou e kappa de Cohen ponderado linear com a interpretação de Landis e Koch |
| `resultados/tabelas/rq07_transicao_<Ci>_<Cj>.{csv,tex}` | Matriz de transição do nível geral (a última linha e coluna são "Sem classificação") |
| `resultados/tabelas/rq07_distribuicao.{csv,tex}` | Distribuição do nível geral em cada combinação |
| `resultados/tabelas/rq07_robustez_descritiva.{csv,tex}` | Mediana e IQR de DF, Lead Time e CFR sob cada combinação e a variação da mediana frente à C1 (RQ 01 a 03) |
| `resultados/tabelas/rq07_robustez_spearman.{csv,tex}` | Spearman DF × CFR sob cada combinação e se o sinal e a significância da C1 se mantêm (RQ 05) |
| `resultados/tabelas/rq07_robustez_rq06.{csv,tex}` | Testes da família principal da RQ 06 que rejeitam H0 após Holm em cada combinação, em comum com a C1, novos e perdidos |
| `resultados/figuras/rq07_distribuicao.pdf` | Barras empilhadas do nível geral por combinação |
| `resultados/figuras/rq07_transicao_C1_C{2,3,4}.pdf` | Mapas de calor das transições a partir da C1 |
| `resultados/texto/notas_rq07.md` | Rascunho da seção, com todos os números calculados |

### Decisões

- **Repositório sem nível numa combinação fica de fora do par**, e a tabela traz quantos
  ficaram só de um lado (`so_na_primeira`, `so_na_segunda`). Nenhuma métrica ausente vira
  Low.
- **Coleta falha numa unidade não vira "zero deploys".** Se `collection_complete` é falso, as
  métricas da unidade ficam ausentes e o nível geral da combinação também: o CFR (a) e a
  recuperação, que não dependem da unidade, não bastam para sustentar um nível sozinhos.
- **Kappa indefinido** quando as duas combinações têm uma única categoria (0/0), em vez de
  forçar 1 ou 0.
- **A família da RQ 06 é a do Paulo** (`rq06.familia`, Holm sobre 4 fatores × 4 métricas),
  reaproveitada; a partição em grupos não muda com a unidade de deploy.
- **Conferência:** a unidade `release` de `variantes.csv` é comparada com
  `repositorios.csv`, e a C1 daqui, com `classificacao_c1`; divergências saem em
  `notas_rq07.md`.

### Testes

`tests/test_rq07.py` usa um cenário de 5 repositórios com os níveis, os percentuais e os
kappas calculados à mão (3/7, 8/11, 0,8, 1/3 e 4/7), incluindo um repositório cuja coleta de
tags falhou e outro ausente de `variantes.csv`. Cobre também o kappa nos casos de borda, a
matriz de transição, a robustez da RQ 05 (inclusive o CFR constante, que torna a correlação
indefinida), da RQ 06 e das medianas, a unidade duplicada, a unidade ausente e o comando sem
`variantes.csv`.

## Lab03S03 — RQ 08 (bônus): rework rate

A *deployment rework rate* que o DORA acrescentou em 2024: a proporção de entregas não
planejadas, feitas para corrigir problemas. Aqui é `releases corretivas ÷ releases
avaliadas` por repositório, com a heurística `v1` da RQ 03 (b).

```bash
python -m analise --analise rq08
```

**Em que difere do CFR (b).** O CFR (b) marca a release que *falhou* (a seguida por uma
corretiva em até 7 dias); o rework rate marca a *própria correção*, sem janela de tempo.
Por isso: uma correção tardia é retrabalho aqui e passa despercebida lá; o rework rate não
censura os últimos 7 dias da janela; e uma só corretiva pode marcar várias falhas no CFR
(b). A primeira release da história de cada repositório, que não tem anterior para ser
corrigida, fica fora do denominador e é contada à parte.

A função pura é `dora_selection.cfr.rework_rate`, e o pipeline grava `rework_rate`,
`rework_evaluated`, `rework_corrective` e `rework_no_previous` em `repositorios.csv`
(documentadas no [dicionário](docs/dicionario_de_dados.md#rework-rate-rq-08)). A análise
recalcula a taxa a partir de `releases.csv` e confere com a coluna do pipeline.

| Saída | Conteúdo |
| --- | --- |
| `resultados/tabelas/rq08_resumo.{csv,tex}` | n, mediana, Q1, Q3 e IQR do rework rate e do CFR (b) |
| `resultados/tabelas/rq08_correlacao.{csv,tex}` | Spearman rework rate × CFR (b): ρ, p, n e força |
| `resultados/tabelas/rq08_divergencias.{csv,tex}` | Os 10 repositórios em que as duas métricas mais se afastam, com as contagens |
| `resultados/figuras/rq08_distribuicao.pdf` | Histograma do rework rate por repositório |
| `resultados/figuras/rq08_rework_cfr_b.pdf` | Dispersão rework rate × CFR (b) com a reta de igualdade |
| `resultados/texto/notas_rq08.md` | Rascunho com a definição, a diferença para o CFR (b), a correlação e a confiança |

Sobre os 300 repositórios, a mediana do rework rate é 0,70 (IQR 0,41), contra 0,27 do CFR
(b), e a heurística marca 65% das releases como corretivas. Como a precisão da `v1` na
amostra-ouro (0,70) é menor que o recall (0,82), a taxa observada tende a superestimar o
retrabalho: o rascunho traz a correção por P/R como ordem de grandeza.

### Testes

`tests/test_cfr.py` cobre `rework_rate` (repositório sem corretivas, só corretivas, primeira
release da história, release única, sem releases, sem censura, release sem data, `compare`
em erro e tags fora do SemVer), e `tests/test_rq08.py` cobre a análise com um cenário feito
à mão: a taxa por repositório, o denominador, os totais e a reconciliação com o CFR (b), a
origem alternativa dos dados, a conferência com o pipeline, o Spearman à mão, as
divergências, o ajuste por precisão e recall e o comando de ponta a ponta.
