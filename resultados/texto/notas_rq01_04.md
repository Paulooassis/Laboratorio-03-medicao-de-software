# RQ 01 a 04 — números e rascunhos para a seção de Resultados

Gerado por `python -m analise`. Todos os valores vêm das tabelas em `resultados/tabelas/`;
nenhum número aqui foi digitado à mão.

## RQ 01 — Deployment Frequency

Mediana de 0,46 releases por semana (IQR 0,77; Q1 0,23, Q3 1,00) em 300 repositórios. 0
repositórios não publicaram nenhuma release na janela e entram na mediana com zero; 0
ficaram sem valor.

## RQ 02 — Lead Time: por que (a) e (b) divergem

A variante (a), por release, mede o intervalo inteiro coberto pela release: do commit mais
antigo do `compare` até a publicação. A variante (b), por commit, mede cada commit até a
publicação da sua release. Como (a) é definida pelo commit mais antigo e (b) pela mediana
de todos eles, basta um commit antigo "esquecido" no intervalo — um branch retomado, um
cherry-pick, um pull request parado — para (a) subir sem que o ritmo de trabalho tenha
mudado. É por isso que as duas não medem a mesma coisa: (a) responde "quanto tempo cabe
dentro de uma entrega" e (b), "quanto tempo um commit típico espera para ser entregue".

Medianas: (a) 324,91 h (13,54 d, IQR 880,17 h, n = 300) contra (b) 411,81 h (17,16 d, IQR
1.716,16 h, n = 300). A razão (a)/(b) por repositório tem mediana 1,29× (IQR 1,42, n =
299).

Os 5 repositórios com maior razão, inspecionados em `releases.csv`:

- `slidevjs/slidev`: razão 37,51× ((a) 45,73 h contra (b) 1,22 h); maior intervalo em
  `v52.2.1`, 1.069,66 h contra 279,32 h da mediana dos seus commits (3,83×), commits
  espalhados por -- dias.
- `evanw/esbuild`: razão 35,38× ((a) 273,40 h contra (b) 7,73 h); maior intervalo em
  `v0.27.0`, 2.129,42 h contra 15,14 h da mediana dos seus commits (140,65×), commits
  espalhados por -- dias.
- `lfnovo/open-notebook`: razão 18,42× ((a) 521,43 h contra (b) 28,31 h); maior
  intervalo em `v0.2.0`, 1.938,49 h contra 893,28 h da mediana dos seus commits (2,17×),
  commits espalhados por -- dias.
- `filebrowser/filebrowser`: razão 15,72× ((a) 19,38 h contra (b) 1,23 h); maior
  intervalo em `v2.32.1`, 3.631,48 h contra 290,15 h da mediana dos seus commits (12,52×),
  commits espalhados por -- dias.
- `rust-lang/rust`: razão 11,55× ((a) 22.191,11 h contra (b) 1.920,56 h); maior
  intervalo em `1.89.0`, 78.877,95 h contra 2.135,93 h da mediana dos seus commits
  (36,93×), commits espalhados por -- dias.

Em 5 deles a release de maior intervalo tem razão de pelo menos 2,0× entre o intervalo da
release e a mediana dos seus próprios commits, o indício de que um commit antigo — e não o
ritmo de trabalho — define o Lead Time da variante (a).

Releases fora do Lead Time: 3052 de 18389 observadas, detalhadas por motivo em
`resultados/tabelas/rq02_releases_ignoradas.csv`. Nenhuma foi estimada nem tratada como
intervalo zero.

## RQ 03 — falha de pipeline não é falha em produção

As duas variantes do Change Failure Rate medem objetos diferentes. A variante (a) é um
proxy de CI: falhas sobre 730432 workflow runs considerados (60959 ignorados, por estarem
cancelados, em andamento ou com conclusão desconhecida), com mediana 0,06 (IQR 0,12, n =
300). A variante (b) é um proxy de entrega: releases seguidas em até 7 dias por uma
release corretiva da mesma linha — 10974 de 18143 releases avaliadas, mediana 0,27 (IQR
0,39, n = 300).

A diferença entre as duas é a própria interpretação da métrica. Um run vermelho é, na
maior parte das vezes, um teste quebrado em um pull request: é barato, é detectado antes
da entrega e muitas vezes é exatamente o CI fazendo o seu trabalho. Uma release seguida de
uma corretiva em até 7 dias é um defeito que passou pelo pipeline e chegou ao usuário. Por
isso a variante (a) tende a ser a mais alta das duas sem que isso signifique produção
instável: ela conta falhas que nunca viraram incidente. Tratar as duas como a mesma
métrica — e comparar qualquer uma delas direto com as faixas do relatório DORA, que falam
de mudanças em produção — superestima a taxa de falha dos repositórios. 246 releases dos
últimos 7 dias da janela não têm 7 dias observados e ficaram fora do denominador de (b),
em vez de entrarem como sucesso.

## RQ 04 — viés da censura no tempo de recuperação

Mediana entre repositórios de 4,94 h (0,21 d, IQR 17,00 h, n = 264), calculada **apenas
sobre episódios recuperados**: dos 20117 episódios de falha, 19921 foram recuperados — 124
deles têm datas contraditórias e também ficam fora da mediana — e 196 ficaram censurados,
sem nenhum sucesso posterior do mesmo workflow dentro da janela. A proporção censurada por
repositório tem mediana 0,00 (IQR 0,03).

Essa mediana subestima o tempo real de recuperação: justamente os episódios mais longos
são os que não terminaram dentro da janela e, por isso, são os excluídos. Para medir o
tamanho do viés, o limite inferior trata cada episódio censurado como recuperado no fim da
observação (`observed_hours`), o maior valor que a janela permite afirmar: a mediana sobe
para 5,22 h (0,22 d), uma diferença de 0,28 h. O valor real está acima da primeira
mediana, e mesmo esse limite ainda é otimista: um episódio censurado pode ter levado muito
mais tempo do que o que sobrou da janela.
