# Dicionário de dados

Documenta cada coluna dos CSVs finais em `data/processed`, gerados por
`python -m pipeline --config config.yaml` (seção S2-10 do [README](../README.md)).
Serve para que outro grupo replique o pipeline e compare os resultados coluna a coluna.

| Arquivo | Uma linha por | Linhas na amostra final |
| --- | --- | ---: |
| [`repositorios.csv`](#repositorioscsv) | repositório incluído | 300 |
| [`releases.csv`](#releasescsv) | release válida publicada na janela | 18.389 |
| [`episodios_falha.csv`](#episodios_falhacsv) | episódio de falha de um workflow | 20.117 |
| [`funil.md`](#funilmd) | etapa da seleção (tabela Markdown, não CSV) | — |

## Convenções

- **Janela:** de `inicio` a `fim` do `config.yaml`, inclusiva, em UTC, com precisão de
  segundos (2025-01-01T00:00:00Z a 2025-12-31T23:59:59Z). `fim da janela` nas fórmulas
  é esse instante.
- **Release válida:** release com `draft = false`, `prerelease = false` e `published_at`
  dentro da janela. Pré-releases e drafts não aparecem em nenhum CSV.
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
