"""RQ 07: o quanto a classificação DORA depende da definição operacional (sensibilidade).

Cada repositório é classificado em Elite/High/Medium/Low sob quatro combinações de
definições, e as classificações são comparadas par a par:

| Combinação | Unidade de deploy | Lead time | CFR |
| --- | --- | --- | --- |
| C1 (referência) | release | (a) por release | (a) proxy de CI |
| C2 | release + pré-release | (b) por commit | (b) proxy de entrega |
| C3 | tag | (b) por commit | (a) proxy de CI |
| C4 | release | (b) por commit | (b) proxy de entrega |

A C4 não é uma exigência do enunciado: ela muda **só as variantes das métricas** e mantém a
unidade. Sem ela, C1 × C2 mistura dois efeitos (trocar a unidade e trocar as variantes) e a
pergunta "a classificação depende da unidade ou da variante?" não tem resposta. Com ela:

- C1 × C4 isola o efeito de trocar as variantes, com a unidade fixa;
- C2 × C4 isola o efeito de trocar a unidade (release → release + pré-release), com as
  variantes fixas.

As faixas e a mediana das notas vêm de `dora_selection.rating`, as mesmas da C1: a análise
não reescreve nenhum limite. O tempo de recuperação e o CFR (a) usam workflow runs e não
dependem da unidade de deploy; entram iguais em todas as combinações.

As métricas por unidade vêm de `variantes.csv`. Uma unidade cuja coleta falhou
(`collection_complete` falso) fica sem valor, e nunca vira "zero deploys" e, com isso, Low.
"""
import warnings
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score

from dora_selection import rating

from . import classificacao_c1, comum, estilo, rq05, rq06


UNIDADES = ("release", "release_prerelease", "tag")
# nome → (unidade de deploy, variante do Lead Time, variante do CFR)
COMBINACOES = {"C1": ("release", "a", "a"), "C2": ("release_prerelease", "b", "b"),
               "C3": ("tag", "b", "a"), "C4": ("release", "b", "b")}
ROTULOS_UNIDADE = {"release": "release", "release_prerelease": "release + pré-release", "tag": "tag"}
NOMES = tuple(COMBINACOES)
PARES = tuple(combinations(NOMES, 2))
# As três métricas cuja definição pode mudar entre combinações; a recuperação nunca muda.
METRICAS = {"df": "Deployment Frequency", "lt": "Lead Time", "cfr": "Change Failure Rate"}
SEM_NIVEL = classificacao_c1.SEM_CLASSIFICACAO
NIVEIS = classificacao_c1.NIVEIS
ALPHA = 0.05
NOTAS = {nivel: rating.SCORES[nivel] for nivel in rating.LEVELS}
COLUNAS_UNIDADE = {"deployment_frequency_per_week": "df", "lead_time_a_hours": "lt_a",
                   "lead_time_b_hours": "lt_b", "cfr_b": "cfr_b"}


def rotulo(nome):
    unidade, lt, cfr = COMBINACOES[nome]
    return f"{nome}: {ROTULOS_UNIDADE[unidade]}, LT ({lt}), CFR ({cfr})"


def metricas_por_unidade(dados):
    """Métricas de cada unidade por repositório, na ordem de `repositorios.csv`.

    Unidade com coleta marcada como incompleta fica toda ausente. Um par repositório ×
    unidade repetido é erro: seria impossível dizer qual linha vale.
    """
    variantes = dados.variantes
    repositorios = dados.repositorios["repository"]
    saida = {}
    for unidade in UNIDADES:
        linhas = variantes[variantes["unit"].eq(unidade).fillna(False)] if not variantes.empty else variantes
        if not linhas.empty and linhas["repository"].duplicated().any():
            raise ValueError(f"RQ 07: variantes.csv repete repositórios na unidade {unidade}.")
        if linhas.empty:
            quadro = pd.DataFrame(np.nan, index=repositorios, columns=list(COLUNAS_UNIDADE.values()))
            quadro["completa"] = False
        else:
            quadro = linhas.set_index("repository")[[*COLUNAS_UNIDADE, "collection_complete"]]
            quadro = quadro.rename(columns={**COLUNAS_UNIDADE, "collection_complete": "completa"})
            quadro["completa"] = quadro["completa"].astype("boolean").fillna(True).astype(bool)
            for coluna in COLUNAS_UNIDADE.values():
                quadro[coluna] = comum.serie_numerica(quadro[coluna])
            quadro = quadro.reindex(repositorios)
            quadro["completa"] = quadro["completa"].astype("boolean").fillna(False).astype(bool)
            quadro.loc[~quadro["completa"], list(COLUNAS_UNIDADE.values())] = np.nan
        saida[unidade] = quadro
    return saida


