# RQ 07 — Sensibilidade da classificação DORA à definição operacional

Os 300 repositórios foram classificados sob quatro combinações de definições: C1: release,
LT (a), CFR (a); C2: release + pré-release, LT (b), CFR (b); C3: tag, LT (b), CFR (a); C4:
release, LT (b), CFR (b). A C4 não vem do enunciado: ela muda só as variantes das métricas
e mantém a unidade, o que permite separar os dois efeitos que C1 × C2 mistura. Um
repositório só entra numa comparação quando está classificado nas duas combinações; o n de
cada par está na tabela.

## Quanto a classificação muda

- C1 × C2: 94 de 300 repositórios mudaram de categoria (31,3%); κ ponderado = 0,506 (moderada).
- C1 × C3: 73 de 300 repositórios mudaram de categoria (24,3%); κ ponderado = 0,651 (substancial).
- C1 × C4: 85 de 300 repositórios mudaram de categoria (28,3%); κ ponderado = 0,546 (moderada).
- C2 × C3: 100 de 300 repositórios mudaram de categoria (33,3%); κ ponderado = 0,507 (moderada).
- C2 × C4: 22 de 300 repositórios mudaram de categoria (7,3%); κ ponderado = 0,878 (quase perfeita).
- C3 × C4: 103 de 300 repositórios mudaram de categoria (34,3%); κ ponderado = 0,492 (moderada).

Isolando os efeitos: trocar só as variantes das métricas (C1 × C4) muda 28,3% dos
repositórios, e trocar só a unidade de deploy (C2 × C4, de release para release + pré-
release) muda 7,3%.

Em C1 × C2, a métrica que mais muda de nível é Change Failure Rate (72,3% dos 300
repositórios comparáveis).

## As conclusões das RQ 01 a 06 resistem?

**RQ 05 (DF × CFR).** O Spearman entre frequência e CFR, recalculado sob cada combinação,
mantém o sinal e a significância da C1 (ρ = 0,071; p = 0,222) em 1 de 4 combinações,
contando a própria C1.

**RQ 06 (fatores).** Na família principal (4 fatores × 4 métricas, Holm), 4 testes
rejeitam H0 na C1. Nas demais combinações, C2 6 (4 em comum com a C1, 2 novos e 0
perdidos), C3 3 (3 em comum com a C1, 0 novos e 1 perdidos), C4 7 (4 em comum com a C1, 3
novos e 0 perdidos).

**RQ 01 a 03.** As medianas e IQR de DF, Lead Time e CFR sob cada combinação, com a
variação da mediana frente à C1, estão em
`resultados/tabelas/rq07_robustez_descritiva.csv`.

## Conferência

A unidade `release` de `variantes.csv` foi comparada com `repositorios.csv`: df 0
divergência(s), lt_a 0 divergência(s), lt_b 0 divergência(s), cfr_b 0 divergência(s). A C1
deste módulo diverge da `classificacao_c1` em 0 de 300 repositórios.

## Limites

O kappa ponderado fica indefinido quando uma combinação classifica todos os repositórios
na mesma categoria. Os p-valores são exploratórios e a comparação de conjuntos da RQ 06
depende de cada família de Holm ser avaliada isoladamente. Todas as combinações usam a
mesma heurística corretiva (F1 ≈ 0,75) e a mesma janela; a sensibilidade a elas não foi
medida aqui. Na unidade `tag`, a data do deploy é a do commit, e não a de uma publicação,
o que encurta o Lead Time por construção.
