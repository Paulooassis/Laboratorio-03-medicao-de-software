"""RQ 05: Spearman entre frequência e CFR, com diagnóstico da janela de sete dias.

As correlações usam um par por repositório, sem imputação. O diagnóstico compara
os quartis extremos de DF e resume os intervalos de cada repositório antes de
comparar os grupos, evitando dar mais peso a quem publica mais releases.
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from . import comum, estilo, rq01_04


ALPHA = 0.05
LINTHRESH = 0.1  # releases/semana; zero permanece no trecho linear do symlog.
SCHOBER = "https://doi.org/10.1213/ANE.0000000000002864"
SCIPY = "https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.stats.spearmanr.html"
DORA = "https://dora.dev/guides/dora-metrics/"
VARIANTES = {"a": "(a) proxy de CI", "b": "(b) proxy de entrega"}


def interpretar_forca(rho):
    """Faixas convencionais de Schober, Boer & Schwarte (2018), sobre |ρ|."""
    if not math.isfinite(rho):
        return "indefinida"
    for limite, rotulo in ((0.1, "desprezível"), (0.4, "fraca"), (0.7, "moderada"), (0.9, "forte")):
        if abs(rho) < limite:
            return rotulo
    return "muito forte"


def pares_validos(df, cfr):
    """Alinha por índice e exclui ausentes par a par; zeros são observações válidas."""
    pares = pd.concat([comum.serie_numerica(df).rename("df"),
                       comum.serie_numerica(cfr).rename("cfr")], axis=1)
    for coluna in pares:
        presentes = pares[coluna].dropna()
        if not np.isfinite(presentes).all() or (presentes < 0).any():
            raise ValueError(f"RQ 05: {coluna} deve conter valores finitos e não negativos.")
    if (pares["cfr"].dropna() > 1).any():
        raise ValueError("RQ 05: CFR deve estar entre 0 e 1.")
    return pares.dropna()


def correlacao(df, cfr):
    """ρ e p bilateral do scipy.stats.spearmanr, com o n efetivo de cada teste."""
    pares = pares_validos(df, cfr)
    rho, p = float("nan"), float("nan")
    if len(pares) < 2:
        motivo = "menos de dois pares"
    elif (pares.nunique() < 2).any():
        motivo = "variável constante"
    else:
        teste = spearmanr(pares["df"], pares["cfr"], alternative="two-sided")
        rho, p = float(teste.statistic), float(teste.pvalue)
        motivo = "ok" if math.isfinite(p) else "p-valor indefinido"
    return {"n": len(pares), "rho": rho, "p": p, "forca": interpretar_forca(rho),
            "motivo": motivo, "zeros_df": int((pares["df"] == 0).sum())}


def por_repositorio(dados):
    """Mesmas métricas das RQ 01/03; veredito incompleto nunca vira zero falha."""
    base = dados.repositorios
    if base["repository"].isna().any() or base["repository"].duplicated().any():
        raise ValueError("RQ 05: repositorios.csv deve ter um identificador único por repositório.")
    quadro = base[["repository"]].copy()
    quadro["df"] = comum.serie_numerica(base["releases_per_week"])
    quadro["cfr_a"] = comum.serie_numerica(base["change_failure_rate"])
    entrega = rq01_04.cfr_entrega_por_repositorio(dados.releases)
    if entrega.empty or not entrega["cfr_entrega"].notna().any():
        quadro["cfr_b"] = comum.serie_numerica(base["delivery_change_failure_rate"])
        origem_b = "repositorios.csv"
    else:
        quadro["cfr_b"] = rq01_04.alinhar(base, entrega, "cfr_entrega")
        origem_b = "releases.csv"
        releases = dados.releases[dados.releases["published_at"].notna()]
        indefinido = releases["censored"].isna() | (
            releases["censored"].eq(False).fillna(False) & releases["failed"].isna())
        incompletos = releases.loc[indefinido, "repository"]
        quadro.loc[quadro["repository"].isin(incompletos), "cfr_b"] = np.nan
    return quadro, origem_b


def intervalos_por_repositorio(releases):
    """Intervalos consecutivos em dias; simultâneos valem zero, a primeira não tem par."""
    colunas = ["repository", "intervalos", "mediana_intervalo_dias", "fracao_intervalos_ate7"]
    datadas = releases.dropna(subset=["repository", "published_at"]).sort_values(
        ["repository", "published_at"])
    linhas = []
    for repository, grupo in datadas.groupby("repository", sort=False):
        intervalos = grupo["published_at"].diff().dt.total_seconds().div(86400).dropna()
        linhas.append({"repository": repository, "intervalos": len(intervalos),
                       "mediana_intervalo_dias": comum.resumo(intervalos)["mediana"],
                       "fracao_intervalos_ate7": float((intervalos <= 7).sum() / len(intervalos))
                       if len(intervalos) else np.nan})
    return pd.DataFrame(linhas, columns=colunas)


def artefato(quadro, releases):
    """Baixa DF ≤ Q1, alta DF ≥ Q3 na amostra válida de DF × CFR (b).

    A tabela compara medianas por repositório, com o mesmo peso para cada projeto.
    Quartis coincidentes tornam o contraste indefinido para evitar grupos sobrepostos.
    """
    completo = quadro.merge(intervalos_por_repositorio(releases), on="repository", how="left")
    pares = pares_validos(completo["df"], completo["cfr_b"])
    amostra = completo.loc[pares.index]
    q1, q3 = (float(amostra["df"].quantile(q)) for q in (0.25, 0.75))
    separavel = math.isfinite(q1) and math.isfinite(q3) and q1 < q3
    grupos, linhas = {}, []
    for grupo, mascara in (("Baixa DF", amostra["df"] <= q1), ("Alta DF", amostra["df"] >= q3)):
        selecionados = amostra[mascara] if separavel else amostra.iloc[:0]
        resumo = comum.resumo(selecionados["mediana_intervalo_dias"])
        linhas.append({"grupo": grupo, "n": resumo["n"], "mediana_dias": resumo["mediana"],
                       "iqr_dias": resumo["iqr"], "fracao_ate7":
                       comum.resumo(selecionados["fracao_intervalos_ate7"])["mediana"]})
        grupos[grupo] = {"repositorios": len(selecionados), "sem_intervalos": resumo["ausentes"]}
    return {"q1_df": q1, "q3_df": q3, "grupos_separaveis": separavel, "grupos": grupos,
            "tabela": pd.DataFrame(linhas), "por_repositorio": completo}


def figura(df, cfr, resultado, variante, saida):
    """Um ponto por par válido; symlog preserva DF = 0 sem pseudocontagem."""
    plt = estilo.aplicar()
    pares = pares_validos(df, cfr)
    fig, eixo = plt.subplots(figsize=estilo.TAMANHO_SIMPLES)
    eixo.scatter(pares["df"], pares["cfr"], s=12, alpha=0.7, edgecolors="none",
                 color=estilo.VARIANTE_A if variante == "a" else estilo.VARIANTE_B, clip_on=False)
    eixo.set_xscale("symlog", base=10, linthresh=LINTHRESH)
    eixo.set(xlabel="DF, releases/semana (symlog)", ylabel="CFR, proporção",
             ylim=(0, 1),
             xlim=(0, max(LINTHRESH, float(pares["df"].max()) * 1.1) if len(pares) else 1))
    p = f"{resultado['p']:.3g}" if math.isfinite(resultado["p"]) else "indefinido"
    rho = f"{resultado['rho']:.3f}" if math.isfinite(resultado["rho"]) else "indefinido"
    eixo.set_title(f"DF × CFR {VARIANTES[variante]}\nρ = {rho}; p = {p}; n = {resultado['n']}")
    fig.tight_layout()
    return estilo.salvar(fig, saida, f"rq05_df_cfr_{variante}")


def leitura_dora(teste):
    """Interpretação condicional; ausência de significância não comprova ausência de associação."""
    if not math.isfinite(teste["rho"]) or not math.isfinite(teste["p"]):
        return ("O teste é indefinido nesta amostra e não permite avaliar a afirmação do DORA "
                f"({teste['motivo']}).")
    if teste["p"] >= ALPHA:
        return ("Não há evidência estatística de associação monotônica ao nível de 5%; "
                "isso não confirma nem refuta o DORA, nem demonstra independência.")
    if teste["rho"] < 0:
        return ("A associação negativa é compatível com a afirmação do DORA: maior frequência "
                "acompanha menor CFR nesta amostra, sem demonstrar uma relação causal.")
    return ("A associação positiva apresenta uma tensão aparente com a afirmação do DORA: "
            "maior frequência acompanha maior CFR nesta amostra. As proxies e o mecanismo "
            "de medição impedem tratar isso como uma refutação direta do DORA.")


def p_texto(p):
    """Preserva p pequeno em notação científica, sem arredondá-lo para zero no artigo."""
    return format(p, ".6g").replace(".", ",") if math.isfinite(p) else "--"


def discussao(testes, diagnostico, origem_b):
    """Rascunho preenchido somente com estatísticas calculadas dos CSVs de entrada."""
    paragrafos = ["# RQ 05 — Frequência de deploy e estabilidade", "",
        "A unidade de análise é o repositório. Cada variante exclui ausentes par a par; "
        f"o CFR (b) foi obtido de {origem_b}, segundo a agregação da RQ 03. "
        "Os p-valores são bilaterais, sem ajuste por multiplicidade, e exploratórios."]
    for variante, teste in testes.items():
        p = p_texto(teste["p"])
        paragrafos += ["", comum.paragrafo(
            f"Na variante {VARIANTES[variante]}, ρ = {comum.numero(teste['rho'], 4)}, "
            f"p = {p} e n = {teste['n']}; a força da associação é {teste['forca']}. "
            + leitura_dora(teste))]
    paragrafos += ["", comum.paragrafo(
        "A força usa |ρ|, sem arredondamento prévio: desprezível [0; 0,10), fraca [0,10; 0,40), "
        "moderada [0,40; 0,70), forte [0,70; 0,90) e muito forte [0,90; 1]. "
        f"São as faixas convencionais apresentadas por [Schober, Boer e Schwarte (2018)]({SCHOBER}), "
        "usadas como descrição, não como limites universais ou como teste de significância."),
        "", "## Diagnóstico do artefato do CFR (b)", ""]
    tabela = diagnostico["tabela"].set_index("grupo")
    baixa, alta = tabela.loc["Baixa DF"], tabela.loc["Alta DF"]
    paragrafos += [comum.paragrafo(
        f"Na amostra válida de DF × CFR (b), o grupo de baixa frequência inclui DF ≤ "
        f"{comum.numero(diagnostico['q1_df'], 4)} releases/semana (Q1), e o de alta frequência "
        f"DF ≥ {comum.numero(diagnostico['q3_df'], 4)} (Q3). Ordenamos as datas de publicação "
        "dentro de cada repositório e calculamos os intervalos consecutivos, incluindo "
        "intervalos nulos de releases simultâneas. Primeiro resumimos cada repositório; "
        "depois comparamos as medianas desses resumos, sem ponderar pelo número de releases.")]
    if diagnostico["grupos_separaveis"] and baixa["n"] and alta["n"]:
        paragrafos += ["", comum.paragrafo(
            f"O intervalo mediano por repositório tem mediana {comum.numero(baixa['mediana_dias'])} "
            f"dias (IQR {comum.numero(baixa['iqr_dias'])}; n = {int(baixa['n'])}) na baixa DF e "
            f"{comum.numero(alta['mediana_dias'])} dias (IQR {comum.numero(alta['iqr_dias'])}; "
            f"n = {int(alta['n'])}) na alta DF. A mediana da fração de intervalos de até sete "
            f"dias é {comum.numero(baixa['fracao_ate7'])} e {comum.numero(alta['fracao_ate7'])}, "
            "respectivamente.")]
        if alta["mediana_dias"] < baixa["mediana_dias"] and alta["fracao_ate7"] > baixa["fracao_ate7"]:
            achado = ("O grupo de alta DF apresenta intervalos menores e maior fração dentro de sete "
                      "dias, padrão compatível com mais oportunidades de a heurística marcar falha.")
        else:
            achado = ("Os dois indicadores não apresentam conjuntamente o padrão esperado de mais "
                      "oportunidades na alta DF; este diagnóstico não descarta o artefato.")
    else:
        achado = ("Não foi possível comparar os grupos: os quartis coincidem ou não há intervalos "
                  "válidos em um deles. Sem duas releases datadas, o intervalo fica ausente, nunca zero.")
    paragrafos += ["", comum.paragrafo(achado + " O CFR (b) procura uma corretiva em até sete dias; "
        "mais publicações podem aumentar a chance de encontrar uma, mesmo sem piora de qualidade. "
        "DF e intervalos também derivam das mesmas datas, portanto este contraste é um diagnóstico "
        "descritivo e não estima qual parcela da correlação decorre da construção da métrica. "
        "Os intervalos consideram todas as releases do repositório, sem controlar linhas de versão."),
        "", "## Limites e relação com o DORA", "", comum.paragrafo(
        f"O [DORA]({DORA}) sustenta que velocidade e estabilidade podem melhorar juntas. "
        "Correlação não implica causalidade: composição dos projetos, tamanho e práticas de entrega "
        "podem explicar associações. O CFR (a) mede falha de pipeline, não falha em produção; "
        "o CFR (b) é uma proxy baseada em releases e corretivas. A comparação com o DORA é, "
        "portanto, limitada por essas diferenças de medição."), "", comum.paragrafo(
        "Os p-valores são os retornados por [scipy.stats.spearmanr][scipy-spearman]. A documentação "
        "ressalta a aproximação em amostras pequenas (até 500 observações); a inferência nesta "
        "amostra deve ser tratada como exploratória. Nos gráficos, DF usa symlog de base 10, "
        f"com trecho linear entre 0 e {comum.numero(LINTHRESH, 1)} releases/semana e log acima desse limiar; "
        "zeros permanecem no cálculo e na figura, sem somar constantes. CFR usa eixo de 0 a 1."),
        "", f"[scipy-spearman]: {SCIPY}"]
    return "\n".join(paragrafos)


def executar(dados, saida):
    """Gera tabelas, duas dispersões vetoriais e discussão com os dados da RQ 05."""
    saida = Path(saida)
    quadro, origem_b = por_repositorio(dados)
    testes = {variante: correlacao(quadro["df"], quadro[f"cfr_{variante}"]) for variante in VARIANTES}
    tabela = pd.DataFrame([{"variante": VARIANTES[variante],
                            **{campo: teste[campo] for campo in ("n", "rho", "p", "forca")}}
                           for variante, teste in testes.items()])
    diagnostico = artefato(quadro, dados.releases)
    _, tex = comum.salvar_tabela(tabela, saida, "rq05_correlacoes", casas=6)
    tex.write_text(comum.tabela_latex(tabela.assign(p=tabela["p"].map(p_texto)), casas=6), encoding="utf-8")
    comum.salvar_tabela(diagnostico["tabela"], saida, "rq05_artefato_cfr_b", casas=4)
    comum.salvar_csv(diagnostico["por_repositorio"], saida, "rq05_por_repositorio")
    for variante, teste in testes.items():
        figura(quadro["df"], quadro[f"cfr_{variante}"], teste, variante, saida)
    comum.salvar_texto(discussao(testes, diagnostico, origem_b), saida, "notas_rq05")
    resultado = {"diretorio_dados": str(dados.diretorio), "origem_cfr_b": origem_b,
                 "testes": testes, "correlacoes": tabela,
                 "artefato": {chave: valor for chave, valor in diagnostico.items() if chave != "por_repositorio"}}
    comum.salvar_json(resultado, saida, "rq05")
    return resultado
