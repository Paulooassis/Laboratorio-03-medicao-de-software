# RQ 06 — Fatores associados ao desempenho DORA

A entrada contém 100 repositórios, não uma amostra presumida de 300. Cada repositório tem o mesmo peso. A análise é univariada, bilateral, com α = 0,05. As métricas principais são DF, LT (a), CFR (a) e recuperação da C1 estrita; não há fallback de LT (a) para (b), nem imputação de episódios censurados. O CFR (b) suplementar usa releases.csv e a mesma agregação/censura da RQ 05.

Durações negativas encontradas: LT (b): 1. Os Lead Times negativos são preservados, conforme a política do pipeline documentada no README (rebase ou cherry-pick podem gerar essas diferenças de datas). Não se toma módulo nem se troca por zero. São uma limitação temporal da proxy; não representam tempo de entrega fisicamente negativo nem justificam alegar desempenho superior.

## Grupos e cortes

Os grupos são fixados com os metadados antes de excluir a métrica ausente em cada teste. Idade é (window_end − created_at) em dias de 24 horas; datas ausentes não são estimadas. Estrelas, contribuidores e idade usam [pandas.qcut][qcut], com quatro quantis e duplicates='drop': cortes coincidentes são removidos; empates não são separados por posição arbitrária. Os grupos restantes são Q1…Qk, em ordem crescente, e podem ter tamanhos diferentes ou intervalos vazios. Um fator constante não permite teste. Os intervalos são abertos à esquerda e fechados à direita, exceto o primeiro, que inclui o mínimo. Todos os limites exatos e n estão em rq06_grupos.csv.

- Linguagem: TypeScript: n=31; Python: n=19; Outras: n=49.

- Estrelas: Q1 [65165; 76791.5] estrelas: n=25; Q2 (76791.5; 93780] estrelas: n=25; Q3 (93780; 120355.25] estrelas: n=25; Q4 (120355.25; 391686] estrelas: n=25.

- Contribuidores: Q1 [37; 386.25] pessoas: n=25; Q2 (386.25; 897] pessoas: n=25; Q3 (897; 1848.25] pessoas: n=25; Q4 (1848.25; 8872] pessoas: n=25.

- Idade: Q1 [28.930486; 1025.8099] dias: n=25; Q2 (1025.8099; 2785.9488] dias: n=25; Q3 (2785.9488; 4160.249] dias: n=25; Q4 (4160.249; 6129.0608] dias: n=25.

Entre as seis linguagens mais frequentes, mantêm-se separadas apenas as que têm pelo menos 15 repositórios. As demais conhecidas formam Outras; se Outras tiver menos de 15, absorve a menor linguagem mantida até atingir esse mínimo. Linguagem ausente fica fora desse fator. A quantidade de linguagens separadas depende dos dados: não se fabricam grupos de 15 para alcançar cinco ou seis linguagens.

## Testes e tamanhos de efeito

A família principal contém os 16 testes planejados (4 fatores × 4 métricas). A suplementar contém 8 (os mesmos fatores × LT (b) e CFR (b)). Tipo do projeto tem 4 testes exploratórios separados. Holm é aplicado a todos os p válidos de cada família, inclusive os não significativos; testes indefinidos permanecem ausentes. São usados Kruskal–Wallis com correção de empates para três ou mais grupos, e Mann–Whitney para dois. KW não é estimado se algum grupo efetivo tem menos de 5 observações ([recomendação do SciPy][kw]). As tabelas CSV registram n, tamanhos dos grupos efetivos, restrições e motivo de teste indefinido.

Para KW, ε² = H/(n−1); a convenção descritiva de [Mangiafico][efeitos] é: desprezível <0,01; pequeno [0,01;0,08); médio [0,08;0,26); grande ≥0,26. Esses limites não são universais nem provam importância prática. Para MW, usa-se δ = 2U/(n₁n₂)−1 e a convenção da base comum (Romano et al., 2006): |δ| <0,147 desprezível; <0,33 pequeno; <0,474 médio; demais grande. As tabelas LaTeX mostram H/ε² nas linhas KW e U/δ nas linhas MW; CSV preserva colunas distintas. O sinal de δ compara o primeiro grupo listado com o segundo.

### Família principal

16 testes planejados; 16 estimáveis; 3 significativo(s) após Holm; 3 com efeito ao menos médio na convenção adotada.