def nivel_ou_none(metrica, valor):
    """Nível DORA de um valor; ausente continua ausente, nunca vira Low."""
    return classificacao_c1.nivel(metrica, valor)


def classificar_combinacoes(dados, referencia=None):
    """Níveis das quatro métricas e o nível geral de cada repositório, em cada combinação.

    Devolve uma linha por repositório com as colunas `<C>_df`, `<C>_lt`, `<C>_cfr`, `<C>_rec`
    e `<C>_geral`. Nível ausente é None.
    """
    por_unidade = metricas_por_unidade(dados)
    c1 = classificacao_c1.classificar(dados) if referencia is None else referencia
    c1 = c1.set_index("repository")
    linhas = []
    for repositorio in dados.repositorios["repository"]:
        linha = {"repository": repositorio}
        ref = c1.loc[repositorio]
        for nome, (unidade, lt, cfr) in COMBINACOES.items():
            valores = por_unidade[unidade].loc[repositorio]
            niveis = {
                "df": nivel_ou_none("deployment_frequency", valores["df"]),
                "lt": nivel_ou_none("lead_time", valores[f"lt_{lt}"]),
                # O CFR (a) vem do nível da C1, que parte de repositorios.csv; o (b) é da unidade.
                "cfr": (ref["change_failure_rate_level"] if cfr == "a" else
                        nivel_ou_none("change_failure_rate", valores["cfr_b"])),
                "rec": ref["recovery_time_level"]}
            niveis = {chave: (None if pd.isna(nivel) else nivel) for chave, nivel in niveis.items()}
            # Coleta da unidade falhou: sobram só o CFR (a) e a recuperação, que não bastam para
            # um nível geral. Sem isso, o repositório viraria "Elite" por duas métricas.
            geral = (rating.overall_classification(list(niveis.values()))["overall"]
                     if valores["completa"] else None)
            linha.update({f"{nome}_{chave}": nivel for chave, nivel in niveis.items()})
            linha[f"{nome}_geral"] = geral
        linhas.append(linha)
    return pd.DataFrame(linhas, columns=["repository", *[f"{n}_{c}" for n in NOMES
                                                         for c in (*METRICAS, "rec", "geral")]])


def kappa_ponderado(a, b):
    """Kappa de Cohen com peso linear sobre as notas 1 a 4; NaN quando é indefinido.

    O peso linear faz Elite→High valer menos que Elite→Low, porque as categorias são
    ordenadas. Fica indefinido (NaN) com menos de dois pares ou quando os dois lados têm uma
    única categoria: nesse caso a concordância esperada ao acaso já é total (0/0).
    """
    x, y = (pd.Series(lado).map(NOTAS) for lado in (a, b))
    pares = pd.concat([x, y], axis=1).dropna()
    if len(pares) < 2 or pd.concat([pares.iloc[:, 0], pares.iloc[:, 1]]).nunique() < 2:
        return float("nan")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        valor = cohen_kappa_score(pares.iloc[:, 0].astype(int), pares.iloc[:, 1].astype(int),
                                  weights="linear", labels=[1, 2, 3, 4])
    return float(valor) if np.isfinite(valor) else float("nan")


def comparar(wide, primeira, segunda, coluna):
    """Compara duas combinações numa coluna de nível, só nos repositórios classificados nas duas."""
    x, y = wide[f"{primeira}_{coluna}"], wide[f"{segunda}_{coluna}"]
    ambos = x.notna() & y.notna()
    n = int(ambos.sum())
    mudaram = int((x[ambos] != y[ambos]).sum())
    kappa = kappa_ponderado(x[ambos], y[ambos])
    return {"n": n, "so_na_primeira": int((x.notna() & y.isna()).sum()),
            "so_na_segunda": int((x.isna() & y.notna()).sum()), "mudaram": mudaram,
            "pct_mudou": mudaram / n if n else float("nan"), "kappa": kappa,
            "interpretacao": comum.landis_koch(kappa)}


