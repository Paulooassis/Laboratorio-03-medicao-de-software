# Fragilidade da classificação DORA perto dos limites das faixas

Gerado por `python -m analise`. A classificação geral é a mediana das quatro notas
arredondada para baixo, e cada nota vem de uma faixa com limite fixo. Quando uma métrica
cai perto de um limite, uma diferença pequena de coleta — uma janela deslocada em horas,
um episódio de falha a mais — muda a nota e pode mudar a categoria geral. Esta análise
mede essa distância para todos os repositórios.

Em 259 dos 300 repositórios (86,3%), mover **uma única métrica** um degrau já muda a
classificação geral. Em 53 deles a métrica mais próxima está a 5% ou menos do limite, e em
31 as duas coisas valem ao mesmo tempo: estão perto do limite **e** a troca mudaria a
categoria.

## Os cinco mais frágeis

- `ultralytics/ultralytics` (High): Lead Time (a) por release em 23,99 contra o limite
  de 24,00 — margem de 0,0146 (0,06% do valor).
- `react/react` (Medium): Deployment Frequency em 0,23 contra o limite de 0,23 — margem
  de 0,0002 (0,07% do valor); mover essa métrica um degrau muda a classificação geral.
- `rust-lang/rust` (Medium): Deployment Frequency em 0,23 contra o limite de 0,23 —
  margem de 0,0002 (0,07% do valor); mover essa métrica um degrau muda a classificação
  geral.
- `obsproject/obs-studio` (High): Deployment Frequency em 0,23 contra o limite de 0,23 —
  margem de 0,0002 (0,07% do valor); mover essa métrica um degrau muda a classificação
  geral.
- `apache/superset` (High): Deployment Frequency em 0,23 contra o limite de 0,23 —
  margem de 0,0002 (0,07% do valor); mover essa métrica um degrau muda a classificação
  geral.

O mais frágil da amostra é `ultralytics/ultralytics`, a 0,06% de distância do limite de
Lead Time (a) por release.

## O caso relatado na Issue #62

Uma replicação independente do nosso dataset reclassificou `FuelLabs/sway` de Low para a
categoria seguinte (Issue #62). A tabela explica por quê: a métrica Tempo de recuperação
vale 169,87 contra um limite de 168,00 — margem de 1,87, ou 1,10% do valor — e 3 das suas
quatro métricas mudam a classificação geral se andarem um degrau. Não é o repositório mais
frágil da amostra: é o 25º de 300. O cálculo dos dois lados estava correto; o que diverge
é a posição de uma medida contínua em relação a um limite fixo.

## Para a seção de ameaças à validade

A classificação DORA em faixas é uma discretização de medidas contínuas, e nada no método
avisa quando um repositório está à beira de uma faixa. Duas consequências para quem lê os
nossos resultados: (1) uma divergência de categoria entre duas execuções não implica erro
de cálculo em nenhuma delas — pode ser uma métrica a 1% do limite; (2) comparações de
categoria entre grupos ou entre combinações (RQ 07) deveriam reportar, junto, quantos
repositórios estavam perto de um limite, porque é deles que vem a instabilidade. A tabela
`resultados/tabelas/fragilidade_limites.csv` traz a margem de cada repositório para esse
fim.
