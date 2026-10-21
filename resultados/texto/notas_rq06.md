# RQ 06 — Fatores associados ao desempenho DORA

A entrada contém 300 repositórios, não uma amostra presumida de 300. Cada repositório tem o mesmo peso. A análise é univariada, bilateral, com α = 0,05. As métricas principais são DF, LT (a), CFR (a) e recuperação da C1 estrita; não há fallback de LT (a) para (b), nem imputação de episódios censurados. O CFR (b) suplementar usa releases.csv e a mesma agregação/censura da RQ 05.

Durações negativas encontradas: LT (b): 1. Os Lead Times negativos são preservados, conforme a política do pipeline documentada no README (rebase ou cherry-pick podem gerar essas diferenças de datas). Não se toma módulo nem se troca por zero. São uma limitação temporal da proxy; não representam tempo de entrega fisicamente negativo nem justificam alegar desempenho superior.

## Grupos e cortes

Os grupos são fixados com os metadados antes de excluir a métrica ausente em cada teste. Idade é (window_end − created_at) em dias de 24 horas; datas ausentes não são estimadas. Estrelas, contribuidores e idade usam [pandas.qcut][qcut], com quatro quantis e duplicates='drop': cortes coincidentes são removidos; empates não são separados por posição arbitrária. Os grupos restantes são Q1…Qk, em ordem crescente, e podem ter tamanhos diferentes ou intervalos vazios. Um fator constante não permite teste. Os intervalos são abertos à esquerda e fechados à direita, exceto o primeiro, que inclui o mínimo. Todos os limites exatos e n estão em rq06_grupos.csv.

- Linguagem: TypeScript: n=88; Python: n=60; Go: n=38; Rust: n=30; C++: n=19; JavaScript: n=18; Outras: n=46.

- Estrelas: Q1 [33630; 40120.75] estrelas: n=75; Q2 (40120.75; 51148.5] estrelas: n=75; Q3 (51148.5; 76686] estrelas: n=75; Q4 (76686; 391637] estrelas: n=75.

- Contribuidores: Q1 [11; 269.75] pessoas: n=75; Q2 (269.75; 536.5] pessoas: n=75; Q3 (536.5; 1140] pessoas: n=75; Q4 (1140; 9905] pessoas: n=75.

- Idade: sem metadados válidos.

Entre as seis linguagens mais frequentes, mantêm-se separadas apenas as que têm pelo menos 15 repositórios. As demais conhecidas formam Outras; se Outras tiver menos de 15, absorve a menor linguagem mantida até atingir esse mínimo. Linguagem ausente fica fora desse fator. A quantidade de linguagens separadas depende dos dados: não se fabricam grupos de 15 para alcançar cinco ou seis linguagens.

## Testes e tamanhos de efeito

A família principal contém os 16 testes planejados (4 fatores × 4 métricas). A suplementar contém 8 (os mesmos fatores × LT (b) e CFR (b)). Tipo do projeto tem 4 testes exploratórios separados. Holm é aplicado a todos os p válidos de cada família, inclusive os não significativos; testes indefinidos permanecem ausentes. São usados Kruskal–Wallis com correção de empates para três ou mais grupos, e Mann–Whitney para dois. KW não é estimado se algum grupo efetivo tem menos de 5 observações ([recomendação do SciPy][kw]). As tabelas CSV registram n, tamanhos dos grupos efetivos, restrições e motivo de teste indefinido.

Para KW, ε² = H/(n−1); a convenção descritiva de [Mangiafico][efeitos] é: desprezível <0,01; pequeno [0,01;0,08); médio [0,08;0,26); grande ≥0,26. Esses limites não são universais nem provam importância prática. Para MW, usa-se δ = 2U/(n₁n₂)−1 e a convenção da base comum (Romano et al., 2006): |δ| <0,147 desprezível; <0,33 pequeno; <0,474 médio; demais grande. As tabelas LaTeX mostram H/ε² nas linhas KW e U/δ nas linhas MW; CSV preserva colunas distintas. O sinal de δ compara o primeiro grupo listado com o segundo.

### Família principal

