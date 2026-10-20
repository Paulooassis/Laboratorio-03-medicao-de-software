# Diário de execução da replicação cruzada

Registro da execução do pipeline do grupo sorteado **usando apenas o README dele**, sobre
uma subamostra de 30 repositórios do dataset original, sem pedir ajuda ao grupo autor.

Travar não é fracasso: é resultado. Todo passo entra aqui, inclusive os que falharam, com
o comando exato, a saída e o contorno — e cada falha de execução ou documentação faltante
vira uma Issue no repositório do grupo autor, listada na seção final.

> **Como preencher:** uma linha por comando executado, na ordem. Cole a mensagem de erro
> **completa**, não um resumo. Quando um contorno exigir sair do README, marque
> "Saiu do README: sim" — é esse o dado que diz se o estudo é replicável como publicado.

## 1. Grupo replicado

| Campo | Valor |
| --- | --- |
| Grupo sorteado | _(a preencher)_ |
| Repositório | _(a preencher: URL)_ |
| Commit/tag replicado | _(a preencher: `git rev-parse HEAD` do clone)_ |
| Data da execução | _(a preencher)_ |
| README seguido | _(a preencher: caminho e seção, ex.: `README.md`, "Como executar")_ |

## 2. Ambiente

| Campo | Valor |
| --- | --- |
| Sistema operacional | _(a preencher: ex. macOS 27.0 / Ubuntu 24.04)_ |
| Versão do Python | _(a preencher: `python --version`)_ |
| Ambiente virtual | venv nova, criada só para esta execução |
| Cache | nenhum: diretório de cache do outro grupo ausente no início |
| Token | `GITHUB_TOKEN` próprio, sem escopos |

## 3. Subamostra

Sorteada por `python -m replicacao.subamostra`, com semente fixa e publicada.

| Campo | Valor |
| --- | --- |
| CSV de origem | _(a preencher: caminho no repositório do outro grupo)_ |
| sha256 do CSV | _(a preencher: de `replicacao/subamostra.json`)_ |
| Semente | 42 |
| Repositórios no universo | _(a preencher)_ |
| Tamanho da subamostra | 30 |
| Lista usada | [`subamostra.csv`](subamostra.csv) |

## 4. Passos executados

### Passo 1 — _(a preencher: o que o README mandou fazer)_

- **Comando:** `(a preencher)`
- **Tempo:** _(a preencher)_
- **Saída relevante:**

```
(a preencher)
```

- **Erro:** _(nenhum / mensagem completa)_
- **Contorno aplicado:** _(nenhum / o que foi feito)_
- **Saiu do README:** _(não / sim — o quê)_
- **Issue aberta:** _(nenhuma / link)_

<!-- Copie o bloco do Passo 1 para cada comando executado, na ordem. -->

## 5. Issues abertas no repositório do grupo autor

Uma Issue por problema de execução ou de documentação, cada uma com o comando executado,
a mensagem de erro completa, o ambiente (SO e versão do Python) e o resultado esperado ×
o obtido.

| # | Problema | Tipo | Link |
| --- | --- | --- | --- |
| 1 | _(a preencher)_ | execução / documentação | _(a preencher)_ |

## 6. Resumo para o artigo

- **O estudo foi executável?** _(a preencher: sim / sim, com contornos / não — e em que
  passo parou)_
- **Quanto tempo levou?** _(a preencher: tempo total, do clone aos CSVs, e quanto disso
  foi espera de API)_
- **O que impediu ou dificultou?** _(a preencher: o que estava faltando no README, o que
  só funcionou saindo dele, e o que teria resolvido)_

## 7. Resultados obtidos

Os CSVs produzidos pela execução ficam em
[`resultados_obtidos/`](resultados_obtidos/), como saíram do pipeline do outro grupo —
sem edição, para que a comparação da Issue seguinte parta do arquivo original.
