# RQ 05 — Frequência de deploy e estabilidade

A unidade de análise é o repositório. Cada variante exclui ausentes par a par; o CFR (b) foi obtido de releases.csv, segundo a agregação da RQ 03. Os p-valores são bilaterais, sem ajuste por multiplicidade, e exploratórios.

Na variante (a) proxy de CI, ρ = 0,2318, p = 0,020337 e n = 100; a força da associação é
fraca. A associação positiva apresenta uma tensão aparente com a afirmação do DORA: maior
frequência acompanha maior CFR nesta amostra. As proxies e o mecanismo de medição impedem
tratar isso como uma refutação direta do DORA.

Na variante (b) proxy de entrega, ρ = 0,6832, p = 4,85952e-15 e n = 100; a força da
associação é moderada. A associação positiva apresenta uma tensão aparente com a afirmação
do DORA: maior frequência acompanha maior CFR nesta amostra. As proxies e o mecanismo de
medição impedem tratar isso como uma refutação direta do DORA.

A força usa |ρ|, sem arredondamento prévio: desprezível [0; 0,10), fraca [0,10; 0,40),
moderada [0,40; 0,70), forte [0,70; 0,90) e muito forte [0,90; 1]. São as faixas
convencionais apresentadas por [Schober, Boer e Schwarte
(2018)](https://doi.org/10.1213/ANE.0000000000002864), usadas como descrição, não como
limites universais ou como teste de significância.

## Diagnóstico do artefato do CFR (b)

Na amostra válida de DF × CFR (b), o grupo de baixa frequência inclui DF ≤ 0,2445
releases/semana (Q1), e o de alta frequência DF ≥ 1,2705 (Q3). Ordenamos as datas de
publicação dentro de cada repositório e calculamos os intervalos consecutivos, incluindo
intervalos nulos de releases simultâneas. Primeiro resumimos cada repositório; depois
comparamos as medianas desses resumos, sem ponderar pelo número de releases.

O intervalo mediano por repositório tem mediana 28,55 dias (IQR 29,00; n = 25) na baixa DF
e 0,95 dias (IQR 1,94; n = 25) na alta DF. A mediana da fração de intervalos de até sete
dias é 0,20 e 0,92, respectivamente.

O grupo de alta DF apresenta intervalos menores e maior fração dentro de sete dias, padrão
compatível com mais oportunidades de a heurística marcar falha. O CFR (b) procura uma
corretiva em até sete dias; mais publicações podem aumentar a chance de encontrar uma,
mesmo sem piora de qualidade. DF e intervalos também derivam das mesmas datas, portanto
este contraste é um diagnóstico descritivo e não estima qual parcela da correlação decorre
da construção da métrica. Os intervalos consideram todas as releases do repositório, sem
controlar linhas de versão.

## Limites e relação com o DORA

O [DORA](https://dora.dev/guides/dora-metrics/) sustenta que velocidade e estabilidade
podem melhorar juntas. Correlação não implica causalidade: composição dos projetos,
tamanho e práticas de entrega podem explicar associações. O CFR (a) mede falha de
pipeline, não falha em produção; o CFR (b) é uma proxy baseada em releases e corretivas. A
comparação com o DORA é, portanto, limitada por essas diferenças de medição.

Os p-valores são os retornados por [scipy.stats.spearmanr][scipy-spearman]. A documentação
ressalta a aproximação em amostras pequenas (até 500 observações); a inferência nesta
amostra deve ser tratada como exploratória. Nos gráficos, DF usa symlog de base 10, com
trecho linear entre 0 e 0,1 releases/semana e log acima desse limiar; zeros permanecem no
cálculo e na figura, sem somar constantes. CFR usa eixo de 0 a 1.

[scipy-spearman]: https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.stats.spearmanr.html
