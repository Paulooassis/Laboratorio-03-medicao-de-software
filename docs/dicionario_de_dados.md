# Dicionário de dados

Documenta cada coluna dos CSVs finais em `data/processed`, gerados por
`python -m pipeline --config config.yaml` (seção S2-10 do [README](../README.md)).
Serve para que outro grupo replique o pipeline e compare os resultados coluna a coluna.

| Arquivo | Uma linha por | Linhas na amostra final |
| --- | --- | ---: |
| [`repositorios.csv`](#repositorioscsv) | repositório incluído | 300 |
| [`releases.csv`](#releasescsv) | release válida publicada na janela | 18.389 |
| [`episodios_falha.csv`](#episodios_falhacsv) | episódio de falha de um workflow | 20.117 |
| [`variantes.csv`](#variantescsv) | repositório × unidade de deploy (RQ 07) | 900 |
| [`deploys_variantes.csv`](#deploys_variantescsv) | deploy de cada unidade (RQ 07) | a preencher após a coleta |
| [`funil.md`](#funilmd) | etapa da seleção (tabela Markdown, não CSV) | — |

## Convenções

- **Janela:** de `inicio` a `fim` do `config.yaml`, inclusiva, em UTC, com precisão de
  segundos (2025-01-01T00:00:00Z a 2025-12-31T23:59:59Z). `fim da janela` nas fórmulas
  é esse instante.
- **Release válida:** release com `draft = false`, `prerelease = false` e `published_at`
  dentro da janela. Pré-releases e drafts não aparecem em `repositorios.csv`,
  `releases.csv` nem `episodios_falha.csv`; as pré-releases só entram nos dois CSVs de
  variantes da RQ 07.
- **Unidade de deploy (RQ 07):** `release` (a definição principal), `release_prerelease`
  (releases e pré-releases da janela numa só sequência) e `tag` (veja
  [`variantes.csv`](#variantescsv)).
- **Workflow run válido:** run de `GET /repos/{owner}/{repo}/actions/runs` com
  `head_branch` igual ao branch padrão, `event = push`, `created_at` na janela e
  `status = completed`. É classificado como `success` (`conclusion = success`), `failure`
  (`conclusion` em `failure`, `timed_out`, `startup_failure`) ou `ignored` (demais
  conclusões, como `cancelled`, `skipped`, `neutral`, `action_required`, `stale`, ou run
  ainda em andamento).
- **Datas:** strings ISO 8601 em UTC. As copiadas da API terminam em `Z`
  (`2025-11-25T13:24:35Z`); as calculadas pelo pipeline terminam em `+00:00`. Ambas
  representam o mesmo fuso.
- **Durações:** `float` em **horas**, calculadas como diferença em segundos dividida
  por 3600, sem arredondamento.
- **Lead Time:** a data do commit é sempre `commit.author.date`, nunca
  `commit.committer.date`.
- **Booleanos:** escritos como `True` ou `False`.
- **Célula vazia:** valor ausente ou métrica sem amostra (por exemplo, divisão com
  denominador zero). Nunca significa zero.
- **Mediana:** `statistics.median` do Python; com quantidade par de valores, é a média
  dos dois centrais.
- **Medida no momento da coleta:** `stars` e `contributors` vêm da API no instante da
  consulta e mudam com o tempo; a replicação deve esperar diferenças pequenas nessas
  colunas.

### Endpoints da API REST do GitHub

| Abreviação | Endpoint |
| --- | --- |
| busca | `GET /search/repositories?q=is:public stars:A..B` |
| contributors | `GET /repos/{owner}/{repo}/contributors?anon=true&per_page=1` |
| releases | `GET /repos/{owner}/{repo}/releases` |
| tags | `GET /repos/{owner}/{repo}/tags` |
| compare | `GET /repos/{owner}/{repo}/compare/{base}...{head}` (todas as páginas) |
| tags (GraphQL) | `POST /graphql`: `repository.refs(refPrefix: "refs/tags/", orderBy: {field: TAG_COMMIT_DATE, direction: DESC})`, com `authoredDate` do commit apontado |
| runs | `GET /repos/{owner}/{repo}/actions/runs?branch={padrão}&event=push&created={período}` |

`base` e `head` do compare são os SHAs das tags da release anterior e da atual (o nome
da tag quando o SHA não está disponível). A release anterior da primeira release da
janela é a última release válida publicada antes dela, mesmo fora da janela.

## repositorios.csv

Uma linha por repositório incluído na amostra, na ordem da seleção (estrelas
decrescentes).

### Identificação e fatores da RQ 06

| Coluna | Tipo | Unidade | Descrição / fórmula | Origem |
| --- | --- | --- | --- | --- |
| `repository` | string | — | Nome `owner/repo`, com a grafia devolvida pela API | busca: `full_name` |
| `url` | string | — | Endereço do repositório no GitHub | busca: `html_url` |
| `stars` | int | estrelas | Estrelas no momento da busca | busca: `stargazers_count` |
| `language` | string | — | Linguagem principal detectada pelo GitHub; vazia quando o GitHub não detecta | busca: `language` |
| `contributors` | int | pessoas | Contribuidores, incluindo anônimos: número da última página com `per_page=1` | contributors: header `Link`, `rel="last"` |
| `created_at` | datetime | — | Data de criação do repositório | busca: `created_at` |
| `age_days` | int | dias | Dias inteiros completos entre `created_at` e o fim da janela: `floor((fim da janela − created_at) / 1 dia)` | derivada de `created_at` |
| `project_type` | string | — | Tipo do projeto por consenso dos avaliadores: `library/framework`, `application/service`, `cli` ou `other`. Vazia fora da amostra-ouro | `validacao/resultados/tipo_projeto.csv` (S2-06), não vem da API |
| `gold_sample` | bool | — | `True` quando o repositório pertence à amostra-ouro de 60 repositórios, ou seja, tem `project_type` | idem |
| `collection_complete` | bool | — | `True` quando os workflow runs foram coletados em todos os meses e a listagem de releases não teve erro. Falha em um compare isolado não torna a coleta incompleta | pipeline |

### Deployment Frequency

| Coluna | Tipo | Unidade | Descrição / fórmula | Origem |
| --- | --- | --- | --- | --- |
| `releases` | int | releases | Quantidade de releases válidas na janela | releases: `draft`, `prerelease`, `published_at` |
| `deployment_frequency_per_week` | float | releases/semana | `releases / semanas da janela`, com `semanas da janela = (fim − início + 1 s) / 604800 s` (52,14 semanas na janela de 2025) | releases |
| `median_releases_per_week` | float | releases/semana | Mediana da contagem de releases por semana ISO (segunda a domingo, UTC), considerando todas as semanas que cobrem a janela, inclusive as sem release e as parciais das pontas | releases: `published_at` |

### Lead Time

| Coluna | Tipo | Unidade | Descrição / fórmula | Origem |
| --- | --- | --- | --- | --- |
| `lead_time_a_hours` | float | horas | **Variante (a), por release.** Mediana, entre as releases medidas, de `published_at − min(commit.author.date)`, sendo o mínimo tomado entre os commits do intervalo entre a release anterior e a atual | releases + tags + compare: `commits[].commit.author.date` |
| `lead_time_a_releases` | int | releases | Releases que entraram na mediana de `lead_time_a_hours` (`lead_time_status = measured` em `releases.csv`) | pipeline |
| `lead_time_b_hours` | float | horas | **Variante (b), por commit.** Mediana de `published_at − commit.author.date` sobre todos os commits de todas as releases medidas do repositório, juntos (não é a mediana das medianas por release) | releases + tags + compare |
| `lead_time_b_commits` | int | commits | Commits que entraram na mediana de `lead_time_b_hours` | pipeline |
| `releases_ignored` | int | releases | Releases válidas que não produzem Lead Time, por qualquer motivo. É a soma de `releases_no_previous`, `releases_compare_not_found`, `releases_compare_error`, `releases_no_new_commits` e `releases_no_commit_dates`, mais releases sem `published_at` (zero na coleta real) | pipeline |
| `releases_no_previous` | int | releases | Primeira release da história do repositório: não há release anterior para comparar | releases |
| `releases_compare_not_found` | int | releases | Compare respondeu HTTP 404, por exemplo por tag apagada | compare: status HTTP |
| `releases_compare_error` | int | releases | Compare falhou com outro erro definitivo, por exemplo HTTP 422 | compare: status HTTP |
| `releases_no_new_commits` | int | releases | Compare válido e vazio: a release não trouxe commits novos. Continua contando em `releases` | compare: `commits` vazio |
| `releases_no_commit_dates` | int | releases | Compare com commits, mas nenhum com `commit.author.date` legível | compare |

Lead Times negativos (commit com data de autor posterior à publicação, possível com
rebase ou cherry-pick) são mantidos nas medianas.

### Change Failure Rate

| Coluna | Tipo | Unidade | Descrição / fórmula | Origem |
| --- | --- | --- | --- | --- |
| `cfr_a` | float | proporção (0 a 1) | **Variante (a), por workflow run.** `cfr_a_failures / cfr_a_runs` | runs: `status`, `conclusion` |
| `cfr_a_runs` | int | runs | Denominador do CFR (a): runs válidos classificados como `success` ou `failure` | runs |
| `cfr_a_failures` | int | runs | Runs válidos classificados como `failure` | runs: `conclusion` |
| `runs_ignored` | int | runs | Runs válidos classificados como `ignored`, fora do denominador | runs: `conclusion` |
| `cfr_b` | float | proporção (0 a 1) | **Variante (b), por entrega.** `cfr_b_failed / cfr_b_evaluated`. Uma release falha quando, em até 7 dias depois dela (`published_at < posterior ≤ published_at + 7 dias`), é publicada uma release corretiva da mesma linha `major.minor` | releases + compare: `tag_name`, `published_at`, mensagens dos commits |
| `cfr_b_version` | string | — | Versão da heurística de release corretiva aprovada em `config.yaml` (`v1`). Regra completa em [validacao/heuristica_versoes.md](../validacao/heuristica_versoes.md) | `config.yaml` |
| `cfr_b_evaluated` | int | releases | Denominador do CFR (b): releases com 7 dias observados depois da publicação | pipeline |
| `cfr_b_failed` | int | releases | Releases avaliadas seguidas por uma corretiva em até 7 dias | pipeline |
| `cfr_b_corrective` | int | releases | Releases que a heurística classifica como corretivas, incluindo as censuradas | pipeline |
| `cfr_b_censored` | int | releases | Releases publicadas nos últimos 7 dias da janela (`published_at > fim − 7 dias`): ficam fora do denominador | releases: `published_at` |

Heurística `v1`, resumida: com tag SemVer, a release é corretiva quando, em relação à
anterior da mesma linha, muda apenas o patch (sem anterior menor, quando o próprio patch
é maior que zero); com tag fora do SemVer, quando ao menos metade das primeiras linhas
das mensagens dos commits contém `fix`, `hotfix` ou `revert` como palavra inteira.

### Rework rate (RQ 08)

A *deployment rework rate* que o DORA acrescentou em 2024: a proporção de entregas
não planejadas, feitas para corrigir problemas. Usa a mesma heurística `v1` do CFR (b),
mas mede a **própria correção**, e não a release que falhou. Por isso não há janela de
7 dias nem censura: uma correção publicada na última semana da janela conta.

| Coluna | Tipo | Unidade | Descrição / fórmula | Origem |
| --- | --- | --- | --- | --- |
| `rework_rate` | float | proporção (0 a 1) | `rework_corrective / rework_evaluated`; vazio sem nenhuma release avaliável | releases + compare |
| `rework_evaluated` | int | releases | Denominador: releases datadas da janela, exceto a primeira da história. As releases com `compare` em erro ficam no denominador, como no CFR (b) | releases: `comparison_status` |
| `rework_corrective` | int | releases | Releases avaliadas que a heurística classifica como corretivas | releases + compare: `tag_name`, mensagens |
| `rework_no_previous` | int | releases | Primeira release da história do repositório, sem release anterior para corrigir: fora do denominador | releases: `comparison_status` |

Difere de `cfr_b_corrective` por incluir as corretivas dos últimos 7 dias e por excluir a
primeira release da história; as duas contagens só coincidem se nenhuma dessas
situações ocorre.

### Tempo de recuperação

| Coluna | Tipo | Unidade | Descrição / fórmula | Origem |
| --- | --- | --- | --- | --- |
| `recovery_hours` | float | horas | Mediana de `recovery_hours` dos episódios recuperados e consistentes de todos os workflows do repositório, juntos (definição em [`episodios_falha.csv`](#episodios_falhacsv)) | runs |
| `recovery_episodes` | int | episódios | Episódios de falha de todos os workflows | runs |
| `recovery_recovered` | int | episódios | Episódios encerrados por um sucesso do mesmo workflow | runs |
| `recovery_censored` | int | episódios | Episódios sem sucesso posterior até o fim da janela | runs |
| `recovery_censored_share` | float | proporção (0 a 1) | `recovery_censored / recovery_episodes` (RQ 04); vazia sem episódios | pipeline |
| `recovery_inconsistent` | int | episódios | Episódios recuperados com fim anterior ao início; ficam fora da mediana | runs |

### Classificação DORA

| Coluna | Tipo | Unidade | Descrição / fórmula | Origem |
| --- | --- | --- | --- | --- |
| `deployment_frequency_level` | string | nível | Nível de `deployment_frequency_per_week`: Elite ≥ 7, High ≥ 1, Medium ≥ 0,23, Low < 0,23 | pipeline |
| `lead_time_level` | string | nível | Nível de `lead_time_a_hours` (ou `lead_time_b_hours` quando o (a) está vazio): Elite < 24, High < 168, Medium < 720, Low ≥ 720 | pipeline |
| `change_failure_rate_level` | string | nível | Nível de `cfr_a`: Elite ≤ 0,15, High ≤ 0,30, Medium ≤ 0,45, Low > 0,45 | pipeline |
| `recovery_time_level` | string | nível | Nível de `recovery_hours`: Elite < 1, High < 24, Medium < 168, Low ≥ 168. Sem episódio recuperado, a mediana de `observed_hours` dos censurados classifica como Low quando já é ≥ 168 h (nesse caso `recovery_hours` fica vazio e o nível é Low); caso contrário o nível fica vazio | pipeline |
| `median_score` | float | nota (1 a 4) | Mediana das notas dos níveis disponíveis (Elite = 4, High = 3, Medium = 2, Low = 1) | pipeline |
| `overall` | string | nível | Classificação geral: nível de `floor(median_score)`; vazia sem nenhum nível | pipeline |

Os níveis valem `Elite`, `High`, `Medium` ou `Low`; vazio quando a métrica não tem
amostra. A classificação usa o CFR (a); o CFR (b) não entra em nenhum nível.

## releases.csv

Uma linha por release válida da janela, agrupadas por repositório e ordenadas por
`published_at` (desempate pelo `release_id`). Inclui as releases que não produzem
Lead Time, com o motivo em `lead_time_status`.

| Coluna | Tipo | Unidade | Descrição / fórmula | Origem |
| --- | --- | --- | --- | --- |
| `repository` | string | — | Nome `owner/repo`, igual a `repositorios.csv` | busca: `full_name` |
| `release_id` | int | — | Identificador da release no GitHub | releases: `id` |
| `tag_name` | string | — | Tag da release | releases: `tag_name` |
| `published_at` | datetime | — | Publicação da release | releases: `published_at` |
| `previous_tag_name` | string | — | Tag da release anterior usada como base do compare (pode ser anterior à janela); vazia na primeira release da história | releases |
| `comparison_status` | string | — | Resultado do compare: `completed`, `no_previous_release`, `not_found` (HTTP 404) ou `error` (outro erro) | compare |
| `lead_time_status` | string | — | `measured` ou o motivo de não medir: `no_previous_release`, `no_comparison` (compare `not_found` ou `error`), `no_date`, `no_commits` (sem commits novos) ou `no_commit_dates` | pipeline |
| `commits` | int | commits | Commits devolvidos pelo compare entre `previous_tag_name` e `tag_name`, sem duplicatas de SHA | compare: `commits` |
| `measured_commits` | int | commits | Commits com `commit.author.date` legível | compare |
| `first_commit_author_date` | datetime | — | `min(commit.author.date)` dos commits da release | compare: `commits[].commit.author.date` |
| `lead_time_a_hours` | float | horas | `published_at − first_commit_author_date` (Lead Time (a) da release) | releases + compare |
| `lead_time_b_hours` | float | horas | Mediana de `published_at − commit.author.date` entre os commits desta release | releases + compare |
| `corrective` | bool | — | A heurística `v1` classifica a release como corretiva | releases + compare: `tag_name`, mensagens |
| `cfr_b_censored` | bool | — | Publicada nos últimos 7 dias da janela; fora do denominador do CFR (b) | releases: `published_at` |
| `cfr_b_failed` | bool | — | Seguida por uma corretiva da mesma linha `major.minor` em até 7 dias. Sempre `False` quando censurada | pipeline |
| `fixed_by_tag_name` | string | — | Tag da primeira corretiva que caracterizou a falha; vazia quando não falhou | pipeline |

As colunas `lead_time_*` ficam vazias quando `lead_time_status` não é `measured`; as
quatro últimas ficam vazias se nenhuma versão da heurística estiver aprovada em
`config.yaml`.

## episodios_falha.csv

Uma linha por episódio de falha. Cada workflow é uma série independente, com seus runs
válidos ordenados por `created_at` (desempate pelo `id`). Um episódio começa na
primeira falha depois de um sucesso (ou no início da série), agrupa as falhas
consecutivas e termina no primeiro sucesso seguinte do mesmo workflow. Runs `ignored`
não abrem, não estendem e não encerram episódios.

| Coluna | Tipo | Unidade | Descrição / fórmula | Origem |
| --- | --- | --- | --- | --- |
| `repository` | string | — | Nome `owner/repo`, igual a `repositorios.csv` | busca: `full_name` |
| `workflow_id` | int | — | Identificador do workflow | runs: `workflow_id` |
| `workflow_name` | string | — | Nome do workflow, tomado do primeiro run coletado dele | runs: `name` |
| `failure_run_id` | int | — | Primeiro run com falha do episódio | runs: `id` |
| `failures` | int | runs | Runs com falha consecutivos no episódio | runs |
| `started_at` | datetime | — | Início do primeiro run com falha | runs: `run_started_at` (na falta, `created_at`) |
| `recovery_run_id` | int | — | Run com sucesso que encerrou o episódio; vazio quando censurado | runs: `id` |
| `recovered_at` | datetime | — | Fim do run que encerrou o episódio | runs: `updated_at` (na falta, `created_at`) |
| `recovery_hours` | float | horas | `recovered_at − started_at`; vazio quando censurado | runs |
| `observed_hours` | float | horas | Só nos censurados: limite inferior da recuperação, de `started_at` até o mais tardio entre o fim da janela e o fim do último run com falha | runs |
| `recovered` | bool | — | O episódio terminou em sucesso dentro da janela | pipeline |
| `censored` | bool | — | Sem sucesso posterior até o fim da janela; sempre o oposto de `recovered` | pipeline |
| `inconsistent` | bool | — | Recuperado com `recovery_hours` negativo; fora da mediana | pipeline |

## variantes.csv

Metade da análise de sensibilidade (RQ 07): as métricas que dependem da **unidade de
deploy**, calculadas para cada uma das três unidades. Só existe quando
`coleta.variantes` é `true` no `config.yaml`. Uma linha por repositório e unidade, na
ordem `release`, `release_prerelease`, `tag` de cada repositório.

| Unidade | Deploy | Data do deploy | Base da 1ª comparação |
| --- | --- | --- | --- |
| **release** | Release publicada (definição principal; repete `repositorios.csv`) | `published_at` | Última release publicada antes da janela |
| **release_prerelease** | Release ou pré-release publicada na janela | `published_at` | Última release (não pré-release) antes da janela |
| **tag** | Commit apontado por uma ou mais tags da janela | `commit.author.date` do commit da tag | Tag mais recente com commit anterior à janela |

Na unidade `tag`, tags que apontam para o mesmo commit contam como **um** deploy, para
que um monorepo que marca vários pacotes de uma vez não multiplique a frequência; o nome
do deploy é o da primeira tag em ordem alfabética. Tags anotadas são seguidas até o
commit. Como a data da tag é a do commit, o Lead Time dessa unidade é menor que o das
releases (o deploy acontece quando o commit foi escrito, não quando foi publicado).
Cada deploy é comparado (`compare`) com o **anterior da mesma unidade**. As fórmulas
das métricas são as de `repositorios.csv`, com "release" lido como "deploy".

| Coluna | Tipo | Unidade | Descrição / fórmula | Origem |
| --- | --- | --- | --- | --- |
| `repository` | string | — | Nome `owner/repo`, igual a `repositorios.csv` | busca: `full_name` |
| `unit` | string | — | `release`, `release_prerelease` ou `tag` | pipeline |
| `deploys` | int | deploys | Deploys da unidade com data dentro da janela | releases / tags (GraphQL) |
| `deploys_without_date` | int | deploys | Deploys sem data legível, fora da contagem | pipeline |
| `tags` | int | tags | Tags que formam os deploys (maior que `deploys` quando tags dividem o mesmo commit); nas outras unidades, igual a `deploys` | tags |
| `deployment_frequency_per_week` | float | deploys/semana | `deploys ÷ (duração da janela em semanas)` | pipeline |
| `lead_time_a_hours` | float | horas | Mediana, entre os deploys, de `data do deploy − commit.author.date` mais antigo do deploy | compare |
| `lead_time_a_deploys` | int | deploys | Deploys que entraram na mediana de `lead_time_a_hours` | pipeline |
| `lead_time_b_hours` | float | horas | Mediana de `data do deploy − commit.author.date` entre todos os commits de todos os deploys | compare |
| `lead_time_b_commits` | int | commits | Commits que entraram na mediana de `lead_time_b_hours` | compare |
| `deploys_ignored` | int | deploys | Deploys sem Lead Time, somados os motivos abaixo | pipeline |
| `deploys_no_previous` | int | deploys | Primeiro deploy da unidade, sem base para o compare | pipeline |
| `compare_not_found` | int | deploys | Compare com HTTP 404 (tag apagada ou reescrita) | compare |
| `compare_error` | int | deploys | Compare com outro erro | compare |
| `deploys_no_new_commits` | int | deploys | Compare válido sem commits novos | compare |
| `deploys_no_commit_dates` | int | deploys | Commits sem `commit.author.date` legível | compare |
| `cfr_b` | float | proporção | CFR (b) da unidade: `cfr_b_failed ÷ cfr_b_evaluated`, pela heurística `v1`; vazio sem deploy avaliado | pipeline |
| `cfr_b_evaluated` | int | deploys | Deploys fora dos últimos 7 dias da janela | pipeline |
| `cfr_b_failed` | int | deploys | Avaliados seguidos, em até 7 dias, de um deploy corretivo da mesma linha `major.minor` | pipeline |
| `cfr_b_corrective` | int | deploys | Deploys classificados como corretivos pela heurística | pipeline |
| `cfr_b_censored` | int | deploys | Publicados nos últimos 7 dias da janela, fora do denominador | pipeline |
| `collection_complete` | bool | — | A unidade foi coletada. `False` indica falha de coleta (datas das tags indisponíveis, listagem de releases com erro ou repositório fora da coleta), e as demais colunas da linha **não** significam "sem deploys". Um `compare` com 404 ou outro erro não torna a unidade incompleta: o deploy sai do Lead Time e é contado em `compare_not_found`/`compare_error` | pipeline |

O CFR (a) e o tempo de recuperação usam workflow runs e não dependem da unidade de
deploy; para eles vale `repositorios.csv`. Os níveis DORA de cada combinação são
calculados na análise (RQ 07) a partir destas colunas, com as mesmas faixas da C1.

## deploys_variantes.csv

Uma linha por deploy de cada unidade de `variantes.csv`, ordenadas por data (mesma
estrutura de `releases.csv`, mais a unidade). Permite auditar uma mediana até os deploys
e commits que a produziram.

| Coluna | Tipo | Unidade | Descrição / fórmula | Origem |
| --- | --- | --- | --- | --- |
| `repository` | string | — | Nome `owner/repo`, igual a `repositorios.csv` | busca: `full_name` |
| `unit` | string | — | `release`, `release_prerelease` ou `tag` | pipeline |
| `tag_name` | string | — | Tag do deploy; para tags no mesmo commit, a primeira em ordem alfabética | releases / tags |
| `tags` | int | tags | Tags que apontam para o commit do deploy | tags |
| `prerelease` | bool | — | O deploy é uma pré-release; vazio na unidade `tag` | releases: `prerelease` |
| `published_at` | datetime | — | Data do deploy: publicação (releases) ou `commit.author.date` do commit da tag | releases / tags (GraphQL) |
| `commit_sha` | string | — | Commit apontado pela tag | tags |
| `previous_tag_name` | string | — | Deploy anterior da mesma unidade usado como base do compare; vazio no primeiro | pipeline |
| `comparison_status` | string | — | `completed`, `no_previous_release`, `not_found` ou `error` | compare |
| `lead_time_status` | string | — | `measured` ou o motivo de não medir, como em `releases.csv` | pipeline |
| `commits` | int | commits | Commits devolvidos pelo compare, sem duplicatas de SHA | compare |
| `measured_commits` | int | commits | Commits com `commit.author.date` legível | compare |
| `lead_time_a_hours` | float | horas | `data do deploy − min(commit.author.date)` | compare |
| `lead_time_b_hours` | float | horas | Mediana de `data do deploy − commit.author.date` entre os commits do deploy | compare |
| `corrective` | bool | — | A heurística `v1` classifica o deploy como corretivo | tag_name, mensagens |
| `cfr_b_censored` | bool | — | Publicado nos últimos 7 dias da janela | pipeline |
| `cfr_b_failed` | bool | — | Seguido, em até 7 dias, por um corretivo da mesma linha `major.minor` | pipeline |
| `fixed_by_tag_name` | string | — | Deploy corretivo que caracterizou a falha | pipeline |

## funil.md

Tabela Markdown do funil de seleção, regravada a cada execução. Não é CSV, mas faz parte
da entrega.

| Linha | Descrição |
| --- | --- |
| Candidatos recebidos da busca | Itens recebidos nas páginas percorridas da busca, com duplicatas entre faixas |
| Repositórios únicos avaliados | Candidatos distintos (por `id`) avaliados até atingir a meta |
| Com GitHub Actions | Com ao menos um workflow em `GET /repos/{owner}/{repo}/actions/workflows` |
| Com 5 ou mais releases na janela | Dos anteriores, com 5 ou mais releases válidas |
| Com 50 ou mais workflow runs válidos | Dos anteriores, com 50 ou mais runs válidos classificados como `success` ou `failure` |
| Incluídos na amostra | Atendem a todos os critérios e foram coletados sem erro |
| Motivo de descarte | Contagem por motivo principal: `no_github_actions`, `insufficient_releases`, `insufficient_workflow_runs` ou `collection_error` |