16 testes planejados; 12 estimáveis; 4 significativo(s) após Holm; 3 com efeito ao menos médio na convenção adotada.

- Linguagem × DF: n=299, p Holm=7,69074e-05, ε²=0,1131 (médio).

- Linguagem × LT (a): n=299, p Holm=9,36108e-08, ε²=0,1641 (médio).

- Contribuidores × DF: n=300, p Holm=0,0295575, ε²=0,0459 (pequeno).

- Contribuidores × LT (a): n=300, p Holm=1,5438e-05, ε²=0,1002 (médio).

Nenhum fator teve associação significativa após Holm com CFR (a), Recuperação nesta família.

### Família suplementar

8 testes planejados; 6 estimáveis; 4 significativo(s) após Holm; 3 com efeito ao menos médio na convenção adotada.

- Linguagem × LT (b): n=299, p Holm=3,41586e-05, ε²=0,1140 (médio).

- Linguagem × CFR (b): n=299, p Holm=3,41586e-05, ε²=0,1127 (médio).

- Contribuidores × LT (b): n=300, p Holm=2,14666e-10, ε²=0,1727 (médio).

- Contribuidores × CFR (b): n=300, p Holm=0,0246437, ε²=0,0394 (pequeno).

### Família exploratória

4 testes planejados; 4 estimáveis; 1 significativo(s) após Holm; 1 com efeito ao menos médio na convenção adotada.

- Tipo do projeto × LT (a): n=60, p Holm=0,0204701, ε²=0,1788 (médio).

Nenhum fator teve associação significativa após Holm com DF, CFR (a), Recuperação nesta família.

Efeitos ao menos médios sem significância após Holm: Tipo do projeto × Recuperação (p Holm=0,306442). Permanecem inconclusivos apesar da magnitude estimada.

## Post-hoc e direção

Somente KW significativo após Holm abre comparações MW bilaterais par a par. Holm reúne todos os pares das métricas selecionadas dentro de cada fator e família (não só por métrica). A tabela rq06_posthoc registra todos esses pares, Cliff's delta e direção; MW global com dois grupos já é a comparação direta. DF maior indica sentido favorável; LT, CFR e recuperação menores indicam sentido favorável. Dominância de postos não exige diferença entre medianas.

- principal, Linguagem × DF: A=Go, B=TypeScript; p Holm=0,00472351; δ=-0,4312 (médio); A tende a ter valores menores; sentido favorável a B.

- principal, Linguagem × DF: A=Outras, B=TypeScript; p Holm=3,91656e-05; δ=-0,5168 (grande); A tende a ter valores menores; sentido favorável a B.

- principal, Linguagem × LT (a): A=C++, B=Python; p Holm=0,00255241; δ=0,6105 (grande); A tende a ter valores maiores; sentido favorável a B.

- principal, Linguagem × LT (a): A=C++, B=TypeScript; p Holm=0,000323004; δ=0,6555 (grande); A tende a ter valores maiores; sentido favorável a B.

- principal, Linguagem × LT (a): A=Go, B=TypeScript; p Holm=0,00225741; δ=0,4528 (médio); A tende a ter valores maiores; sentido favorável a B.

- principal, Linguagem × LT (a): A=Outras, B=Python; p Holm=0,00835512; δ=0,4188 (médio); A tende a ter valores maiores; sentido favorável a B.

- principal, Linguagem × LT (a): A=Outras, B=TypeScript; p Holm=3,10461e-05; δ=0,5222 (grande); A tende a ter valores maiores; sentido favorável a B.

- principal, Contribuidores × DF: A=Q1, B=Q3; p Holm=0,00273607; δ=-0,3417 (médio); A tende a ter valores menores; sentido favorável a B.

- principal, Contribuidores × LT (a): A=Q1, B=Q4; p Holm=6,02801e-06; δ=-0,4756 (grande); A tende a ter valores menores; sentido favorável a A.

- principal, Contribuidores × LT (a): A=Q2, B=Q4; p Holm=0,000732552; δ=-0,3753 (médio); A tende a ter valores menores; sentido favorável a A.