def tabela_de_pares(wide):
    """Uma linha por par de combinações e por métrica: % que mudou e kappa ponderado."""
    linhas = []
    for primeira, segunda in PARES:
        for coluna, nome in (("geral", "Classificação geral"), *METRICAS.items()):
            linhas.append({"par": f"{primeira} × {segunda}", "metrica": nome,
                           **comparar(wide, primeira, segunda, coluna)})
    return pd.DataFrame(linhas)


def matriz_transicao(wide, primeira, segunda):
    """Contagem de repositórios por (nível na primeira, nível na segunda); ausente é a última linha."""
    x = wide[f"{primeira}_geral"].fillna(SEM_NIVEL)
    y = wide[f"{segunda}_geral"].fillna(SEM_NIVEL)
    cruzada = pd.crosstab(x, y).reindex(index=NIVEIS, columns=NIVEIS, fill_value=0)
    cruzada.index.name = f"{primeira} \\ {segunda}"
    return cruzada.reset_index()


def distribuicao(wide):
    """Contagem dos níveis gerais por combinação."""
    return pd.DataFrame([{"combinacao": nome, **classificacao_c1.contagem_por_nivel(wide[f"{nome}_geral"])}
                         for nome in NOMES])


def series_da_combinacao(dados, por_unidade, nome):
    """DF, Lead Time e CFR de cada repositório sob a combinação, mais a recuperação (fixa)."""
    unidade, lt, cfr = COMBINACOES[nome]
    quadro = por_unidade[unidade]
    return pd.DataFrame({
        "repository": dados.repositorios["repository"].to_numpy(),
        "df": quadro["df"].to_numpy(),
        "lt": quadro[f"lt_{lt}"].to_numpy(),
        "cfr": (comum.serie_numerica(dados.repositorios["change_failure_rate"]).to_numpy() if cfr == "a"
                else quadro["cfr_b"].to_numpy()),
        "recuperacao": comum.serie_numerica(dados.repositorios["recovery_hours"]).to_numpy()})


def robustez_descritiva(series):
    """Mediana e IQR de DF, Lead Time e CFR por combinação, e a variação da mediana frente à C1."""
    linhas = []
    for nome, quadro in series.items():
        for coluna, metrica in METRICAS.items():
            resumo = comum.resumo(quadro[coluna])
            base = comum.resumo(series["C1"][coluna])["mediana"]
            variacao = (resumo["mediana"] / base - 1 if np.isfinite(base) and base != 0
                        and np.isfinite(resumo["mediana"]) else float("nan"))
            linhas.append({"combinacao": nome, "metrica": metrica,
                           **{chave: resumo[chave] for chave in ("n", "mediana", "q1", "q3", "iqr")},
                           "variacao_mediana_vs_c1": variacao})
    return pd.DataFrame(linhas)


def sinal(valor):
    return "indefinido" if not np.isfinite(valor) else ("positivo" if valor > 0 else "negativo" if valor < 0 else "nulo")


def robustez_spearman(series):
    """Spearman DF × CFR sob cada combinação, e se a conclusão da RQ 05 se mantém frente à C1."""
    linhas, base = [], rq05.correlacao(series["C1"]["df"], series["C1"]["cfr"])
    for nome, quadro in series.items():
        teste = rq05.correlacao(quadro["df"], quadro["cfr"])
        mesmo_sinal = sinal(teste["rho"]) == sinal(base["rho"]) != "indefinido"
        mesma_significancia = (teste["p"] < ALPHA) == (base["p"] < ALPHA) if np.isfinite(teste["p"]) and np.isfinite(base["p"]) else False
        linhas.append({"combinacao": nome, "n": teste["n"], "rho": teste["rho"], "p": teste["p"],
                       "forca": teste["forca"], "sinal": sinal(teste["rho"]),
                       "mantem_sinal": bool(mesmo_sinal), "mantem_significancia": bool(mesma_significancia),
                       "conclusao_mantida": bool(mesmo_sinal and mesma_significancia)})
    return pd.DataFrame(linhas)


