# RQ 08 (bônus) — Rework rate

O rework rate é a proporção de releases corretivas entre as releases avaliadas de cada
repositório, com a heurística `v1` da RQ 03 (b). Entre os 300 repositórios com taxa
definida, a mediana é 0,700 (IQR 0,406; Q1 = 0,462; Q3 = 0,867). Somando todas as
releases, 12020 de 18366 são corretivas (0,654). Fonte: releases.csv; a primeira release
da história de cada repositório (23 no total) fica fora do denominador por não ter release
anterior para corrigir.

## Em que difere do CFR (b)

O CFR (b) marca a release que falhou, isto é, a que foi seguida por uma corretiva em até 7
dias; o rework rate marca a própria correção, sem janela de tempo. Há três consequências.
Primeiro, uma correção publicada depois de mais de 7 dias é retrabalho para o rework rate
e passa despercebida pelo CFR (b). Segundo, o CFR (b) censura as releases dos últimos 7
dias da janela e o rework rate não censura ninguém. Terceiro, uma única corretiva pode ser
a 'próxima release' de várias releases recentes da mesma linha, de modo que o CFR (b) pode
contar mais falhas do que o rework rate conta correções. Nesta amostra o CFR (b) tem
mediana 0,269 (IQR 0,395; n = 300), com 10974 falhas em 18143 releases avaliadas (0,605),
contra 12020 corretivas no rework rate. Os repositórios em que as duas métricas mais se
afastam estão em `resultados/tabelas/rq08_divergencias.csv`.

Entre os 300 repositórios com as duas métricas, o Spearman entre rework rate e CFR (b) é ρ
= 0,359 (p = 1,45e-10). A associação é positiva e fraca (ρ = 0,359; distinguível de zero
ao nível de 5%, sem ajuste por multiplicidade). Como as duas métricas saem da mesma
heurística aplicada às mesmas releases, parte dessa associação é construção, e não
evidência independente sobre a qualidade das entregas.

## Confiança no valor

O rework rate herda os erros da heurística. Na amostra-ouro de 300 releases, a versão v1
tem precisão 0,696, recall 0,824 e F1 0,754: ela marca como corretivas mais releases do
que o consenso humano (precisão menor que o recall), então a taxa observada tende a
superestimar o retrabalho. Corrigindo a taxa agregada por P/R, ela cairia de 0,654 para
cerca de 0,553. É uma ordem de grandeza, e não uma correção exata, porque supõe que
precisão e recall da amostra-ouro valem para todas as releases; o refinamento da
heurística olhou para a mesma amostra em que ela foi avaliada, o que também infla o F1.