- principal, Contribuidores × LT (a): A=Q3, B=Q4; p Holm=0,000397581; δ=-0,3909 (médio); A tende a ter valores menores; sentido favorável a A.

- suplementar, Linguagem × LT (b): A=C++, B=Python; p Holm=0,0017737; δ=0,6263 (grande); A tende a ter valores maiores; sentido favorável a B.

- suplementar, Linguagem × LT (b): A=JavaScript, B=Python; p Holm=0,00363406; δ=0,6111 (grande); A tende a ter valores maiores; sentido favorável a B.

- suplementar, Linguagem × LT (b): A=Outras, B=Python; p Holm=0,00339979; δ=0,4471 (médio); A tende a ter valores maiores; sentido favorável a B.

- suplementar, Linguagem × CFR (b): A=C++, B=TypeScript; p Holm=0,0150385; δ=-0,5185 (grande); A tende a ter valores menores; sentido favorável a A.

- suplementar, Linguagem × CFR (b): A=Go, B=TypeScript; p Holm=0,00901061; δ=-0,4136 (médio); A tende a ter valores menores; sentido favorável a A.

- suplementar, Linguagem × CFR (b): A=Outras, B=TypeScript; p Holm=0,000186382; δ=-0,4832 (grande); A tende a ter valores menores; sentido favorável a A.

- suplementar, Contribuidores × LT (b): A=Q1, B=Q4; p Holm=3,53653e-10; δ=-0,6292 (grande); A tende a ter valores menores; sentido favorável a A.

- suplementar, Contribuidores × LT (b): A=Q2, B=Q4; p Holm=5,83573e-08; δ=-0,5524 (grande); A tende a ter valores menores; sentido favorável a A.

- suplementar, Contribuidores × LT (b): A=Q3, B=Q4; p Holm=9,85804e-05; δ=-0,4183 (médio); A tende a ter valores menores; sentido favorável a A.

- suplementar, Contribuidores × CFR (b): A=Q2, B=Q4; p Holm=0,0283729; δ=0,2775 (pequeno); A tende a ter valores maiores; sentido favorável a B.

- exploratoria, Tipo do projeto × LT (a): A=application/service, B=cli; p Holm=0,0102348; δ=0,5661 (grande); A tende a ter valores maiores; sentido favorável a B.

- exploratoria, Tipo do projeto × LT (a): A=cli, B=library/framework; p Holm=0,0133061; δ=-0,5639 (grande); A tende a ter valores menores; sentido favorável a A.

## Tipo de projeto e limites da interpretação

Rótulos consensuais: validacao/resultados/tipo_projeto.csv; 60 repositórios com métricas e tipo elegível; 0 do tipo other excluídos.

Os tipos elegíveis são biblioteca/framework, aplicação/serviço e CLI. Não se estendem rótulos aos projetos não rotulados. Se algum tipo efetivo tiver n<5, comparam-se apenas os dois maiores por MW; a restrição e os grupos ficam na tabela. Não se mistura esta amostra com a família principal.

Significância após Holm indica evidência de distribuições diferentes, não que uma característica cause desempenho melhor. Efeito pequeno pode ser significativo; efeito médio/grande sem significância continua inconclusivo. As associações são univariadas e podem refletir confundimento entre popularidade, idade, linguagem e contribuidores. Cobertura e ausências podem selecionar os projetos observados. O CFR (a) mede falha de pipeline, não incidente de produção; métricas baseadas em releases e recuperação de CI são proxies do DORA. No suplemento, CFR (b) também carrega o artefato da janela de sete dias discutido na RQ 05.

Somente combinações significativas após Holm geram boxplots. Durações usam symlog base 10 com trecho linear até 1 hora; DF até 0,1 release/semana. Zeros permanecem sem pseudocontagem. CFR tem eixo linear de 0 a 1. As figuras mostram mediana, quartis, bigodes de 1,5 IQR e observações além dos bigodes.

[qcut]: https://pandas.pydata.org/pandas-docs/version/2.2/reference/api/pandas.qcut.html
[kw]: https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.stats.kruskal.html
[efeitos]: https://rcompanion.org/handbook/F_08.html