def robustez_rq06(dados, series):
    """Refaz a família principal da RQ 06 (4 fatores × 4 métricas, Holm) sob cada combinação.

    Os grupos (linguagem e quartis) não dependem da unidade de deploy, então a partição é a
    mesma em todas: só os valores das métricas mudam. Compara o conjunto de testes que
    rejeitam H0 após Holm com o da C1.
    """
    grupos, _ = rq06.definir_grupos(dados.repositorios)
    metricas = ("df", "lt", "cfr", "recuperacao")
    rejeitados = {}
    for nome, quadro in series.items():
        tabela, _ = rq06.familia(quadro, grupos, metricas, nome)
        rejeitados[nome] = {(linha["fator"], linha["metrica"])
                            for _, linha in tabela[tabela["rejeita"].fillna(False)].iterrows()}
    base = rejeitados["C1"]
    return pd.DataFrame([{
        "combinacao": nome, "rejeitam_h0": len(conjunto), "iguais_a_c1": len(conjunto & base),
        "so_nesta": len(conjunto - base), "so_na_c1": len(base - conjunto),
        "lista": "; ".join(f"{fator}/{metrica}" for fator, metrica in sorted(conjunto))}
        for nome, conjunto in rejeitados.items()])


def conferencia(dados, por_unidade, wide):
    """A unidade `release` de variantes.csv e a C1 daqui batem com o pipeline e com `classificacao_c1`?"""
    base = dados.repositorios.set_index("repository")
    release = por_unidade["release"]
    pares = (("df", "releases_per_week"), ("lt_a", "release_lead_time_hours"),
             ("lt_b", "commit_lead_time_hours"), ("cfr_b", "delivery_change_failure_rate"))
    divergentes = {}
    for coluna, referencia in pares:
        esperado = comum.serie_numerica(base[referencia]).reindex(release.index)
        diferente = ~np.isclose(release[coluna], esperado, equal_nan=True, rtol=1e-9, atol=1e-9)
        divergentes[coluna] = int(diferente.sum())
    c1 = classificacao_c1.classificar(dados).set_index("repository")["overall"]
    igual = wide.set_index("repository")["C1_geral"].fillna(SEM_NIVEL).eq(c1.fillna(SEM_NIVEL))
    return {"unidade_release_vs_repositorios": divergentes, "c1_diverge_da_classificacao_c1": int((~igual).sum()),
            "repositorios": int(len(wide))}


def figura_transicao(matriz, primeira, segunda, saida):
    """Mapa de calor da matriz de transição, com a contagem em cada célula."""
    plt = estilo.aplicar()
    figura, eixo = plt.subplots(figsize=estilo.TAMANHO_SIMPLES)
    valores = matriz.drop(columns=matriz.columns[0]).to_numpy(dtype=float)
    eixo.imshow(valores, cmap="Blues", aspect="auto")
    eixo.grid(False)
    maximo = valores.max() if valores.size and valores.max() else 1
    for i in range(valores.shape[0]):
        for j in range(valores.shape[1]):
            eixo.text(j, i, f"{int(valores[i, j])}", ha="center", va="center", fontsize=7,
                      color="white" if valores[i, j] > maximo / 2 else "black")
    rotulos = [nivel.replace("Sem classificação", "Sem") for nivel in NIVEIS]
    eixo.set(xticks=range(len(NIVEIS)), yticks=range(len(NIVEIS)), xticklabels=rotulos,
             yticklabels=rotulos, xlabel=f"nível geral em {segunda}", ylabel=f"nível geral em {primeira}")
    eixo.tick_params(axis="x", rotation=30)
    figura.tight_layout()
    return estilo.salvar(figura, saida, f"rq07_transicao_{primeira}_{segunda}")


def figura_distribuicao(contagens, saida):
    """Barras empilhadas do nível geral em cada combinação."""
    plt = estilo.aplicar()
    figura, eixo = plt.subplots(figsize=(estilo.LARGURA, 2.2))
    acumulado = np.zeros(len(contagens))
    for nivel in NIVEIS:
        valores = contagens[nivel].to_numpy(dtype=float)
        eixo.barh(range(len(contagens)), valores, left=acumulado, height=0.62, label=nivel,
                  color=estilo.NIVEIS[nivel], edgecolor="white", linewidth=0.5)
        acumulado += valores
    eixo.set(yticks=range(len(contagens)), yticklabels=list(contagens["combinacao"]),
             xlabel="repositórios", xlim=(0, max(acumulado.max(), 1)))
    eixo.invert_yaxis()
    eixo.grid(axis="y", visible=False)
    estilo.contagem_inteira(eixo, das_contagens="x")
    eixo.legend(ncols=len(NIVEIS), frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0),
                columnspacing=1.0, handlelength=1.2)
    figura.tight_layout()
    return estilo.salvar(figura, saida, "rq07_distribuicao")


