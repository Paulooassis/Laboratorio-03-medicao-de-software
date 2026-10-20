# Diário de execução da replicação cruzada

Registro da execução do pipeline do grupo sorteado **usando apenas o README dele**, sobre
uma subamostra de 30 repositórios do dataset original, sem pedir ajuda ao grupo autor.

Travar não é fracasso: é resultado. Todo passo entra aqui, inclusive os que falharam, com
o comando exato, a saída e o contorno — e cada falha de execução ou documentação faltante
vira uma Issue no repositório do grupo autor, listada na seção 5.

As saídas completas dos comandos estão em [`evidencias/`](evidencias/).

## 1. Grupo replicado

| Campo | Valor |
| --- | --- |
| Grupo sorteado | João Gabriel Santos Andrade Almeida, Lucas Ferreira Ribeiro, Vitor Veiga Silva |
| Repositório | <https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software> |
| Commit replicado | `73b739fbd6527b37b7c2508da07beed49f272045` |
| Data do commit | 2026-10-20 15:07:35 -0300 (`Merge pull request #64 from JoaoAlmeida02/Joao`) |
| Tags | nenhuma no repositório |
| Data da execução | 2026-10-20 |
| README seguido | [`LAB03/README.md`](https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software/blob/73b739fbd6527b37b7c2508da07beed49f272045/LAB03/README.md) |

O README da raiz tem só os nomes dos integrantes; as instruções de execução estão em
`LAB03/README.md`, que é o documento efetivamente seguido.

## 2. Ambiente

| Campo | Valor |
| --- | --- |
| Sistema operacional | macOS 27.0.1 (arm64) |
| Versão do Python | 3.14.0 — atende ao "Python 3.10 ou superior" do README |
| Ambiente virtual | venv nova, criada só para esta execução |
| Cache | nenhum: `.cache_http/` e `data/runs/` ausentes no clone |
| Token | `GITHUB_TOKEN` pessoal, sem escopos |

## 3. Subamostra

Sorteada por `python -m replicacao.subamostra`, com semente fixa e publicada.

| Campo | Valor |
| --- | --- |
| CSV de origem | `LAB03/data/dataset.csv` do repositório replicado |
| sha256 do CSV | `03a0e7fa1e95d8da3df2af12fca5f7b2d2055b453f121b44c43a687a88a6a89a` |
| Coluna detectada | `repo` |
| Semente | 42 |
| Repositórios no universo | 300 |
| Tamanho da subamostra | 30 |
| Lista usada | [`subamostra.csv`](subamostra.csv) |

Os 30 sorteados estão todos presentes em `LAB03/data/repos.csv` do grupo replicado, o que
torna possível alimentar as etapas 2 e 3 com exatamente essa subamostra (ver Passo 5).

## 4. Passos executados

### Passo 1 — Clonar o repositório

- **Comando:** `git clone https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software alvo`
- **Tempo:** 27,4 s
- **Saída relevante:** clone completo; `git rev-parse HEAD` = `73b739fbd652…`
- **Erro:** nenhum
- **Contorno aplicado:** nenhum
- **Saiu do README:** não
- **Issue aberta:** nenhuma

### Passo 2 — Instalar as dependências (README §1)

- **Comando:** `cd LAB03 && python -m pip install -r requirements.txt`
- **Tempo:** 57,1 s
- **Saída relevante:** 37 pacotes instalados, todos com wheel para Python 3.14/arm64
  (pandas 3.0.6, scikit-learn 1.9.1, statsmodels 0.15.0, matplotlib 3.11.2). Evidência em
  [`evidencias/passo1_pip_py314.log`](evidencias/passo1_pip_py314.log).
- **Erro:** nenhum
- **Contorno aplicado:** nenhum. O README §1 não menciona criar um ambiente virtual — o
  comando como está escrito instala no Python do sistema. Criei a venv por exigência da
  nossa própria replicação (ambiente limpo), não para contornar um defeito.
