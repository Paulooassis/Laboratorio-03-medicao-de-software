# Protocolo de consenso e desempate da amostra-ouro

Este protocolo define como os rótulos independentes dos três avaliadores (S2-04) viram
um rótulo único por item, usado como referência na avaliação da heurística (S2-08) e
como fator "tipo do projeto" da RQ 06. A parte mecânica é feita por
`python -m validacao.consenso`; as decisões humanas ficam registradas em
`validacao/decisoes.csv`, versionado junto com este arquivo.

## 1. Itens e rótulos

| Dimensão | Item | Valores |
|---|---|---|
| `project_type` | repositório (60) | `library/framework`, `application/service`, `cli`, `other` |
| `releases_represent_deliveries` | repositório (60) | `yes`, `no`, `uncertain` |
| `is_corrective` | release (300) | `yes`, `no` |

## 2. Ordem dos passos

1. Os três avaliadores rotulam de forma independente (S2-04) e só depois os arquivos
   `validacao/rotulos/rotulos_{X}.csv` são unidos na `main`.
2. A concordância é medida **antes** de qualquer discussão (`python -m validacao.concordancia`,
   S2-05), para que o kappa reflita os julgamentos independentes.
3. `python -m validacao.consenso` aplica a regra automática e gera a pauta em
   `validacao/resultados/pendencias.csv`.
4. Os três se reúnem, discutem só os itens da pauta e registram as decisões em
   `validacao/decisoes.csv`.
5. `python -m validacao.consenso` é executado de novo e gera `validacao/consenso.csv` e
   `validacao/resultados/tipo_projeto.csv`. As planilhas individuais não são editadas.

## 3. Regra automática: maioria simples

- **Unanimidade** (3-0): o rótulo comum é o final (`method = unanimous`).
- **Maioria** (2-1): o rótulo da maioria é o final (`method = majority`).

Em `is_corrective`, com dois valores e três avaliadores, sempre há maioria.

## 4. Casos que vão para a reunião

| Motivo (`reason`) | Quando | Sem decisão registrada |
|---|---|---|
| `tie` | Nenhum rótulo tem maioria (1-1-1), possível em `project_type` e `releases_represent_deliveries` | Item fica sem rótulo; o consenso não é gerado |
| `uncertain_majority` | A maioria escolheu `uncertain` | Item fica sem rótulo; o consenso não é gerado |
| `uncertain_vote` | Um avaliador marcou `uncertain`, mas há maioria definida | Vale a maioria; o item só entra na pauta para revisão |

## 5. Reunião de consenso

- Participam os três avaliadores. Para cada item da pauta, cada um expõe a evidência que
  usou (README, release notes, lista de commits) antes da decisão.
- A decisão é tomada por acordo entre os três; sem acordo, prevalece a leitura mais
  conservadora: `other` em `project_type`, `no` em `releases_represent_deliveries` e
  `no` em `is_corrective`. Isso deve ser registrado na justificativa.
- O resultado pode ser qualquer valor permitido da dimensão, inclusive `uncertain`
  em `releases_represent_deliveries` quando o grupo concluir que a evidência não basta.
- A reunião também pode revisar um item decidido pela maioria (por exemplo, quando
  ninguém havia notado uma evidência); a decisão registrada prevalece sobre a maioria.

## 6. Registro das decisões (`validacao/decisoes.csv`)

Uma linha por item decidido em reunião:

| Coluna | Conteúdo |
|---|---|
| `dimension` | `project_type`, `releases_represent_deliveries` ou `is_corrective` |
| `repository` | `owner/repo` |
| `release_id` | ID da release; vazio para as dimensões do repositório |
| `label` | Rótulo decidido |
| `justification` | Motivo da decisão, obrigatório (evidência usada e, se for o caso, a regra conservadora) |

Exemplo:

```csv
dimension,repository,release_id,label,justification
project_type,owner/repo,,cli,"README descreve uso só pela linha de comando; o pacote Python é interno"
is_corrective,owner/repo,123456,yes,"Release notes listam apenas correções de regressão da 2.3.0"
```

## 7. Saídas

| Arquivo | Conteúdo |
|---|---|
| `validacao/resultados/pendencias.csv` | Pauta: item, votos, motivo, maioria e rótulo decidido (quando houver) |
| `validacao/consenso.csv` | Rótulo final de cada item, método (`unanimous`, `majority`, `meeting`), votos e justificativa |
| `validacao/resultados/tipo_projeto.csv` | Tipo do projeto consensual por repositório, para a RQ 06 |

`consenso.csv` só é gerado quando nenhum item fica sem rótulo.

## 8. Registro da reunião

- Data:
- Participantes:
- Itens na pauta (por motivo):
- Itens decididos pela regra conservadora:
- Observações sobre critérios ambíguos (para a discussão do kappa no artigo):
