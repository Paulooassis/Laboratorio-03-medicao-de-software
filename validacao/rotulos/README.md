# Rótulos da amostra-ouro

A planilha `rotulos_grupo.csv` contém os 60 repositórios e as 300 releases sorteadas,
com links e identificadores originais preservados. As observações registram
justificativas e limitações das evidências.

Critério: uma release é corretiva quando seu objetivo principal é corrigir falhas.

Estado atual: 60 tipos de projeto e 300 releases rotulados. Supabase permanece
com representatividade `uncertain`. Os casos ambíguos estão justificados em
`observacao` conforme o critério do objetivo principal da entrega.

Valores permitidos: tipo `library/framework`, `application/service`, `cli` ou
`other`; representatividade `yes`, `no` ou `uncertain`; corretiva `yes` ou `no`.

A issue só estará concluída com todos os rótulos preenchidos e revisados.
O grupo adotou esta planilha coletiva como fonte única para gerar o consenso.
Não foram usados resultados da heurística no preenchimento dos rótulos.