def porcentagem(valor):
    return "--" if not np.isfinite(valor) else f"{comum.numero(valor * 100, 1)}%"


def linha_do_par(pares, par, metrica="Classificação geral"):
    return pares[(pares["par"] == par) & (pares["metrica"] == metrica)].iloc[0]


def notas(pares, spearman, rq06_tabela, distribuicao_, descricao, confere, total):
    """Rascunho da seção: o que mudou, o que isola cada efeito e se as conclusões resistem."""
    numero = comum.numero
    marcadores = []
    for primeira, segunda in PARES:
        linha = linha_do_par(pares, f"{primeira} × {segunda}")
        marcadores.append(
            f"- {primeira} × {segunda}: {linha['mudaram']} de {linha['n']} repositórios mudaram de "
            f"categoria ({porcentagem(linha['pct_mudou'])}); κ ponderado = "
            f"{numero(linha['kappa'], 3) if np.isfinite(linha['kappa']) else 'indefinido'} "
            f"({linha['interpretacao']}).")
    efeito_variantes, efeito_unidade = linha_do_par(pares, "C1 × C4"), linha_do_par(pares, "C2 × C4")
    por_metrica = pares[(pares["par"] == "C1 × C2") & (pares["metrica"] != "Classificação geral")]
    pior = por_metrica.sort_values("pct_mudou", ascending=False).iloc[0] if not por_metrica.empty else None
    mantidas = int(spearman["conclusao_mantida"].sum())
    ref = spearman.iloc[0]
    rq06_outras = rq06_tabela[rq06_tabela["combinacao"] != "C1"]
    base06 = int(rq06_tabela.iloc[0]["rejeitam_h0"])
    blocos = [
        "# RQ 07 — Sensibilidade da classificação DORA à definição operacional",
        comum.paragrafo(
            f"Os {total} repositórios foram classificados sob quatro combinações de definições: "
            + "; ".join(rotulo(nome) for nome in NOMES) + ". A C4 não vem do enunciado: ela muda só "
            "as variantes das métricas e mantém a unidade, o que permite separar os dois efeitos que "
            "C1 × C2 mistura. Um repositório só entra numa comparação quando está classificado nas "
            "duas combinações; o n de cada par está na tabela."),
        "## Quanto a classificação muda", "\n".join(marcadores),
        comum.paragrafo(
            f"Isolando os efeitos: trocar só as variantes das métricas (C1 × C4) muda "
            f"{porcentagem(efeito_variantes['pct_mudou'])} dos repositórios, e trocar só a unidade de "
            f"deploy (C2 × C4, de release para release + pré-release) muda "
            f"{porcentagem(efeito_unidade['pct_mudou'])}."),
    ]
    if pior is not None:
        blocos.append(comum.paragrafo(
            f"Em C1 × C2, a métrica que mais muda de nível é {pior['metrica']} "
            f"({porcentagem(pior['pct_mudou'])} dos {pior['n']} repositórios comparáveis)."))
    blocos += [
        "## As conclusões das RQ 01 a 06 resistem?",
        comum.paragrafo(
            "**RQ 05 (DF × CFR).** O Spearman entre frequência e CFR, recalculado sob cada "
            f"combinação, mantém o sinal e a significância da C1 (ρ = {numero(ref['rho'], 3)}; "
            f"p = {format(ref['p'], '.3g').replace('.', ',') if np.isfinite(ref['p']) else '--'}) em "
            f"{mantidas} de {len(spearman)} combinações, contando a própria C1."),
        comum.paragrafo(
            "**RQ 06 (fatores).** Na família principal (4 fatores × 4 métricas, Holm), "
            f"{base06} testes rejeitam H0 na C1. Nas demais combinações, "
            + ", ".join(f"{linha['combinacao']} {linha['rejeitam_h0']} "
                        f"({linha['iguais_a_c1']} em comum com a C1, {linha['so_nesta']} novos e "
                        f"{linha['so_na_c1']} perdidos)" for _, linha in rq06_outras.iterrows()) + "."),
        comum.paragrafo(
            "**RQ 01 a 03.** As medianas e IQR de DF, Lead Time e CFR sob cada combinação, com a "
            "variação da mediana frente à C1, estão em `resultados/tabelas/rq07_robustez_descritiva.csv`."),
        "## Conferência",
        comum.paragrafo(
            "A unidade `release` de `variantes.csv` foi comparada com `repositorios.csv`: "
            + ", ".join(f"{coluna} {quantidade} divergência(s)"
                        for coluna, quantidade in confere["unidade_release_vs_repositorios"].items())
            + f". A C1 deste módulo diverge da `classificacao_c1` em {confere['c1_diverge_da_classificacao_c1']} "
            f"de {confere['repositorios']} repositórios."),
        "## Limites",
        comum.paragrafo(
            "O kappa ponderado fica indefinido quando uma combinação classifica todos os repositórios "
            "na mesma categoria. Os p-valores são exploratórios e a comparação de conjuntos da RQ 06 "
            "depende de cada família de Holm ser avaliada isoladamente. Todas as combinações usam a "
            "mesma heurística corretiva (F1 ≈ 0,75) e a mesma janela; a sensibilidade a elas não foi "
            "medida aqui. Na unidade `tag`, a data do deploy é a do commit, e não a de uma publicação, "
            "o que encurta o Lead Time por construção."),
    ]
    return "\n\n".join(blocos) + "\n"


