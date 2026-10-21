# Avaliação e versões da heurística — S2-08

| Versão | Regra | P | R | F1 | Motivo |
| --- | --- | --- | --- | --- | --- |
| v1 | SemVer: somente patch; sem anterior menor, patch próprio > 0. Fora de SemVer: ao menos metade dos títulos de commits com fix, hotfix ou revert. | 0,6961 | 0,8235 | 0,7545 | Regra existente em S2-07 aprovada sem refinamento. |

A regra fica em `dora_selection/cfr.py`. Avaliação e CFR (b) usam a mesma função e
o mesmo predecessor, incluindo linhas paralelas de versões. A classificação usa
o histórico coletado completo, não apenas as cinco releases sorteadas. A regex
compara palavras inteiras e ignora maiúsculas; `fixes` e `bugfix` não são sinais
da v1. Essa regra não usa release notes.

## Execução

Na raiz do projeto:

```powershell
py -3.13 -m pip install -r requirements-dev.txt
py -3.13 -m validacao.consenso
py -3.13 validacao/avaliar_heuristica.py
```

Neste projeto, o consenso é consolidado diretamente de `rotulos_grupo.csv`, conforme
a decisão de manter um único arquivo do grupo. O formato de `validacao.consenso` tem 420 itens; a avaliação usa apenas
as 300 linhas `dimension=is_corrective`, `level=release`, com `label=yes/no`.
Também é aceito um CSV com `repository`, `release_id`, `is_corrective`.
Releases faltantes, duplicadas, rótulos vazios e `uncertain` interrompem a avaliação.
A estrutura é verificada pelo script; a independência humana cabe ao grupo.

Entradas: `outputs/pipeline/deployments.json` e
`outputs/gold_sample/sample_releases.csv`. A coleta é lida por repositório com
ijson, sem nova mineração. Históricos incompletos de tags não SemVer não viram `no`.

Cada execução completa cria uma pasta em `validacao/resultados/heuristica/` com
`resultado.json`, `predicoes.csv`, `matriz_confusao.csv`, `falsos_positivos.csv` e
`falsos_negativos.csv`. A matriz tem consenso nas linhas e previsão nas colunas,
na ordem `no`, `yes`. P/R/F1 usam a classe positiva `yes` e `zero_division=0`.
Regra, resultados, motivo e hashes dos dados são acrescentados a este histórico.

Sem consenso, para aplicar somente a regra:

```powershell
py -3.13 validacao/avaliar_heuristica.py --predict-only
```

Esse modo gera previsões, sem calcular métricas ou definir versão oficial.
Para oficializar uma versão avaliada com F1 >= 0,70:

```powershell
py -3.13 validacao/avaliar_heuristica.py --approve
```

F1 abaixo de 0,70 bloqueia a aprovação, salvo exceção explicitamente documentada
com `--approve --justification "Motivo real da limitação"`. A exceção não altera
o F1. Caso contrário, examine os erros, implemente uma versão nova no módulo CFR,
atualize `HEURISTIC_VERSION` e a descrição `RULE`, e reavalie com
`--reason "Motivo do refinamento"`. Guarde o histórico das versões anteriores.

`config.yaml` mantém `versao_oficial: null` até a avaliação. Após aprovação, o
pipeline usa a versão registrada no CFR (b). Alterar a implementação invalida
seu hash de aprovação e exige reavaliação. O CFR (b) mantém sua definição:
releases seguidas por corretiva da mesma linha em até sete dias / releases
avaliáveis; os últimos sete dias ficam censurados. O CFR por workflow runs é
separado. `metrics.json` recebe o resultado completo e `dora.csv` inclui
`cfr_b`, `cfr_b_version` e `cfr_b_censored`.

## Ameaça à validade

Refinar a regra com os erros da mesma amostra em que ela é reavaliada infla o F1.
O artigo deve apresentar essas reavaliações como exploratórias, sem afirmar
generalização. Uma avaliação final independente exige reservar previamente outros
repositórios sem consultar seus rótulos durante o refinamento.

## Situação da execução

Aplicação final da v1 executada em 13/10/2026 sobre as **300 releases**. Os
identificadores, links e ordem da amostra foram preservados. A avaliação obteve
P=0,6961, R=0,8235 e F1=0,7545, com 55 falsos positivos e 27 falsos negativos.
A matriz de confusão foi `[[92, 55], [27, 126]]`, com consenso nas linhas e
previsão nas colunas. Os arquivos finais estão em
`resultados/heuristica/v1-20261013T230913657067Z/`.

Verificação: os testes desta etapa passaram. A suíte completa teve 385 testes
aprovados, cobertura de 95,83% e quatro falhas preexistentes dos testes de CLI
dos Cards 1–3: `collection.log` permanece aberto e o Windows impede a limpeza
do diretório temporário. Essas falhas não foram alteradas nesta issue.

O consenso contém 420 itens, incluindo as 300 classificações de releases. Como
F1 >= 0,70, a v1 foi definida como oficial em `config.yaml`, sem necessidade de
criar v2. Nenhum commit foi realizado.

## v1 — 2026-10-13T23:09:12.780912+00:00

Regra: SemVer: mudança apenas de patch em relação à anterior da mesma linha; sem anterior menor, patch próprio > 0. Tags não SemVer: ao menos 50% dos títulos de commits contêm fix, hotfix ou revert como palavra inteira.

P=0.696133; R=0.823529; F1=0.754491. FP=55; FN=27; n=300.

Motivo: Avaliação inicial da heurística existente.

Justificativa de exceção: Não informada.

Regra SHA-256: `c8321a39d6de4c655ce698b9e0b1abaea92420ae82aa6a2502289d5bd66fa459`. Consenso SHA-256: `476627a6ef111172467e482454a3db4431d11b461048a091ea701654a0124485`. Coleta SHA-256: `3926ec151206719f4ddeb47da646e36ade7e720c45de7e2f9023455d4cb24248`.

Reavaliação após refinamento nesta mesma amostra pode inflar o F1; registrar como ameaça à validade.
