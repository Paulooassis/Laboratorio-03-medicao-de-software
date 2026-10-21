# Replicação cruzada — comparação

Unidade: repositório. Junção pela chave sem distinção de caixa, restrita à subamostra, preservando ausências no denominador. Categorias são as publicadas pelo grupo autor; não são recalculadas com os limites do nosso pipeline.

Diferença = (obtido − original)/original. Original zero (inclusive 0/0) e ausências têm razão indefinida, registrada como célula vazia no CSV. Mediana e IQR usam somente razões finitas e quantis com interpolação linear. Valores seguem a precisão publicada; zero não significa dado ausente.

## Resultados numéricos

- DF (semana): mediana 0.0000%; IQR 0.0000 p.p.; n=30/30; iguais=30; ambos zero=0; original zero=0; ausentes=0.
- LT release (h): mediana 0.0000%; IQR 0.0000 p.p.; n=30/30; iguais=30; ambos zero=0; original zero=0; ausentes=0.
- LT commit (h): mediana 0.0000%; IQR 0.0000 p.p.; n=30/30; iguais=30; ambos zero=0; original zero=0; ausentes=0.
- CFR CI: mediana 0.0000%; IQR 0.0000 p.p.; n=23/30; iguais=21; ambos zero=7; original zero=0; ausentes=0.
- CFR entrega: mediana 0.0000%; IQR 0.0000 p.p.; n=23/30; iguais=30; ambos zero=7; original zero=0; ausentes=0.
- Recuperação (h): mediana 0.0000%; IQR 0.0000 p.p.; n=23/30; iguais=18; ambos zero=0; original zero=0; ausentes=7.
- Retrabalho: mediana 0.0000%; IQR 0.0000 p.p.; n=26/30; iguais=30; ambos zero=4; original zero=0; ausentes=0.

## Concordância DORA

Kappa de Cohen com pesos lineares, Low < Medium < High < Elite. Pares incompletos são excluídos do kappa; duas categorias ausentes não contam como acordo. Kappa fica indefinido com menos de dois pares ou desacordo esperado zero.

- DF: 30/30 (100.00%) da subamostra; 30/30 (100.00%) dos pares; κ linear=1.0000.
- LT C1: 30/30 (100.00%) da subamostra; 30/30 (100.00%) dos pares; κ linear=1.0000.
- CFR C1: 30/30 (100.00%) da subamostra; 30/30 (100.00%) dos pares; κ linear=1.0000.
- Recuperação: 21/30 (70.00%) da subamostra; 21/23 (91.30%) dos pares; κ linear=0.9065.
- Geral: 29/30 (96.67%) da subamostra; 29/30 (96.67%) dos pares; κ linear=0.9599.

## Maiores diferenças

- `falcosecurity/falco`, Recuperação (h): 48.1 → 502.68 (945.0728%).
- `aws-amplify/amplify-js`, Recuperação (h): 193.13 → 94.54 (-51.0485%).
- `blockscout/blockscout`, Recuperação (h): 5.55 → 4.03 (-27.3874%).
- `yosyshq/yosys`, CFR CI: 0.0103 → 0.0087 (-15.5340%).
- `langwatch/langwatch`, Recuperação (h): 16.32 → 18.84 (15.4412%).
- `dkron-io/dkron`, CFR CI: 0.1111 → 0.1183 (6.4806%).
- `aws-amplify/amplify-js`, CFR CI: 0.2283 → 0.2159 (-5.4314%).
- `giscience/openrouteservice`, CFR CI: 0.0129 → 0.0134 (3.8760%).
- `tencent/cherry-markdown`, CFR CI: 0.0571 → 0.0593 (3.8529%).
- `yosyshq/yosys`, Recuperação (h): 10.78 → 10.5 (-2.5974%).

## Proveniência

- original: `replicacao/resultados_originais/dataset.csv`, SHA-256 `03a0e7fa1e95d8da3df2af12fca5f7b2d2055b453f121b44c43a687a88a6a89a`.
  **Manifesto inconsistente:** o SHA-256 declarado não corresponde ao CSV. Data e commit declarados não comprovam a origem desse arquivo.
- obtido: `replicacao/resultados_obtidos/dataset.csv`, SHA-256 `af28947b07365d3bebe3ddcf33ab12ed2367e5fad5de88cecfd9e535c494bc63`.
- amostra: `replicacao/subamostra.csv`, SHA-256 `9b6e4d598053cffea1b421c67675f2db15fb86bfcd1e364affb39418eca8133b`.

## Causas e limitações

No Falco, o pipeline usa updated_at como fim da recuperação. Dois sucessos de setembro/2025 foram atualizados em outubro/2026, embora os jobs tenham terminado em 2025. No snapshot adicional, usar updated_at reproduz 502,68 h; trocar somente esses dois fins pelo maior completed_at dos jobs reproduz 48,10 h. Isso evidencia sensibilidade a metadados mutáveis, sem provar o estado da coleta original ou que houve reexecução.

Amplify, Blockscout, LangWatch e Yosys têm menos runs na replicação. As consultas adicionais também mostram redução no histórico disponível. Exclusão/retenção e data de coleta são hipóteses; faltam os dois snapshots históricos para identificar IDs removidos e descartar cache/paginação. Os intermediários de releases coincidem nos 30 repositórios.

O manifesto original tem hashes incompatíveis com os CSVs publicados; sua data declarada não comprova a origem dos números. Os JSONs das consultas estão em replicacao/evidencias/.

Issues de divergência: publicação pendente. O conector rejeitou a abertura da primeira Issue (user rejected MCP tool call); nenhuma foi criada.

A figura usa symlog (trecho linear entre −1% e +1%); boxplots incluem outliers. Mediana nula não implica identidade em todos os repositórios.
