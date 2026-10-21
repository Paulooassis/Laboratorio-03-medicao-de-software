# C1 — classificação DORA de referência

Gerado por `python -m analise`. A C1 é a combinação de referência da análise de
sensibilidade (RQ 07) e o resultado que resume as RQ 01 a 04: deployment = release
publicada, Lead Time pela variante (a) por release, Change Failure Rate pela variante (a)
proxy de CI e tempo de recuperação da primeira falha ao primeiro sucesso do mesmo
workflow. As faixas são as da tabela de referência do enunciado, implementadas em
`dora_selection/rating.py` — a análise não as reescreve, para que exista uma definição só
no repositório.

## Decisão 1 — o fallback do Lead Time

`lead_time_rating` classifica pela variante (a) e, quando ela não existe, cai para a (b)
por commit. 0 de 300 repositórios foram classificados assim e, a rigor, não estão na C1.
As duas leituras saem no mesmo CSV:

- `lead_time_level` e `overall`: C1 **estrita**, só com a variante (a); sem ela o Lead
  Time fica sem classificação e o nível geral sai da mediana das outras três métricas.
- `lead_time_level_com_fallback` e `overall_com_fallback`: a regra de hoje do pipeline.

A escolha muda o nível geral de 0 repositórios. **Decisão registrada: opção (2)** — a C1
usa só a variante (a) e esses repositórios ficam sem classificação de Lead Time. O motivo
é a RQ 07: ela compara a C1 com a C4 (release + (b) + (b)) justamente para separar o
efeito de trocar a unidade de deploy do de trocar a variante da métrica, e aceitar o
fallback na referência colocaria repositórios híbridos C1/C4 dentro dela, contaminando a
comparação. A tabela e a figura da distribuição seguem essa decisão; a leitura com
fallback fica no CSV para quem quiser reproduzir a regra do pipeline, sem refazer a
análise.

## Decisão 2 — métrica sem classificação

O nível geral é a **mediana das notas das métricas disponíveis** (Elite = 4 a Low = 1),
arredondada para baixo; o repositório só fica sem nível geral quando nenhuma das quatro
métricas foi classificada. Uma métrica ausente nunca é tratada como zero nem como Elite e
não entra na mediana — é por isso que um repositório com três métricas ainda recebe nível
geral, calculado sobre essas três.

268 de 300 repositórios têm as quatro métricas classificadas na C1, 32 têm menos de quatro
e 0 ficaram sem nenhuma, portanto sem nível geral. A distribuição completa está em
`resultados/tabelas/classificacao_c1_cobertura.csv`.

## Reprodutibilidade a partir do CSV

Os níveis foram recalculados a partir das colunas de `repositorios.csv` e comparados com o
que o pipeline gravou: 300 de 300 repositórios batem em todas as quatro métricas e no
nível geral, e 0 divergem (detalhe em
`resultados/tabelas/classificacao_c1_divergencias.csv`).

A comparação usa a leitura com fallback, que é a regra implementada no pipeline; o tempo
de recuperação sem nenhum episódio recuperado é reconstruído do limite inferior dos
censurados em `episodios_falha.csv`, como faz `recovery_time_rating`.

## Distribuição

Classificação geral (C1 estrita): Elite 9 (3,0%), High 110 (36,7%), Medium 154 (51,3%),
Low 27 (9,0%), Sem classificação 0 (0,0%). A distribuição por métrica está em
`resultados/tabelas/classificacao_c1_distribuicao.csv` (contagem) e
`classificacao_c1_distribuicao_percentual.csv` (proporção), e na figura
`resultados/figuras/classificacao_c1_distribuicao.pdf`.
