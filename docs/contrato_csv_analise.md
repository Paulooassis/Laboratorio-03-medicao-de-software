# Dicionário dos CSVs de análise

Contrato de leitura de `analise.comum` para a Sprint 3. Para o significado, o tipo e a
fórmula de cada coluna que o pipeline realmente grava, veja o
[dicionário de dados](dicionario_de_dados.md). Os três arquivos em `data/processed/`
são entradas da análise; nenhuma função de análise consulta a API. A unidade
estatística das comparações entre projetos é o repositório; releases e episódios
permitem reconstruir suas métricas e contabilizar exclusões.

## Regras de leitura

- CSV com cabeçalho, vírgula como separador, UTF-8 (BOM aceito), ponto decimal.
- `repository` é a coluna obrigatória nos três arquivos. Aceita-se `full_name`
  como apelido se `repository` não existir. Deve identificar o projeto como `dono/nome`.
- Todas as outras colunas são opcionais; quando faltam, são criadas como ausentes.
  As análises usam detalhes quando disponíveis ou publicam o valor ausente.
- Colunas numéricas usam `float64`, inclusive contagens, para representar NaN.
  Contagens e identificadores devem conter números inteiros quando presentes.
- Datas usam `datetime64[ns, UTC]`: offsets são convertidos para UTC; datas sem
  fuso são interpretadas como UTC. Datas inválidas e vazias viram `NaT`.
- Células vazias, só com espaços e marcadores padrão de ausente do pandas
  (`NaN`, `NA`, `NULL` etc.) são ausentes. Números inválidos viram NaN, sem imputação.
- Textos usam `string` com `pd.NA` e espaços externos removidos. Booleanos usam
  `boolean` com `pd.NA`; são aceitos `true/false`, `1/0`, `sim/não`, `yes/no`,
  `t/f`, `y/n`, sem distinção entre maiúsculas e minúsculas. Outros valores são NA.
- Colunas extras são ignoradas. Um arquivo sem registros deve manter o cabeçalho.
  Os três arquivos precisam existir, mesmo quando não há releases ou episódios.
- Zero é uma medição válida e não é convertido em ausente. Taxas usam frações
  de 0 a 1; durações usam horas. Resumos usam mediana e IQR, nunca média e desvio padrão.

## repositorios.csv

Uma linha por repositório. As colunas principais correspondem ao resumo do pipeline
em `dora_selection.output.DORA_FIELDS`; as demais dão suporte a exclusões e variantes.

| Coluna(s) | Tipo | Significado / unidade |
| --- | --- | --- |
| `repository` | texto, obrigatória | Identificador `dono/nome` |
| `stars`, `contributors` | número | Estrelas e contribuidores |
| `language` | texto | Linguagem principal |
| `created_at` | data UTC | Criação do repositório |
| `window_start`, `window_end` | data UTC | Limites da janela de observação |
| `collection_complete` | booleano | Coleta completa |
| `releases` | número | Releases na janela |
| `releases_per_week` | número | Deployment Frequency, releases/semana |
| `release_lead_time_hours` | número | Lead Time (a), mediana por release em horas |
| `commit_lead_time_hours` | número | Lead Time (b), mediana por commit em horas |
| `releases_no_previous` | número | Releases ignoradas por não ter release anterior |
| `releases_compare_not_found` | número | Releases cujo compare retornou 404 |
| `releases_compare_error` | número | Releases com outros erros no compare |
| `releases_no_new_commits` | número | Releases sem commits novos |
| `releases_no_commit_dates` | número | Releases com commits sem data |
| `releases_no_date` | número | Releases sem data de publicação |
| `considered_runs`, `ignored_runs` | número | Runs considerados e ignorados no CFR (a) |
| `change_failure_rate` | número | CFR (a), fração de runs considerados que falharam |
| `delivery_change_failure_rate` | número | CFR (b), fração de releases avaliadas que falharam |
| `recovery_hours` | número | Mediana do tempo de recuperação, em horas |
| `censored_episodes` | número | Episódios sem recuperação observada na janela |
| `deployment_frequency_level`, `lead_time_level`, `change_failure_rate_level`, `recovery_time_level` | texto | Classificações do pipeline: `Elite`, `High`, `Medium`, `Low` ou ausente |
| `median_score` | número | Mediana das notas DORA disponíveis (Elite=4, High=3, Medium=2, Low=1) |
| `overall` | texto | Classificação geral do pipeline |

