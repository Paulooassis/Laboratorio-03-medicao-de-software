# Laboratorio-03-medicao-de-software

## Lab03S01 — Card 1: seleção de repositórios

Pipeline em Python 3.10+ usando somente a biblioteca padrão. Não requer instalação
de pacotes, PyGithub ou configuração de token em arquivo. Não calcula métricas DORA.

### Execução

Na raiz deste repositório, disponibilize `GITHUB_TOKEN` no ambiente do processo.
O programa lê o token exclusivamente dessa variável e não o inclui nas saídas.
Não salve tokens no repositório. A janela deve ser definida antes do experimento;
o exemplo abaixo é apenas ilustrativo, sem garantia de tamanho da amostra.

```powershell
python -m dora_selection --start 2025-01-01T00:00:00Z --end 2025-12-31T23:59:59Z
```

Datas ISO 8601 com fuso horário, precisão de segundos e limites inclusivos são
obrigatórias. Datas são normalizadas para UTC. Opções:

- `--target`: tamanho desejado, padrão 100, mínimo 100;
- `--min-stars`: mínimo de estrelas, padrão 1001;
- `--output`: diretório de saída, padrão `outputs/card1`.

A execução para quando alcança a meta ou esgota os candidatos. Retorna código 0
quando alcança a meta e 1 quando há erro de busca ou amostra insuficiente. Erros
em um repositório geram exclusão `collection_error` e não interrompem os demais.
Erros globais de busca são registrados no funil, com persistência da amostra parcial.
Reexecutar no mesmo diretório substitui os arquivos anteriores; use diretórios
diferentes para experimentos diferentes.

### Regras e saídas

- Busca pública pela API REST oficial, ordenada por estrelas. Faixas acima de
  1000 resultados são subdivididas por estrelas e, se necessário, por criação.
  IDs removem duplicatas; nomes são alternativa quando não há ID.
- Actions é verificado pela existência de workflows registrados no endpoint
  `/actions/workflows`. Workflows desativados também indicam uso de Actions;
  workflows apagados historicamente não são reconstruídos neste card.
- Releases válidas: `draft=false`, `prerelease=false`, `published_at` na janela.
- Runs válidos: `head_branch=default_branch`, evento `push`, `created_at` na
  janela, status `completed`, conclusão `success`, `failure`, `timed_out` ou
  `startup_failure`. As demais conclusões e runs em andamento são ignorados.
- Inclusão: Actions, pelo menos 5 releases e 50 runs válidos, e coleta sem erro.
  Contagens são completas, não apenas interrompidas no limiar. Consultas de
  runs acima de 1000 resultados são subdivididas por tempo e IDs deduplicados.
  Uma faixa indivisível saturada gera erro explícito em vez de contagem truncada.
- Contribuidores: `anon=true`, `per_page=1`, quantidade pela última página do
  header `Link`; sem `last`, paginação completa se houver `next`. É a contagem
  disponibilizada pelo endpoint do GitHub, inclusive contribuidores anônimos,
  sujeita à atualização/cache do próprio serviço.
- Linguagem nula é permitida; dados essenciais ausentes impedem inclusão.

Arquivos em `outputs/card1` (ignorados pelo Git):

| Arquivo | Conteúdo |
| --- | --- |
| `repositories.json` / `.csv` | Todos os candidatos únicos avaliados, metadados, valores dos filtros, inclusão, motivo e erro |
| `selected.json` / `.csv` | Apenas os repositórios incluídos |
| `funnel.json` | Etapas cumulativas, exclusões por motivo, janela, meta, resultado e motivo de parada |

O funil conta os candidatos efetivamente percorridos, e não todos os resultados
potenciais da API. `candidates_found` inclui duplicatas recebidas nas páginas
percorridas; `unique_repositories` conta os candidatos únicos avaliados.
As etapas são cumulativas: Actions → releases suficientes → runs suficientes →
incluídos. Cada descarte recebe um motivo principal, nesta ordem; erros de coleta
prevalecem. Dados ainda não coletados são `null`, não zero. Não há números de
amostra hardcoded. Nenhum cache, retomada ou backoff foi acrescentado.

### Organização

- `dora_selection/api.py`: HTTP, autenticação, erros e paginação por `Link`;
- `dora_selection/search.py`: particionamento de busca e deduplicação;
- `dora_selection/selection.py`: coleta, classificação, filtros e funil;
- `dora_selection/output.py`: persistência JSON/CSV;
- `dora_selection/__main__.py`: execução e configuração;
- `tests/test_card1.py`: testes offline com mocks e dados sintéticos.

### Testes

```powershell
python -m unittest discover -s tests -v
```

Os testes cobrem inclusão/exclusão, conclusões de runs, branch/evento/janela,
releases, contribuidores, funil, paginação, deduplicação, faixas de estrelas/datas,
subdivisão de runs, erros HTTP, token obrigatório, saída e seleção de 100
repositórios simulados. A obtenção de 100 repositórios reais depende de uma janela
com candidatos suficientes, credenciais e limites da API; não é comprovada pelos
testes offline. Tratamento completo de rate limit pertence a outro card.

Referências oficiais:
[busca](https://docs.github.com/en/rest/search/search#search-repositories),
[paginação](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api),
[workflow runs](https://docs.github.com/en/rest/actions/workflow-runs#list-workflow-runs-for-a-repository),
[releases](https://docs.github.com/en/rest/releases/releases#list-releases),
[contribuidores](https://docs.github.com/en/rest/repos/repos#list-repository-contributors).