- Linguagem × LT (a): n=99, p Holm=0,00137956, ε²=0,1897 (médio).

- Contribuidores × LT (a): n=100, p Holm=0,00807179, ε²=0,1761 (médio).

- Idade × LT (a): n=100, p Holm=1,05808e-07, ε²=0,4139 (grande).

Nenhum fator teve associação significativa após Holm com DF, CFR (a), Recuperação nesta família.

Efeitos ao menos médios sem significância após Holm: Linguagem × DF (p Holm=0,0778555); Contribuidores × Recuperação (p Holm=0,283173); Idade × DF (p Holm=0,0654068); Idade × CFR (a) (p Holm=0,350186). Permanecem inconclusivos apesar da magnitude estimada.

### Família suplementar

8 testes planejados; 8 estimáveis; 5 significativo(s) após Holm; 5 com efeito ao menos médio na convenção adotada.

- Linguagem × LT (b): n=99, p Holm=0,00164919, ε²=0,1673 (médio).

- Linguagem × CFR (b): n=99, p Holm=0,0108861, ε²=0,1251 (médio).

- Contribuidores × LT (b): n=100, p Holm=0,000272124, ε²=0,2331 (médio).

- Idade × LT (b): n=100, p Holm=7,77588e-10, ε²=0,5010 (grande).

- Idade × CFR (b): n=100, p Holm=0,0108861, ε²=0,1462 (médio).

### Família exploratória

4 testes planejados; 4 estimáveis; 1 significativo(s) após Holm; 1 com efeito ao menos médio na convenção adotada.

- Tipo do projeto × LT (a): n=60, p Holm=0,0204701, ε²=0,1788 (médio).

Nenhum fator teve associação significativa após Holm com DF, CFR (a), Recuperação nesta família.

## Post-hoc e direção

Somente KW significativo após Holm abre comparações MW bilaterais par a par. Holm reúne todos os pares das métricas selecionadas dentro de cada fator e família (não só por métrica). A tabela rq06_posthoc registra todos esses pares, Cliff's delta e direção; MW global com dois grupos já é a comparação direta. DF maior indica sentido favorável; LT, CFR e recuperação menores indicam sentido favorável. Dominância de postos não exige diferença entre medianas.

- principal, Linguagem × LT (a): A=Outras, B=Python; p Holm=0,00504661; δ=0,4758 (grande); A tende a ter valores maiores; sentido favorável a B.

- principal, Linguagem × LT (a): A=Outras, B=TypeScript; p Holm=0,000311876; δ=0,5181 (grande); A tende a ter valores maiores; sentido favorável a B.

- principal, Contribuidores × LT (a): A=Q1, B=Q2; p Holm=0,0105383; δ=-0,4976 (grande); A tende a ter valores menores; sentido favorável a A.

- principal, Contribuidores × LT (a): A=Q1, B=Q3; p Holm=0,00473284; δ=-0,5552 (grande); A tende a ter valores menores; sentido favorável a A.

- principal, Contribuidores × LT (a): A=Q1, B=Q4; p Holm=0,00473284; δ=-0,5520 (grande); A tende a ter valores menores; sentido favorável a A.

- principal, Idade × LT (a): A=Q1, B=Q2; p Holm=0,0478058; δ=-0,3280 (pequeno); A tende a ter valores menores; sentido favorável a A.

- principal, Idade × LT (a): A=Q1, B=Q3; p Holm=0,000256615; δ=-0,6608 (grande); A tende a ter valores menores; sentido favorável a A.

- principal, Idade × LT (a): A=Q1, B=Q4; p Holm=2,0064e-06; δ=-0,8432 (grande); A tende a ter valores menores; sentido favorável a A.

- principal, Idade × LT (a): A=Q2, B=Q3; p Holm=0,0156176; δ=-0,4624 (médio); A tende a ter valores menores; sentido favorável a A.

- principal, Idade × LT (a): A=Q2, B=Q4; p Holm=9,98645e-06; δ=-0,7856 (grande); A tende a ter valores menores; sentido favorável a A.

- principal, Idade × LT (a): A=Q3, B=Q4; p Holm=0,0340145; δ=-0,3952 (médio); A tende a ter valores menores; sentido favorável a A.

- suplementar, Linguagem × LT (b): A=Outras, B=Python; p Holm=0,00141831; δ=0,5789 (grande); A tende a ter valores maiores; sentido favorável a B.