`cfr_entrega` e `change_failure_rate_delivery` são apelidos de
`delivery_change_failure_rate`, usados somente se a coluna canônica não existir.

## releases.csv

Uma linha por release. Identificação lógica: `repository` + `release_id`.

| Coluna(s) | Tipo | Significado / unidade |
| --- | --- | --- |
| `repository` | texto, obrigatória | Repositório de origem |
| `release_id` | número | Identificador da release |
| `tag_name`, `previous_tag_name` | texto | Tags atual e anterior da comparação |
| `published_at` | data UTC | Publicação da release |
| `first_commit_author_date`, `last_commit_author_date` | data UTC | Datas de autoria do primeiro e último commit do intervalo |
| `commits`, `measured_commits` | número | Commits no intervalo e com Lead Time mensurável |
| `lead_time_hours` | número | Lead Time (a), do commit mais antigo à publicação, em horas |
| `median_commit_lead_time_hours` | número | Mediana dos Lead Times (b) dos commits, em horas |
| `status` | texto | Estado do cálculo: inclui `no_previous_release`, `no_commits`, `no_commit_dates`, `no_date` |
| `comparison_status` | texto | Estado do compare: inclui `completed`, `not_found`, `error` |
| `corrective` | booleano | Release identificada como corretiva |
| `censored` | booleano | Não há sete dias completos de seguimento após a release |
| `failed` | booleano | Veredito da heurística de CFR de entrega |
| `fixed_by_tag_name` | texto | Tag da release corretiva associada |

## episodios_falha.csv

Uma linha por episódio: da primeira falha até o primeiro sucesso do mesmo workflow,
ou até o fim da janela se censurado.

| Coluna(s) | Tipo | Significado / unidade |
| --- | --- | --- |
| `repository` | texto, obrigatória | Repositório de origem |
| `workflow_id`, `failure_run_id` | número | Workflow e run que iniciou o episódio |
| `failures` | número | Falhas no episódio |
| `started_at`, `recovered_at` | data UTC | Início e recuperação; recuperação ausente nos censurados |
| `recovery_hours` | número | Tempo até recuperação observada, em horas; ausente nos censurados |
| `observed_hours` | número | Duração observada até recuperação ou fim da janela, em horas |
| `recovered` | booleano | Houve sucesso posterior na janela |
| `censored` | booleano | Episódio ainda aberto no fim da janela |
| `inconsistent` | booleano | Datas contraditórias; excluído das estimativas de recuperação |

As fixtures de `tests/test_analise_comum.py` servem somente para validar leitura,
estatística e execução. Não representam resultados empíricos do estudo.

## Dois nomes para a mesma coluna

Os CSVs em `data/processed/` foram gerados pela etapa de coleta **antes** deste
dicionário e trazem os nomes do pipeline, que diferem dos documentados abaixo. A leitura
em `analise/comum.py` aceita os dois, então nenhuma análise precisa ser ajustada; a
tabela existe para que ninguém procure uma coluna que está lá com outro nome.

| Nome no CSV coletado | Nome neste dicionário |
| --- | --- |
| `deployment_frequency_per_week` | `releases_per_week` |
| `lead_time_a_hours` | `release_lead_time_hours` |
| `lead_time_b_hours` | `commit_lead_time_hours` |
| `cfr_a` | `change_failure_rate` |
| `cfr_a_runs` | `considered_runs` |
| `runs_ignored` | `ignored_runs` |
| `cfr_b` | `delivery_change_failure_rate` |
| `recovery_censored` | `censored_episodes` |
| `lead_time_status` (releases) | `status` |
| `lead_time_a_hours` (releases) | `lead_time_hours` |
| `lead_time_b_hours` (releases) | `median_commit_lead_time_hours` |
| `cfr_b_censored`, `cfr_b_failed` (releases) | `censored`, `failed` |

Uma execução futura do pipeline continuará escrevendo os nomes da coluna da esquerda.
Unificar os dois lados é trabalho de outra Issue; até lá, os apelidos garantem que
`python -m analise` funcione sobre o arquivo publicado.
