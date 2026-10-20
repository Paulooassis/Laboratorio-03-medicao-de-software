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

- **Comando:** _(pendente: exige `GITHUB_TOKEN`)_
- **Tempo:** _(pendente)_
- **Saída relevante:** _(pendente)_
- **Erro:** _(pendente)_
- **Contorno aplicado:** `repos.csv` restrito aos 30 sorteados, conforme o Passo 5
- **Saiu do README:** sim (o contorno do Passo 5)
- **Issue aberta:** _(pendente)_

### Passo 7 — Análises e testes sem API (README §7 e §9)

- **Comando:** _(pendente)_ `python -m analises.rq01_04` e `python -m pytest --cov=metricas --cov=pipeline`
- **Tempo:** _(pendente)_
- **Saída relevante:** _(pendente)_
- **Saiu do README:** não
- **Issue aberta:** _(pendente)_

## 5. Issues abertas no repositório do grupo autor

Uma Issue por problema de execução ou de documentação, cada uma com o comando executado,
a mensagem de erro completa, o ambiente (SO e versão do Python) e o resultado esperado ×
o obtido.

| # | Problema | Tipo | Severidade | Link |
| --- | --- | --- | --- | --- |
| 1 | Não há como executar o pipeline sobre uma lista/subamostra dada de repositórios | execução e documentação | alta | [#65](https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software/issues/65) |
| 2 | README §10 aponta para caminhos `file:///c:/Users/vitve/OneDrive/...`, quebrados fora da máquina do autor | documentação | média | [#66](https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software/issues/66) |
| 3 | README §1 instala as dependências sem criar ambiente virtual | documentação | baixa | [#67](https://github.com/JoaoAlmeida02/Laborat-rio-de-Experimenta-o-de-Software/issues/67) |

## 6. Resumo para o artigo

- **O estudo foi executável?** Parcialmente, e o veredito final depende do Passo 6. Até
  aqui: clone, instalação e `--dry-run` funcionaram sem nenhum atrito, em menos de 2
  minutos somados e sem sair do README. A coleta falha sem `.env`, como o README avisa, e
  a mensagem de erro é acionável. O obstáculo real não é defeito de código, é de escopo:
  **o pipeline não aceita a subamostra como entrada**, então a replicação cruzada como o
  enunciado a define não é executável seguindo só o README.
- **Quanto tempo levou?** _(a completar com o Passo 6)_ Até o Passo 5: ~27 s de clone,
  ~57 s de instalação, ~1 s de `--dry-run` e ~2 min investigando como restringir a
  amostra.
- **O que impediu ou dificultou?** Um ponto sério e dois menores. (1) Não existe forma de
  rodar sobre um conjunto dado de repositórios; a Etapa 1 sempre re-seleciona pela busca
  por estrelas, que muda com o tempo — o contorno exigiu ler o código. (2) Os links da
  seção 10 do README apontam para o disco local do autor. (3) O README instala
  dependências sem ambiente virtual. Em contrapartida, três pontos facilitaram: o
  `--dry-run` dimensiona o custo da API antes da coleta, o erro de token é explícito, e
  todas as dependências instalaram sem atrito em Python 3.14.

## 7. Resultados obtidos

Os CSVs produzidos pela execução ficam em
[`resultados_obtidos/`](resultados_obtidos/), como saíram do pipeline do outro grupo —
sem edição, para que a comparação da Issue seguinte parta do arquivo original.
