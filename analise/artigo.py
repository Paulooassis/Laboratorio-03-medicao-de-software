"""Figuras da seção de Resultados do artigo: distribuição, correlação e dispersão.

As quatro métricas DORA vivem em unidades diferentes (releases/semana, horas,
proporção), então nunca dividem um eixo: cada uma aparece em seu próprio painel. A
distribuição usa violino com boxplot por dentro — o violino mostra a forma (bimodalidade,
cauda) e a caixa mostra mediana e IQR, que são as estatísticas que o estudo reporta.

A matriz de correlação traz **Spearman e Pearson lado a lado**. Spearman é a medida do
estudo, porque as métricas são assimétricas e têm caudas longas; Pearson entra como
contraste, e a diferença entre as duas é informativa: onde Pearson cai muito abaixo de
Spearman, a relação é monótona mas não linear, e um coeficiente linear subestima a
associação.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from scipy.stats import pearsonr, spearmanr

from dora_selection import rating

from . import classificacao_c1 as c1
from . import comum, estilo


# Métrica, rótulo curto, coluna e se a escala é logarítmica.
METRICAS = (
    ("df", "Deployment frequency\n(releases/semana)", "releases_per_week", True),
    ("lt_a", "Lead time (a)\n(horas)", "release_lead_time_hours", True),
    ("cfr_a", "Change failure rate (a)\n(proporção)", "change_failure_rate", False),
    ("recuperacao", "Tempo de recuperação\n(horas)", "recovery_hours", True),
)
# Colunas da matriz de correlação, na ordem em que entram no artigo.
# Rótulos por extenso: o artigo não usa siglas de métrica.
CORRELACAO = (("Frequência", "releases_per_week"),
              ("Lead time (a)", "release_lead_time_hours"),
              ("Lead time (b)", "commit_lead_time_hours"),
              ("Taxa de falha (a)", "change_failure_rate"),
              ("Taxa de falha (b)", "delivery_change_failure_rate"),
              ("Recuperação", "recovery_hours"))


def mapa_divergente():
    """Colormap divergente vermelho–cinza–azul: dois matizes opostos e meio neutro."""
    return LinearSegmentedColormap.from_list("correlacao", estilo.DIVERGENTE)


def coeficientes(quadro, metodo):
    """Matriz de correlação entre as métricas, por pares completos.

    Cada par usa só os repositórios com as duas métricas presentes, sem imputação; `n`
    varia entre pares e por isso é devolvido junto.
    """
    rotulos = [rotulo for rotulo, _ in CORRELACAO]
    valores = pd.DataFrame(np.nan, index=rotulos, columns=rotulos, dtype="float64")
    tamanhos = valores.copy()
    funcao = spearmanr if metodo == "spearman" else pearsonr
    for i, (rotulo_i, coluna_i) in enumerate(CORRELACAO):
        for rotulo_j, coluna_j in CORRELACAO[i:]:
            par = quadro.loc[:, [coluna_i, coluna_j]].dropna()
            if len(par) < 3 or par.iloc[:, 0].nunique() < 2 or par.iloc[:, 1].nunique() < 2:
                continue
            resultado = funcao(par.iloc[:, 0], par.iloc[:, 1])
            coeficiente = float(resultado[0])
            for a, b in ((rotulo_i, rotulo_j), (rotulo_j, rotulo_i)):
                valores.loc[a, b], tamanhos.loc[a, b] = coeficiente, len(par)
    return valores, tamanhos


def tabela_correlacao(quadro):
    """Uma linha por par de métricas, com Spearman, Pearson e o n de cada um."""
    spearman, tamanhos = coeficientes(quadro, "spearman")
    pearson, _ = coeficientes(quadro, "pearson")
    linhas = []
    for i, (rotulo_i, _) in enumerate(CORRELACAO):
        for rotulo_j, _ in CORRELACAO[i + 1:]:
            linhas.append({"par": f"{rotulo_i} × {rotulo_j}",
                           "n": tamanhos.loc[rotulo_i, rotulo_j],
                           "spearman": spearman.loc[rotulo_i, rotulo_j],
                           "pearson": pearson.loc[rotulo_i, rotulo_j]})
    tabela = pd.DataFrame(linhas)
    if tabela.empty:
        return tabela
    tabela["diferenca"] = tabela["spearman"] - tabela["pearson"]
    return tabela.sort_values("spearman", key=abs, ascending=False).reset_index(drop=True)


def figura_violino(repositorios, saida):
    """Violino com boxplot por dentro, um painel por métrica (unidades diferentes)."""
    plt = estilo.aplicar()
    figura, eixos = plt.subplots(1, len(METRICAS), figsize=(estilo.LARGURA, 2.9))
    for eixo, (_, rotulo, coluna, logaritmo) in zip(eixos, METRICAS):
        valores = comum.serie_numerica(repositorios[coluna]).dropna()
        amostra = valores[valores > 0] if logaritmo else valores
        if amostra.empty:
            eixo.set_axis_off()
            continue
        dados = np.log10(amostra) if logaritmo else amostra
        corpo = eixo.violinplot([dados.to_numpy()], showextrema=False, widths=0.85)
        for peca in corpo["bodies"]:
            peca.set(facecolor=estilo.NIVEIS["Medium"], alpha=0.35, edgecolor="none")
        eixo.boxplot([dados.to_numpy()], widths=0.16, tick_labels=[""], patch_artist=True,
                     medianprops={"color": "black", "linewidth": 1.1},
                     boxprops={"facecolor": estilo.NIVEIS["Elite"], "alpha": 0.9,
                               "edgecolor": "none"},
                     whiskerprops={"linewidth": 0.8}, capprops={"linewidth": 0.8},
                     flierprops={"marker": ".", "markersize": 2, "alpha": 0.4})
        eixo.set(xticks=[], title=rotulo)
        eixo.grid(axis="x", visible=False)
        if logaritmo:
            limites = range(int(np.floor(dados.min())), int(np.ceil(dados.max())) + 1)
            eixo.set_yticks(list(limites))
            eixo.set_yticklabels([f"$10^{{{expoente}}}$" for expoente in limites])
            eixo.set_ylabel("escala log", labelpad=1)
        # Fora da área de dados: dentro dela a anotação colidia com a cauda do violino.
        eixo.set_xlabel(f"n = {len(amostra)}\nmediana {comum.numero(float(amostra.median()))}",
                        fontsize=6, color=estilo.NEUTRO, labelpad=2)
    figura.tight_layout()
    return estilo.salvar(figura, saida, "artigo_violino_metricas")


def figura_correlacao(quadro, saida):
    """Spearman e Pearson lado a lado, com o mesmo divergente e a mesma escala."""
    plt = estilo.aplicar()
    spearman, tamanhos = coeficientes(quadro, "spearman")
    pearson, _ = coeficientes(quadro, "pearson")
    figura, eixos = plt.subplots(1, 2, figsize=(estilo.LARGURA, 3.4))
    norma = TwoSlopeNorm(vmin=-1, vcenter=0, vmax=1)
    desenho = None
    for posicao, (eixo, (titulo, matriz)) in enumerate(
            zip(eixos, (("Spearman ρ", spearman), ("Pearson r", pearson)))):
        # pcolormesh, e não imshow: o PDF do artigo precisa ser vetorial, sem imagem
        # embutida. A borda branca dá o respiro de superfície entre células vizinhas.
        desenho = eixo.pcolormesh(matriz.to_numpy(dtype="float64"), cmap=mapa_divergente(),
                                  norm=norma, edgecolors="white", linewidth=0.5)
        centros = np.arange(len(matriz)) + 0.5
        eixo.set(xticks=centros, yticks=centros, title=titulo, aspect="equal")
        eixo.set_xticklabels(matriz.columns, rotation=45, ha="right")
        # Só o primeiro painel rotula o eixo y: repetir invadiria o painel vizinho.
        eixo.set_yticklabels(matriz.index if posicao == 0 else [""] * len(matriz))
        eixo.invert_yaxis()
        eixo.grid(visible=False)
        for i in range(len(matriz)):
            for j in range(len(matriz)):
                valor = matriz.iloc[i, j]
                if valor != valor:
                    continue
                # Texto em tinta, não na cor da série: claro só onde o fundo é escuro.
                tinta = "white" if abs(valor) > 0.6 else estilo.NEUTRO
                eixo.text(j + 0.5, i + 0.5, f"{valor:.2f}".replace(".", ","), ha="center",
                          va="center", fontsize=6, color=tinta)
    barra = figura.colorbar(desenho, ax=eixos, fraction=0.025, pad=0.02)
    barra.set_label("coeficiente", fontsize=7)
    barra.ax.tick_params(labelsize=6)
    # O matplotlib rasteriza a barra de cor por padrão; o PDF do artigo é vetorial.
    if barra.solids is not None:
        barra.solids.set_rasterized(False)
    # Amostra pequena pode não ter nenhum par completo: o título diz isso em vez de falhar.
    validos = tamanhos.to_numpy(dtype="float64")
    validos = validos[~np.isnan(validos)]
    legenda = (f"n mínimo por par: {int(validos.min())}" if validos.size
               else "sem nenhum par completo")
    figura.suptitle(f"Correlação entre as métricas DORA ({legenda})", fontsize=8, y=1.02)
    return estilo.salvar(figura, saida, "artigo_correlacao")


def figura_dispersao(quadro, saida):
    """Frequência de deploy × as duas variantes do CFR, com ρ e r anotados."""
    plt = estilo.aplicar()
    figura, eixos = plt.subplots(1, 2, figsize=(estilo.LARGURA, 2.7))
    pares = (("change_failure_rate", "CFR (a) proxy de CI"),
             ("delivery_change_failure_rate", "CFR (b) proxy de entrega"))
    for eixo, (coluna, rotulo) in zip(eixos, pares):
        par = quadro.loc[:, ["releases_per_week", coluna]].dropna()
        eixo.scatter(par["releases_per_week"], par[coluna], s=9, alpha=0.55,
                     color=estilo.NIVEIS["High"], edgecolors="none")
        # Série constante não tem correlação definida: sem isso o scipy avisa e devolve NaN.
        if len(par) >= 3 and par.nunique().min() >= 2:
            rho = spearmanr(par["releases_per_week"], par[coluna])[0]
            r = pearsonr(par["releases_per_week"], par[coluna])[0]
            eixo.annotate(f"ρ = {comum.numero(rho)}   r = {comum.numero(r)}\nn = {len(par)}",
                          xy=(0.03, 0.97), xycoords="axes fraction", va="top", fontsize=7,
                          color=estilo.NEUTRO)
        eixo.set(xscale="symlog", xlabel="releases por semana (symlog)", ylabel=rotulo,
                 ylim=(-0.03, 1.03))
    figura.tight_layout()
    return estilo.salvar(figura, saida, "artigo_dispersao_df_cfr")


def executar(dados, saida="resultados"):
    """Gera as figuras e a tabela de correlação da seção de Resultados."""
    saida = Path(saida)
    quadro = dados.repositorios
    tabela = tabela_correlacao(quadro)
    comum.salvar_tabela(tabela, saida, "artigo_correlacao", casas=3)
    figuras = [figura_violino(quadro, saida), figura_correlacao(quadro, saida),
               figura_dispersao(quadro, saida), figura_rq06(quadro, saida),
               figura_rq07(dados, saida), figura_rq08(quadro, saida)]
    resultado = {"correlacoes": tabela, "figuras": [caminho.name for caminho in figuras]}
    comum.salvar_json(resultado, saida, "artigo_figuras")
    return resultado


# ------------------------------------------------ RQ 06, RQ 07 e RQ 08: figuras próprias

# Linguagens com amostra suficiente para um boxplot honesto.
LINGUAGENS = 5
NIVEIS_ORDEM = (rating.ELITE, rating.HIGH, rating.MEDIUM, rating.LOW)


def quartis_de(serie):
    """Rótulo do quartil de cada valor, para estratificar um fator numérico."""
    valores = comum.serie_numerica(serie)
    cortes = valores.quantile([0.25, 0.5, 0.75]).to_list()
    def rotular(valor):
        if valor != valor:
            return None
        return "Q1" if valor <= cortes[0] else ("Q2" if valor <= cortes[1]
                                                else ("Q3" if valor <= cortes[2] else "Q4"))
    return valores.map(rotular)


def caixas_por_grupo(eixo, quadro, coluna_grupo, coluna_valor, ordem, cor):
    """Boxplots de uma métrica por grupo, em escala log, com o n de cada grupo no rótulo."""
    amostras, rotulos = [], []
    for grupo in ordem:
        valores = comum.serie_numerica(quadro.loc[quadro[coluna_grupo] == grupo, coluna_valor])
        valores = valores.dropna()
        valores = valores[valores > 0]
        if valores.empty:
            continue
        amostras.append(np.log10(valores).to_numpy())
        rotulos.append(f"{grupo}\nn={valores.size}")
    if not amostras:
        eixo.set_axis_off()
        return eixo
    desenho = eixo.boxplot(amostras, tick_labels=rotulos, patch_artist=True, widths=0.6,
                           medianprops={"color": "black", "linewidth": 1.1},
                           flierprops={"marker": ".", "markersize": 2.5, "alpha": 0.45})
    for caixa in desenho["boxes"]:
        caixa.set(facecolor=cor, alpha=0.45, edgecolor=cor, linewidth=0.9)
    limites = range(int(np.floor(min(a.min() for a in amostras))),
                    int(np.ceil(max(a.max() for a in amostras))) + 1)
    eixo.set_yticks(list(limites))
    eixo.set_yticklabels([f"$10^{{{e}}}$" for e in limites])
    eixo.grid(axis="x", visible=False)
    return eixo


def figura_rq06(quadro, saida):
    """RQ 06: lead time (a) por linguagem e por quartil de contribuidores."""
    plt = estilo.aplicar()
    dados = quadro.copy()
    dados["quartil"] = quartis_de(dados["contributors"])
    principais = (dados["language"].value_counts().head(LINGUAGENS).index.tolist())
    figura, (esquerda, direita) = plt.subplots(1, 2, figsize=(estilo.LARGURA, 3.0))
    caixas_por_grupo(esquerda, dados, "language", "release_lead_time_hours", principais,
                     estilo.NIVEIS["High"])
    esquerda.set(ylabel="lead time (a), horas (log)",
                 title="Por linguagem principal ($\\varepsilon^2 = 0{,}164$)")
    caixas_por_grupo(direita, dados, "quartil", "release_lead_time_hours",
                     ("Q1", "Q2", "Q3", "Q4"), estilo.NIVEIS["Medium"])
    direita.set(xlabel="quartis de contribuidores, do menor ao maior",
                title="Por número de contribuidores ($\\varepsilon^2 = 0{,}100$)")
    figura.tight_layout()
    return estilo.salvar(figura, saida, "artigo_rq06_fatores")


def classificar_em(base, quadro, lead_time, cfr):
    """Categoria geral sob um par de variantes, partindo da classificação C1 autoritativa.

    A frequência, o CFR (a) e a recuperação vêm de `classificacao_c1`, e não das colunas
    cruas: a recuperação de um repositório sem episódio recuperado é classificada pelo
    limite inferior dos censurados, que a coluna sozinha não reproduz. É a mesma fonte
    que a RQ 07 usa, de modo que a matriz bate com a tabela de sensibilidade.
    """
    niveis = []
    for (_, referencia), (_, linha) in zip(base.iterrows(), quadro.iterrows()):
        atual = {
            "deployment_frequency": referencia["deployment_frequency_level"],
            "lead_time": (referencia["lead_time_level"] if lead_time == "a"
                          else c1.nivel("lead_time", linha["commit_lead_time_hours"])),
            "change_failure_rate": (referencia["change_failure_rate_level"] if cfr == "a"
                                    else c1.nivel("change_failure_rate",
                                                  linha["delivery_change_failure_rate"])),
            "recovery_time": referencia["recovery_time_level"]}
        atual = {chave: (None if pd.isna(nivel) else nivel) for chave, nivel in atual.items()}
        niveis.append(rating.overall_classification(
            [atual[nome] for nome in rating.METRICS])["overall"])
    return pd.Series(niveis, index=quadro.index)


def figura_rq07(dados, saida):
    """RQ 07: matriz de transição C1 -> C4, isolando o efeito da variante da métrica."""
    plt = estilo.aplicar()
    quadro = dados.repositorios
    base = c1.classificar(dados)
    de = classificar_em(base, quadro, "a", "a")
    para = classificar_em(base, quadro, "b", "b")
    matriz = pd.crosstab(de, para).reindex(index=NIVEIS_ORDEM, columns=NIVEIS_ORDEM,
                                           fill_value=0)
    figura, eixo = plt.subplots(figsize=(estilo.LARGURA / 1.7, 3.0))
    # Contagem é magnitude: rampa sequencial de um matiz, do claro ao escuro.
    rampa = LinearSegmentedColormap.from_list(
        "contagem", ["#f2f6fc", estilo.NIVEIS["Medium"], estilo.NIVEIS["Elite"]])
    valores = matriz.to_numpy(dtype="float64")
    eixo.pcolormesh(valores, cmap=rampa, edgecolors="white", linewidth=1.0,
                    vmin=0, vmax=max(valores.max(), 1))
    centros = np.arange(len(NIVEIS_ORDEM)) + 0.5
    eixo.set(xticks=centros, yticks=centros, aspect="equal",
             xlabel="categoria na C4 (variantes b)", ylabel="categoria na C1 (variantes a)")
    eixo.set_xticklabels(NIVEIS_ORDEM)
    eixo.set_yticklabels(NIVEIS_ORDEM)
    eixo.invert_yaxis()
    eixo.grid(visible=False)
    for i in range(len(NIVEIS_ORDEM)):
        for j in range(len(NIVEIS_ORDEM)):
            contagem = int(valores[i, j])
            if not contagem:
                continue
            tinta = "white" if contagem > valores.max() * 0.55 else estilo.NEUTRO
            eixo.text(j + 0.5, i + 0.5, str(contagem), ha="center", va="center",
                      fontsize=8, color=tinta,
                      fontweight="bold" if i == j else "normal")
    mudaram = int(valores.sum() - np.trace(valores))
    eixo.set_title(f"{mudaram} de {int(valores.sum())} mudam de categoria "
                   f"({mudaram / max(valores.sum(), 1):.1%})")
    figura.tight_layout()
    return estilo.salvar(figura, saida, "artigo_rq07_transicao")


def figura_rq08(quadro, saida):
    """RQ 08: retrabalho contra a taxa de falha (b) e por categoria geral."""
    plt = estilo.aplicar()
    figura, (esquerda, direita) = plt.subplots(1, 2, figsize=(estilo.LARGURA, 2.8))
    par = quadro.loc[:, ["rework_rate", "delivery_change_failure_rate"]].dropna()
    esquerda.scatter(par["delivery_change_failure_rate"], par["rework_rate"], s=9, alpha=0.55,
                     color=estilo.NIVEIS["High"], edgecolors="none")
    if len(par) >= 3 and par.nunique().min() >= 2:
        rho = spearmanr(par.iloc[:, 1], par.iloc[:, 0])[0]
        r = pearsonr(par.iloc[:, 1], par.iloc[:, 0])[0]
        esquerda.annotate(f"ρ = {comum.numero(rho)}   r = {comum.numero(r)}\nn = {len(par)}",
                          xy=(0.03, 0.97), xycoords="axes fraction", va="top", fontsize=7,
                          color=estilo.NEUTRO)
    esquerda.set(xlabel="taxa de falha (b) de entrega", ylabel="taxa de retrabalho",
                 xlim=(-0.03, 1.03), ylim=(-0.03, 1.03), title="Retrabalho × falha de entrega")
    amostras, rotulos, cores = [], [], []
    for nivel_ in NIVEIS_ORDEM:
        valores = comum.serie_numerica(
            quadro.loc[quadro["overall"] == nivel_, "rework_rate"]).dropna()
        if valores.empty:
            continue
        amostras.append(valores.to_numpy())
        rotulos.append(f"{nivel_}\nn={valores.size}")
        cores.append(estilo.NIVEIS[nivel_])
    if amostras:
        estilo.caixa(direita, amostras, rotulos, cores)
    direita.set(ylabel="taxa de retrabalho", ylim=(-0.03, 1.03),
                title="Retrabalho por categoria DORA")
    direita.grid(axis="x", visible=False)
    figura.tight_layout()
    return estilo.salvar(figura, saida, "artigo_rq08_rework")
