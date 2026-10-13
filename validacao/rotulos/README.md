# Rótulos da amostra-ouro

A planilha `rotulos_grupo.csv` contém os 60 repositórios e as 300 releases sorteadas,
com links e identificadores originais preservados. As observações registram
justificativas e limitações das evidências.

Critério: uma release é corretiva quando seu objetivo principal é corrigir falhas.

Estado atual: 60 tipos de projeto preenchidos e 291 releases rotuladas. Faltam:

- Superset: `superset-helm-chart-0.14.3`.
- llama.cpp: `b7188`.
- Mole: `V1.4.1`, `V1.12.25`, `V1.6.4`, `V1.13.13` e `V1.9.20`.
- ImGui: `v1.92.3` e `v1.91.8`.

As nove células vazias estão justificadas em `observacao`. Supabase permanece
com representatividade `uncertain`. Há históricos parcialmente consultados,
registrados nas respectivas observações; os rótulos precisam de revisão humana.

Valores permitidos: tipo `library/framework`, `application/service`, `cli` ou
`other`; representatividade `yes`, `no` ou `uncertain`; corretiva `yes` ou `no`.

A issue só estará concluída com todos os rótulos preenchidos e revisados.
Ela exige uma avaliação independente por integrante; o arquivo coletivo não
substitui essas avaliações. Não foram usados rótulos de outros avaliadores nem
resultados da heurística. Nenhum commit, push ou merge foi realizado.