- suplementar, Linguagem × LT (b): A=Outras, B=TypeScript; p Holm=0,0227548; δ=0,3693 (médio); A tende a ter valores maiores; sentido favorável a B.

- suplementar, Linguagem × CFR (b): A=Outras, B=TypeScript; p Holm=0,00153438; δ=-0,4806 (grande); A tende a ter valores menores; sentido favorável a A.

- suplementar, Contribuidores × LT (b): A=Q1, B=Q2; p Holm=0,00988484; δ=-0,5008 (grande); A tende a ter valores menores; sentido favorável a A.

- suplementar, Contribuidores × LT (b): A=Q1, B=Q3; p Holm=0,000714891; δ=-0,6288 (grande); A tende a ter valores menores; sentido favorável a A.

- suplementar, Contribuidores × LT (b): A=Q1, B=Q4; p Holm=0,000300554; δ=-0,6704 (grande); A tende a ter valores menores; sentido favorável a A.

- suplementar, Idade × LT (b): A=Q1, B=Q2; p Holm=0,0138812; δ=-0,5136 (grande); A tende a ter valores menores; sentido favorável a A.

- suplementar, Idade × LT (b): A=Q1, B=Q3; p Holm=1,77816e-06; δ=-0,8656 (grande); A tende a ter valores menores; sentido favorável a A.

- suplementar, Idade × LT (b): A=Q1, B=Q4; p Holm=1,02562e-06; δ=-0,8848 (grande); A tende a ter valores menores; sentido favorável a A.

- suplementar, Idade × LT (b): A=Q2, B=Q3; p Holm=0,000277709; δ=-0,6928 (grande); A tende a ter valores menores; sentido favorável a A.

- suplementar, Idade × LT (b): A=Q2, B=Q4; p Holm=0,000489764; δ=-0,6672 (grande); A tende a ter valores menores; sentido favorável a A.

- suplementar, Idade × CFR (b): A=Q1, B=Q4; p Holm=0,0138812; δ=0,5120 (grande); A tende a ter valores maiores; sentido favorável a B.

- suplementar, Idade × CFR (b): A=Q2, B=Q4; p Holm=0,0138812; δ=0,5136 (grande); A tende a ter valores maiores; sentido favorável a B.

- exploratoria, Tipo do projeto × LT (a): A=application/service, B=cli; p Holm=0,0102348; δ=0,5661 (grande); A tende a ter valores maiores; sentido favorável a B.

- exploratoria, Tipo do projeto × LT (a): A=cli, B=library/framework; p Holm=0,0133061; δ=-0,5639 (grande); A tende a ter valores menores; sentido favorável a A.

## Tipo de projeto e limites da interpretação

Rótulos coletivos, provisórios (não são consenso independente): validacao/rotulos/rotulos_grupo.csv; 60 repositórios com métricas e tipo elegível; 0 do tipo other excluídos.

Os tipos elegíveis são biblioteca/framework, aplicação/serviço e CLI. Não se estendem rótulos aos projetos não rotulados. Se algum tipo efetivo tiver n<5, comparam-se apenas os dois maiores por MW; a restrição e os grupos ficam na tabela. Não se mistura esta amostra com a família principal.

Significância após Holm indica evidência de distribuições diferentes, não que uma característica cause desempenho melhor. Efeito pequeno pode ser significativo; efeito médio/grande sem significância continua inconclusivo. As associações são univariadas e podem refletir confundimento entre popularidade, idade, linguagem e contribuidores. Cobertura e ausências podem selecionar os projetos observados. O CFR (a) mede falha de pipeline, não incidente de produção; métricas baseadas em releases e recuperação de CI são proxies do DORA. No suplemento, CFR (b) também carrega o artefato da janela de sete dias discutido na RQ 05.

Somente combinações significativas após Holm geram boxplots. Durações usam symlog base 10 com trecho linear até 1 hora; DF até 0,1 release/semana. Zeros permanecem sem pseudocontagem. CFR tem eixo linear de 0 a 1. As figuras mostram mediana, quartis, bigodes de 1,5 IQR e observações além dos bigodes.

[qcut]: https://pandas.pydata.org/pandas-docs/version/2.2/reference/api/pandas.qcut.html
[kw]: https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.stats.kruskal.html
[efeitos]: https://rcompanion.org/handbook/F_08.html