- **Saiu do README:** não
- **Issue aberta:** [#67](https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software/issues/67) (e [#66](https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software/issues/66), encontrada ao ler o README)

### Passo 3 — Estimar o consumo da API (README §4)

- **Comando:** `python -m pipeline --dry-run`
- **Tempo:** 1,1 s
- **Saída relevante:** estimativa de **~9.530 chamadas** e **~1,91 h** para a amostra de
  300 repositórios, detalhada por etapa. Funciona **sem token**, o que é um bom sinal de
  projeto: dá para dimensionar o custo antes de configurar credencial. Evidência em
  [`evidencias/passo2_dryrun_sem_token.log`](evidencias/passo2_dryrun_sem_token.log).
- **Erro:** nenhum
- **Contorno aplicado:** nenhum
- **Saiu do README:** não
- **Issue aberta:** nenhuma

### Passo 4 — Primeira execução de coleta, ainda sem `.env` (README §5)

- **Comando:** `python -m pipeline --etapa selecao --limite 30`
- **Tempo:** 0,18 s
- **Saída relevante:**

```
RuntimeError: GITHUB_TOKEN não definido (crie o arquivo .env com GITHUB_TOKEN=seu_token)
```

- **Erro:** falha esperada — o README §2 manda criar o `.env` antes. A mensagem nomeia o
  arquivo e a variável, então é acionável; sai como *traceback* em vez de mensagem limpa
  com código de saída, o que é cosmético. Evidência em
  [`evidencias/passo4_selecao_sem_token.log`](evidencias/passo4_selecao_sem_token.log).
- **Contorno aplicado:** nenhum ainda; o `.env` é criado no Passo 6.
- **Saiu do README:** não
- **Issue aberta:** nenhuma — a mensagem já diz o que fazer.

### Passo 5 — Como rodar sobre a subamostra de 30? (obstáculo central)

- **Comando:** `python -m pipeline --help` e leitura de `config.yaml` e de
  `pipeline/__main__.py`
- **Tempo:** ~2 min de investigação
- **Saída relevante:** o CLI aceita apenas `--config`, `--etapa`, `--limite`, `--refazer`
  e `--dry-run`. O `config.yaml` parametriza janela, `limite_repos`, mínimos de inclusão,
  faixas de estrelas e caminhos — **não existe campo para uma lista de repositórios**.
- **Erro:** nenhum erro de execução; é uma lacuna de capacidade e de documentação. Não há
  caminho, documentado ou não, para rodar o pipeline sobre um conjunto dado de
  repositórios: a Etapa 1 sempre re-seleciona pela busca por faixas de estrelas.
  `--limite 30` entrega 30 repositórios **escolhidos pela busca deles**, que não são os 30
  sorteados do dataset original — e, como a busca depende da contagem de estrelas no
  momento da execução, nem sequer são estáveis entre execuções.
- **Contorno aplicado:** as etapas 2 e 3 leem `data/repos.csv`, cujo caminho vem de
  `caminhos.repos_csv` no `config.yaml`. Dá para escrever um `repos.csv` contendo apenas
  os 30 sorteados — todos já presentes no `repos.csv` do grupo, com as mesmas colunas — e
  rodar `--etapa releases`, `--etapa runs` e `--etapa consolidar`, pulando a seleção.
  Assim o pipeline deles calcula as métricas exatamente sobre a subamostra.
- **Saiu do README:** **sim** — descobrir esse caminho exigiu ler `config.yaml` e
  `pipeline/__main__.py`; o README não documenta o formato de `repos.csv` nem que as
  etapas 2 e 3 o consomem.
- **Issue aberta:** [#65](https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software/issues/65)

### Passo 6 — Coleta sobre a subamostra (etapas 2 a 4)

Contorno do Passo 5 aplicado: `config_replicacao.yaml` com `caminhos.dados` apontando
para `data_replicacao/` — assim os CSVs publicados pelo grupo em `data/` ficam intactos e
os obtidos por nós saem separados — e `data_replicacao/repos.csv` contendo apenas os 30
sorteados, copiados do `data/repos.csv` deles com as mesmas colunas.

#### Passo 6a — Etapa 2: releases e lead time

- **Comando:** `python -m pipeline --config config_replicacao.yaml --etapa releases`
- **Tempo:** **29 min 07 s** (20,5 s de CPU; o resto é espera da API do GitHub)
- **Saída relevante:** `[30/30]` repositórios processados, de 5 a 86 entregas na janela
  por repositório, terminando com "Pipeline executado com sucesso!". Gerou
  `lead_time_release.csv` (30 linhas, 14 colunas) e `releases_ignoradas_release.csv`.
  Evidência em [`evidencias/passo6a_releases.log`](evidencias/passo6a_releases.log).
- **Erro:** nenhum
- **Contorno aplicado:** o do Passo 5
- **Saiu do README:** sim (o contorno do Passo 5)
- **Issue aberta:** nenhuma além da [#65](https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software/issues/65)

#### Passo 6b — Etapa 3: workflow runs e recuperação

- **Comando:** `python -m pipeline --config config_replicacao.yaml --etapa runs`
- **Tempo:** **9 min 31 s** (19,0 s de CPU)
- **Saída relevante:** `[30/30]` repositórios, coleta mensal com barra de progresso
  mostrando a cota restante do token a cada requisição. Gerou `metricas_runs.csv`
  (30 linhas, 7 colunas) e os checkpoints em `data_replicacao/runs/`. Evidência em
  [`evidencias/passo6b_runs.log`](evidencias/passo6b_runs.log).
- **Erro:** nenhum
- **Saiu do README:** sim (o contorno do Passo 5)
- **Issue aberta:** nenhuma

#### Passo 6c — Etapa 4: consolidação e proveniência

- **Comando:** `python -m pipeline --config config_replicacao.yaml --etapa consolidar`
- **Tempo:** **0,22 s**
- **Saída relevante:** `dataset.csv` com 30 repositórios e 36 colunas, mais o
  `MANIFEST.json` com hashes SHA-256 e metadados. As 36 colunas são **idênticas, na mesma
  ordem**, às do `data/dataset.csv` publicado pelo grupo — o esquema reproduz
  perfeitamente. O README §10 descreve 33 colunas, o que gerou a Issue
  [#68](https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software/issues/68). Evidência em
  [`evidencias/passo6c_consolidar.log`](evidencias/passo6c_consolidar.log).
- **Erro:** nenhum
- **Saiu do README:** sim (o contorno do Passo 5)
- **Issue aberta:** [#68](https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software/issues/68)

### Passo 7 — Análises e testes sem API (README §7 e §9)

#### Passo 7a — Análises das RQ 01 a 04 e classificação C1

- **Comando:** `python -m analises.rq01_04 --dataset data_replicacao/dataset.csv --saida analises/saida_replicacao`
- **Tempo:** **2,4 s**
- **Saída relevante:** gerou os nove artefatos que o README §7 promete
  (`RESUMO_RQ01_04.md`, cinco CSVs e três figuras PNG). Medianas obtidas na subamostra:
  Lead Time (a) 216,35 h e (b) 204,04 h, CFR (a) 0,025 e (b) 0,138, recuperação 18,84 h
  em 23 dos 30 repositórios. Classificação geral: 3 Low, 13 Medium, 11 High e 3 Elite.
  Evidência em [`evidencias/passo7a_analises.log`](evidencias/passo7a_analises.log).
- **Erro:** nenhum
- **Saiu do README:** **sim, parcialmente** — o README §7 mostra apenas
  `python -m analises.rq01_04`, que leria o `data/dataset.csv` publicado por eles, não o
  que obtivemos. A opção `--dataset` existe e aparece no `--help` do módulo, mas não está
  documentada no README.
- **Issue aberta:** nenhuma — é a mesma lacuna de parametrização da [#65](https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software/issues/65)

#### Passo 7b — Suíte de testes do grupo

- **Comando:** `python -m pytest --cov=metricas --cov=pipeline`
- **Tempo:** **13,8 s**
- **Saída relevante:** **159 testes passam**, 2 avisos, cobertura total de 77%. Todos os
  módulos de `metricas/` ficam em 100%; a cobertura menor está em `pipeline/` (de 0% em
  `__main__.py` a 91% em `http.py`). Evidência em
  [`evidencias/passo7b_testes.log`](evidencias/passo7b_testes.log).
- **Erro:** nenhum
- **Saiu do README:** não
- **Issue aberta:** nenhuma

## 5. Issues abertas no repositório do grupo autor

Uma Issue por problema de execução ou de documentação, cada uma com o comando executado,
a mensagem de erro completa, o ambiente (SO e versão do Python) e o resultado esperado ×
o obtido.

| # | Problema | Tipo | Severidade | Link |
| --- | --- | --- | --- | --- |
| 1 | Não há como executar o pipeline sobre uma lista/subamostra dada de repositórios | execução e documentação | alta | [#65](https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software/issues/65) |
| 2 | README §10 aponta para caminhos `file:///c:/Users/vitve/OneDrive/...`, quebrados fora da máquina do autor | documentação | média | [#66](https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software/issues/66) |
| 3 | README §1 instala as dependências sem criar ambiente virtual | documentação | baixa | [#67](https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software/issues/67) |
| 4 | README §10 descreve o dataset com 33 colunas, mas o arquivo tem 36 | documentação | baixa | [#68](https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software/issues/68) |

## 6. Resumo para o artigo

### O estudo foi executável?

**Sim, com um contorno que exigiu sair do README.** O pipeline rodou de ponta a ponta
sobre os 30 repositórios sorteados e produziu todos os artefatos que o README promete:
`dataset.csv` com 36 colunas **idênticas, na mesma ordem**, às do dataset publicado pelo
grupo, mais `MANIFEST.json`, os CSVs intermediários e os nove artefatos das análises das
RQ 01 a 04. A suíte de testes deles passa inteira (159 testes, 77% de cobertura).

A ressalva é de escopo, não de código: **não existe forma, documentada ou não, de
executar o pipeline sobre um conjunto dado de repositórios** (Issue
[#65](https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software/issues/65)). A Etapa 1 sempre re-seleciona candidatos pela busca por faixas de
estrelas, e `--limite 30` devolve outros 30 — instáveis entre execuções, porque a busca
depende da contagem de estrelas do momento. Para rodar sobre a subamostra foi preciso ler
`config.yaml` e `pipeline/__main__.py`, descobrir que as etapas 2 e 3 consomem
`caminhos.repos_csv` e escrever à mão um `repos.csv` com os 30 sorteados. Seguindo
**apenas** o README, a replicação cruzada como o enunciado a define não é executável.

### Quanto tempo levou?

**42 min 20 s** somando todos os comandos, dos quais **38 min 38 s (91%) foram espera da
API do GitHub**. O tempo de CPU somado não chega a 1 minuto.

| Etapa | Tempo |
| --- | --- |
| Clone | 27,4 s |
| Instalação das dependências | 57,1 s |
| `--dry-run` | 1,1 s |
| Primeira tentativa sem `.env` | 0,2 s |
| Investigar como restringir a amostra | ~2 min |
| Sorteio da subamostra | 0,07 s |
| Etapa 2 (releases e lead time) | **29 min 07 s** |
| Etapa 3 (workflow runs e recuperação) | **9 min 31 s** |
| Etapa 4 (consolidação) | 0,22 s |
| Análises das RQ 01 a 04 | 2,4 s |
| Suíte de testes | 13,8 s |

Consumo de cota: cerca de **1.676 requisições** para as etapas 2 e 3 sobre 30
repositórios (a cota do token caiu de 5.000 para 3.324). O `--dry-run` projeta 6.600
requisições para essas duas etapas sobre 300 repositórios, o que daria ~660 para 30 — a
estimativa subestima o consumo real em cerca de **2,5×**. Não abri Issue sobre isso
porque a comparação supõe escala linear, que o próprio pipeline não promete.

### O que impediu ou dificultou?

Um ponto sério e três menores, todos registrados como Issue:

1. **[#65](https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software/issues/65) (alta)** — impossível rodar sobre uma subamostra dada; exigiu ler o
   código. É o único obstáculo que afeta a validade da replicação, e não um defeito de
   implementação: é uma funcionalidade que o estudo precisa e não tem.
2. **[#66](https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software/issues/66) (média)** — os links da seção 10 do README apontam para o disco
   local de um autor (`file:///c:/Users/vitve/OneDrive/...`), inclusive o do
   `DICIONARIO_DADOS.md`, que é a referência das colunas do dataset.
3. **[#67](https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software/issues/67) (baixa)** — a seção 1 instala as dependências sem ambiente virtual.
4. **[#68](https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software/issues/68) (baixa)** — o README descreve 33 colunas; o arquivo tem 36.

Em contrapartida, quatro pontos **facilitaram** bastante e merecem registro no artigo: o
`--dry-run` permite dimensionar o custo da API antes de qualquer coleta; o erro de token
ausente nomeia o arquivo e a variável a criar; as nove dependências instalaram sem atrito
em Python 3.14/arm64, sem nenhum pin quebrado; e o cache (`.cache_http/`) mais os
checkpoints por mês tornam a retomada transparente, exatamente como o README promete.

Veredito para o artigo: **o estudo é reprodutível quanto ao cálculo das métricas e não
quanto à seleção da amostra**. Quem replicar obtém o mesmo esquema de dados e o mesmo
comportamento do pipeline, mas não consegue — seguindo a documentação — apontá-lo para os
mesmos repositórios.

## 7. Resultados obtidos

Em [`resultados_obtidos/`](resultados_obtidos/), como saíram do pipeline do grupo
replicado, sem nenhuma edição:

| Arquivo | Conteúdo |
| --- | --- |
| `dataset.csv` | Dataset consolidado da subamostra: 30 repositórios, 36 colunas |
| `MANIFEST.json` | Manifesto de proveniência com os hashes SHA-256 da execução |
| `repos.csv` | Os 30 repositórios sorteados, no formato de entrada das etapas 2 e 3 |
| `lead_time_release.csv` | Entregas, Lead Time (a) e (b), CFR (b) e Rework Rate |
| `metricas_runs.csv` | CFR (a) e tempo de recuperação por repositório |
| `releases_ignoradas_release.csv` | Releases fora do Lead Time, por motivo |
| `analises/` | Os artefatos do README §7: `RESUMO_RQ01_04.md` e os cinco CSVs das RQ 01 a 04 e da classificação C1 |

A comparação com os números publicados pelo grupo é o objeto da Issue seguinte (#52) e
parte destes arquivos.
