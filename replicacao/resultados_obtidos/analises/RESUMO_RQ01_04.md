# RQ 01 a 04 e classificação DORA de referência (C1)

Gerado por `python -m analises.rq01_04` a partir de `data/dataset.csv` (30 repositórios). Valores reportados como mediana e IQR (1º a 3º quartil), como pede o enunciado.

## Estatística descritiva (RQ 01 a 04)

| RQ | Métrica | Variante | n | Mediana | 1º quartil | 3º quartil | Categoria da mediana |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RQ 01 | Deployment frequency | - | 30 | 0,403 | 0,187 | 0,820 | Medium |
| RQ 02 | Lead time | (a) por release | 30 | 216,4 h (9,0 d) | 41,9 h (1,7 d) | 624,9 h (26,0 d) | Medium |
| RQ 02 | Lead time | (b) por commit | 30 | 204,0 h (8,5 d) | 29,8 h (1,2 d) | 468,4 h (19,5 d) | Medium |
| RQ 03 | Change failure rate | (a) proxy de CI | 30 | 2,5% | 0,2% | 11,7% | Elite |
| RQ 03 | Change failure rate | (b) proxy de entrega | 30 | 13,8% | 2,3% | 33,6% | Elite |
| RQ 04 | Tempo de recuperação | - | 23 | 18,8 h (0,8 d) | 3,3 h (0,1 d) | 83,1 h (3,5 d) | High |

## Classificação C1 (release, lead time (a), CFR (a) e recuperação)

| Métrica | n | Low | Medium | High | Elite | Sem valor |
| --- | --- | --- | --- | --- | --- | --- |
| Frequência de deploy | 30 | 8 (26,7%) | 16 (53,3%) | 6 (20,0%) | 0 (0,0%) | 0 |
| Lead time (a) | 30 | 7 (23,3%) | 9 (30,0%) | 10 (33,3%) | 4 (13,3%) | 0 |
| CFR (a) | 30 | 0 (0,0%) | 2 (6,7%) | 2 (6,7%) | 26 (86,7%) | 0 |
| Tempo de recuperação | 23 | 3 (13,0%) | 6 (26,1%) | 11 (47,8%) | 3 (13,0%) | 7 |
| Geral (C1) | 30 | 3 (10,0%) | 13 (43,3%) | 11 (36,7%) | 3 (10,0%) | 0 |

A categoria geral é a mediana das notas (Elite=4 … Low=1), arredondada para baixo. 7 repositórios não tiveram nenhum episódio de recuperação na janela; para eles a categoria geral usa as 3 métricas disponíveis (coluna `n_metricas`).

## Casos censurados e releases fora do cálculo

| RQ | Descrição | Valor | Total | % |
| --- | --- | --- | --- | --- |
| RQ 04 | repos sem nenhum episódio de recuperação na janela | 7 | 30 | 23,3% |
| RQ 04 | repos com algum episódio censurado | 6 | 30 | 20,0% |
| RQ 04 | mediana da proporção de episódios censurados por repo | 0 | – | – |
| RQ 04 | média da proporção de episódios censurados por repo | 0,0514 | – | – |
| RQ 04 | episódios de recuperação (total) | 370 | – | – |
| RQ 03 (b) | releases censuradas (últimos 7 dias da janela) | 16 | 1202 | 1,3% |
| RQ 02 | releases sem release anterior | 4 | 1202 | 0,3% |
| RQ 02 | releases com compare indisponível (404/422) | 0 | 1202 | 0,0% |
| RQ 02 | releases sem commits novos | 185 | 1202 | 15,4% |
| RQ 02 | repos com mediana do lead time (b) <= 0 (datas de autor posteriores à release) | 0 | 30 | 0,0% |

## Inovação: frequência efetiva (sem releases repetidas de monorepos)

Contando só releases com commits novos, a mediana da frequência passa de 0,403 para 0,403 releases/semana, e **3 repositórios (10,0%) mudam de categoria** de frequência. Dos 0 repositórios Elite em frequência, 0 deixam de ser Elite: a frequência alta vem de várias releases publicadas sobre o mesmo commit.

| Categoria original \ efetiva | Low | Medium | High | Elite |
| --- | --- | --- | --- | --- |
| Low | 8 | 0 | 0 | 0 |
| Medium | 1 | 15 | 0 | 0 |
| High | 0 | 2 | 4 | 0 |
| Elite | 0 | 0 | 0 | 0 |

Maiores diferenças:

| Repositório | Releases | Com commits novos | Freq. original | Freq. efetiva |
| --- | --- | --- | --- | --- |
| subquery/subql | 163 | 48 | 3,126 | 0,920 |
| dmno-dev/varlock | 69 | 25 | 1,323 | 0,479 |
| HotCakeX/Harden-Windows-Security | 111 | 98 | 2,129 | 1,879 |
| Tencent/cherry-markdown | 17 | 10 | 0,326 | 0,192 |
| langwatch/langwatch | 86 | 82 | 1,649 | 1,573 |

## Limitação: sobreposição com a amostra-ouro

Apenas 0 dos 45 repositórios da amostra-ouro estão no dataset final, porque a amostra-ouro foi sorteada antes da aplicação do critério de inclusão. Por isso a comparação das categorias com o rótulo manual "entrega real" não tem tamanho de amostra suficiente e não é reportada.

## Figuras

- `fig_rq01_04_boxplots.png`: distribuição das métricas (RQ 01 a 04)
- `fig_categorias_C1.png`: distribuição das categorias DORA por métrica (C1)
- `fig_heatmap_C1.png`: perfil DORA de cada repositório (C1)
