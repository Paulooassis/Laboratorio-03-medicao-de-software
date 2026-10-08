# Laboratorio-03-medicao-de-software

![Testes](https://github.com/Paulooassis/Laboratorio-03-medicao-de-software/actions/workflows/tests.yml/badge.svg)

## Como executar

Do zero até as métricas DORA dos 100 repositórios. As seções dos Cards 1 a 6, mais
abaixo, detalham as regras de cada etapa; aqui está só o necessário para rodar.

### 1. Instalação

Requer Python 3.10 ou superior. O pipeline usa apenas a biblioteca padrão; as
dependências instaladas servem somente aos testes.

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
métricas e classificação:

```bash
python -m dora_selection.pipeline --start 2025-01-01T00:00:00Z --end 2025-12-31T23:59:59Z
```

`--start` e `--end` definem a janela inclusiva (ISO 8601 com fuso, precisão de
segundos) e são obrigatórios: a janela é uma decisão do experimento e deve ser a
mesma para todo o grupo. As demais opções têm padrão:

| Opção | Padrão | Efeito |
| --- | --- | --- |
| `--target` | `100` | Quantidade de repositórios a selecionar |
| `--min-stars` | `1001` | Mínimo de estrelas dos candidatos |
| `--output` | `outputs/pipeline` | Pasta de saída, com cache e diários |
| `--tag-dates` | desligado | Consulta também a data do commit de cada tag |
| `--workers` | `4` | Consultas simultâneas dentro de cada repositório; `1` desliga o paralelismo |
| `--state` | `<output>/state` | Pasta dos diários de retomada, um por etapa |

As opções de cache, retry e rate limit do Card 4 (`--cache-dir`, `--no-cache`,
`--cache-ttl`, `--no-resume`, `--max-attempts`, `--backoff`, `--max-backoff`,
`--max-wait`, `--rate-limit-reserve`, `--log-file`) valem aqui com os mesmos padrões.

Etapas, na ordem:

1. **Seleção e metadados** (Card 1): percorre os repositórios públicos por estrelas
   até reunir `--target` que atendam aos critérios.
2. **Releases, tags e commits** (Card 2) dos selecionados.
3. **Workflow runs** (Card 3) dos selecionados.
4. **Métricas e classificação DORA** (Cards 5 e 6), sem rede.

A coleta de 100 repositórios faz dezenas de milhares de chamadas e leva horas. O
limite é a cota da API, de 5000 chamadas por hora: quando ela acaba, o programa
aguarda sozinho o reset e continua. Para chegar perto desse limite sem desperdício:

- cada filtro da seleção só é consultado se o anterior passou (sem Actions não se
  consultam releases; com menos de 5 releases não se consultam runs);
- os workflow runs são baixados uma única vez: a seleção faz as mesmas consultas
  mensais da etapa 3, que então vem inteira do cache;
- dentro de um repositório, os meses de runs e as comparações entre releases são
  consultados em paralelo (`--workers`), sempre poucos por vez, como o GitHub pede;
- as respostas trafegam comprimidas (gzip).

O progresso aparece no console e em `collection.log`, uma linha por repositório
concluído. A coleta pode ser interrompida com `Ctrl+C` a qualquer momento: repetir
**o mesmo comando** retoma do ponto em que parou, sem refazer chamadas já
respondidas. Para validar a instalação antes da coleta completa, use uma amostra
pequena em outra pasta (cerca de dois minutos):

```bash
python -m dora_selection.pipeline --start 2025-01-01T00:00:00Z --end 2025-12-31T23:59:59Z --target 3 --output outputs/smoke
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
de `dora_selection/metrics.py` e `dora_selection/rating.py`, lista as linhas não
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

Tudo fica na pasta de saída (`outputs/pipeline` por padrão), ignorada pelo Git:

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
| `summary.json` | Janela, situação da execução, totais por etapa, medianas da amostra, distribuição das classificações e uso da API |
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