def sem_variantes(saida):
    """Sem `variantes.csv` a análise não roda; deixa um aviso explícito em vez de resultados vazios."""
    texto = ("# RQ 07 — indisponível\n\n" + comum.paragrafo(
        "Esta análise precisa de `variantes.csv`, gerado pelo pipeline com `variantes: true` no "
        "`config.yaml` (ou `--variants`). Sem ele não há como classificar os repositórios sob a "
        "unidade `tag` nem sob release + pré-release.") + "\n")
    comum.salvar_texto(texto, saida, "notas_rq07")
    return {"disponivel": False, "motivo": "variantes.csv ausente ou vazio"}


def executar(dados, saida="resultados"):
    """Classifica sob as quatro combinações, compara os pares e testa a robustez das RQs."""
    saida = Path(saida)
    if dados.variantes.empty:
        return sem_variantes(saida)
    por_unidade = metricas_por_unidade(dados)
    referencia = classificacao_c1.classificar(dados)
    wide = classificar_combinacoes(dados, referencia)
    pares = tabela_de_pares(wide)
    series = {nome: series_da_combinacao(dados, por_unidade, nome) for nome in NOMES}
    descritiva = robustez_descritiva(series)
    spearman = robustez_spearman(series)
    rq06_tabela = robustez_rq06(dados, series)
    contagens = distribuicao(wide)
    confere = conferencia(dados, por_unidade, wide)
    comum.salvar_csv(wide, saida, "rq07_por_repositorio")
    comum.salvar_tabela(pares, saida, "rq07_pares", casas=3)
    comum.salvar_tabela(contagens, saida, "rq07_distribuicao", casas=0)
    comum.salvar_tabela(descritiva, saida, "rq07_robustez_descritiva", casas=3)
    comum.salvar_tabela(spearman, saida, "rq07_robustez_spearman", casas=4)
    comum.salvar_tabela(rq06_tabela, saida, "rq07_robustez_rq06", casas=0)
    matrizes = {}
    for primeira, segunda in PARES:
        matrizes[f"{primeira}_{segunda}"] = matriz_transicao(wide, primeira, segunda)
        comum.salvar_tabela(matrizes[f"{primeira}_{segunda}"], saida, f"rq07_transicao_{primeira}_{segunda}", casas=0)
    figuras = [figura_distribuicao(contagens, saida).name]
    figuras += [figura_transicao(matrizes[chave], *chave.split("_"), saida).name
                for chave in ("C1_C2", "C1_C3", "C1_C4")]
    comum.salvar_texto(notas(pares, spearman, rq06_tabela, contagens, descritiva, confere, len(wide)),
                       saida, "notas_rq07")
    resultado = {"disponivel": True, "repositorios": int(len(wide)), "combinacoes": {
                     nome: {"unidade": u, "lead_time": lt, "cfr": cfr} for nome, (u, lt, cfr) in COMBINACOES.items()},
                 "pares": pares, "distribuicao": contagens, "robustez_descritiva": descritiva,
                 "robustez_spearman": spearman, "robustez_rq06": rq06_tabela, "conferencia": confere,
                 "figuras": figuras, "por_repositorio": wide}
    comum.salvar_json(resultado, saida, "rq07")
    return resultado
