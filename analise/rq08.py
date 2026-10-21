"""RQ 08 (bônus): rework rate, a proporção de releases corretivas.

A *deployment rework rate* que o DORA acrescentou em 2024 é a proporção de entregas não
planejadas, feitas para corrigir problemas. Aqui ela é `releases corretivas / releases
avaliadas` por repositório, com a heurística `v1` da RQ 03 (b).

O que a separa do CFR (b), e por isso o centro da discussão:

- o CFR (b) marca a release que **falhou**: a que foi seguida por uma corretiva em até 7
  dias. O rework rate marca **a própria correção**, sem limite de tempo;
- o CFR (b) censura as releases dos últimos 7 dias da janela; o rework rate não censura;
- uma corretiva pode ser a "próxima release" de várias releases recentes da mesma linha,
  então o CFR (b) pode contar mais falhas do que o rework rate conta correções;
- a primeira release da história não tem release anterior para corrigir e fica fora do
  denominador do rework rate.

A fonte é `releases.csv` (uma linha por release, com `corrective` e `comparison_status`).
Sem o veredito por release, usa as colunas `rework_*` de `repositorios.csv`. Nenhuma
ausência vira zero.
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from . import comum, estilo, rq01_04, rq05


HEURISTICA = Path("validacao/resultados/heuristica")
ALPHA = 0.05
MAIORES_DIVERGENCIAS = 10
SEM_ANTERIOR = "no_previous_release"


def veredito_por_release(releases):
    """Releases datadas com veredito da heurística, separando a primeira da história."""
    quadro = releases[releases["published_at"].notna() & releases["corrective"].notna()].copy()
    quadro["sem_anterior"] = quadro["comparison_status"].eq(SEM_ANTERIOR).fillna(False).astype(bool)
    quadro["corretiva"] = quadro["corrective"].astype(bool)
    return quadro


def por_repositorio(dados):
    """Rework rate por repositório, com o denominador e a origem do número.

    Devolve `(quadro, origem)`. `origem` é `releases.csv`, `repositorios.csv` (quando a
    tabela de releases não traz o veredito) ou `indisponivel`.
    """
    base = dados.repositorios
    if base["repository"].isna().any() or base["repository"].duplicated().any():
        raise ValueError("RQ 08: repositorios.csv deve ter um identificador único por repositório.")
    quadro = base[["repository"]].copy()
    veredito = veredito_por_release(dados.releases)
    if not veredito.empty:
        avaliadas = veredito[~veredito["sem_anterior"]]
        contagem = avaliadas.groupby("repository", dropna=False).agg(
            avaliadas=("corretiva", "size"), corretivas=("corretiva", "sum"))
        sem_anterior = veredito.groupby("repository", dropna=False)["sem_anterior"].sum().rename("sem_anterior")
        quadro = quadro.merge(contagem, left_on="repository", right_index=True, how="left").merge(
            sem_anterior, left_on="repository", right_index=True, how="left")
        origem = "releases.csv"
    elif base[["rework_rate", "rework_evaluated"]].notna().any().any():
        quadro["avaliadas"] = comum.serie_numerica(base["rework_evaluated"])
        quadro["corretivas"] = comum.serie_numerica(base["rework_corrective"])
        quadro["sem_anterior"] = comum.serie_numerica(base["rework_no_previous"])
        origem = "repositorios.csv"
    else:
        for coluna in ("avaliadas", "corretivas", "sem_anterior"):
            quadro[coluna] = np.nan
        origem = "indisponivel"
    quadro["avaliadas"] = comum.serie_numerica(quadro["avaliadas"])
    quadro["corretivas"] = comum.serie_numerica(quadro["corretivas"])
    quadro["sem_anterior"] = comum.serie_numerica(quadro["sem_anterior"])
    # Sem nenhuma release avaliável a taxa é indefinida, não zero.
    quadro["rework_rate"] = quadro["corretivas"] / quadro["avaliadas"].where(quadro["avaliadas"] > 0)
    return quadro.reset_index(drop=True), origem


def conferir_com_csv(quadro, dados):
    """Compara a taxa recalculada com a coluna `rework_rate` do pipeline, quando existe."""
    gravada = comum.serie_numerica(dados.repositorios["rework_rate"])
    if not gravada.notna().any():
        return {"verificavel": False, "divergentes": []}
    gravada.index = dados.repositorios["repository"]
    recalculada = quadro.set_index("repository")["rework_rate"]
    juntas = pd.concat([gravada.rename("gravada"), recalculada.rename("recalculada")], axis=1)
    dif = ~np.isclose(juntas["gravada"], juntas["recalculada"], equal_nan=True, atol=1e-9)
    return {"verificavel": True, "divergentes": sorted(map(str, juntas.index[dif]))}


def cfr_b_por_repositorio(dados):
    """CFR (b) e suas contagens, da mesma fonte da RQ 05; nunca zero por falta de veredito."""
    cfr, origem = rq05.por_repositorio(dados)
    quadro = cfr[["repository", "cfr_b"]].copy()
    contagens = rq01_04.cfr_entrega_por_repositorio(dados.releases)
    if not contagens.empty:
        quadro = quadro.merge(contagens[["repository", "avaliadas", "falhas", "censuradas"]].rename(
            columns={"avaliadas": "cfr_b_avaliadas", "falhas": "cfr_b_falhas",
                     "censuradas": "cfr_b_censuradas"}), on="repository", how="left")
    else:
        base = dados.repositorios
        quadro["cfr_b_avaliadas"] = comum.serie_numerica(base["cfr_b_evaluated"]).to_numpy()
        quadro["cfr_b_falhas"] = comum.serie_numerica(base["cfr_b_failed"]).to_numpy()
        quadro["cfr_b_censuradas"] = comum.serie_numerica(base["cfr_b_censored"]).to_numpy()
    return quadro, origem


def correlacao(rework, cfr_b):
    """Spearman entre rework rate e CFR (b), um par por repositório, sem imputação."""
    pares = pd.concat([comum.serie_numerica(rework).rename("rework"),
                       comum.serie_numerica(cfr_b).rename("cfr_b")], axis=1).dropna()
    if ((pares < 0) | (pares > 1)).any().any():
        raise ValueError("RQ 08: as taxas devem estar entre 0 e 1.")
    rho, p = float("nan"), float("nan")
    if len(pares) < 2:
        motivo = "menos de dois pares"
    elif (pares.nunique() < 2).any():
        motivo = "variável constante"
    else:
        teste = spearmanr(pares["rework"], pares["cfr_b"], alternative="two-sided")
        rho, p = float(teste.statistic), float(teste.pvalue)
        motivo = "ok" if math.isfinite(p) else "p-valor indefinido"
    return {"n": len(pares), "rho": rho, "p": p, "forca": rq05.interpretar_forca(rho), "motivo": motivo}


def divergencias(quadro, quantas=MAIORES_DIVERGENCIAS):
    """Os repositórios em que rework rate e CFR (b) mais se afastam, com as contagens."""
    colunas = ["repository", "rework_rate", "cfr_b", "diferenca", "avaliadas", "corretivas",
               "cfr_b_avaliadas", "cfr_b_falhas", "cfr_b_censuradas", "leitura"]
    ambos = quadro.dropna(subset=["rework_rate", "cfr_b"]).copy()
    if ambos.empty:
        return pd.DataFrame(columns=colunas)
    ambos["diferenca"] = ambos["rework_rate"] - ambos["cfr_b"]
    ambos["distancia"] = ambos["diferenca"].abs()
    ambos["leitura"] = np.where(ambos["diferenca"] >= 0, "mais retrabalho que falha",
                                "mais falha que retrabalho")
    ordenado = ambos.sort_values(["distancia", "repository"], ascending=[False, True])
    return ordenado.head(quantas).loc[:, colunas].reset_index(drop=True)


def totais(quadro):
    """Taxas agregadas (todas as releases juntas) e a reconciliação com o CFR (b)."""
    avaliadas, corretivas = quadro["avaliadas"].sum(), quadro["corretivas"].sum()
    avaliadas_b, falhas = quadro["cfr_b_avaliadas"].sum(), quadro["cfr_b_falhas"].sum()
    return {"releases_avaliadas": int(avaliadas), "corretivas": int(corretivas),
            "taxa_agregada": float(corretivas / avaliadas) if avaliadas else float("nan"),
            "cfr_b_avaliadas": int(avaliadas_b), "cfr_b_falhas": int(falhas),
            "cfr_b_agregado": float(falhas / avaliadas_b) if avaliadas_b else float("nan"),
            "sem_anterior": int(quadro["sem_anterior"].sum()),
            "repositorios_sem_taxa": int(quadro["rework_rate"].isna().sum())}


def avaliacao_da_heuristica(raiz=HEURISTICA):
    """Precisão e recall da versão avaliada da heurística; None se o resultado não existe."""
    arquivos = sorted(Path(raiz).glob("v1-*/resultado.json"))
    if not arquivos:
        return None
    try:
        avaliacao = json.loads(arquivos[-1].read_text(encoding="utf-8"))
        precisao, recall = float(avaliacao["precision"]), float(avaliacao["recall"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not (0 < precisao <= 1 and 0 < recall <= 1):
        return None
    return {"versao": avaliacao.get("version", "v1"), "precisao": precisao, "recall": recall,
            "f1": float(avaliacao.get("f1", 2 * precisao * recall / (precisao + recall)))}


def ajustar_pela_heuristica(taxa, avaliacao):
    """Taxa agregada corrigida por precisão e recall: TP = observado × P, total real = TP / R.

    É uma ordem de grandeza, não uma correção exata: supõe que precisão e recall medidos na
    amostra-ouro valem para todas as releases.
    """
    if avaliacao is None or not math.isfinite(taxa):
        return float("nan")
    return min(1.0, taxa * avaliacao["precisao"] / avaliacao["recall"])


def figura_distribuicao(taxas, saida):
    """Histograma do rework rate por repositório, com a mediana marcada."""
    plt = estilo.aplicar()
    figura, eixo = plt.subplots(figsize=estilo.TAMANHO_SIMPLES)
    validas = comum.serie_numerica(taxas).dropna()
    if validas.empty:
        eixo.text(0.5, 0.5, "sem repositórios com\nrework rate definido", ha="center", va="center",
                  transform=eixo.transAxes)
    else:
        eixo.hist(validas, bins=np.linspace(0, 1, 11), color=estilo.VARIANTE_B, alpha=0.75,
                  edgecolor="white", linewidth=0.5)
        eixo.axvline(validas.median(), color="black", linewidth=1.0, linestyle="--",
                     label=f"mediana = {comum.numero(validas.median(), 2)}")
        eixo.legend(frameon=False)
    eixo.set(xlabel="rework rate (proporção de releases corretivas)", ylabel="repositórios",
             xlim=(0, 1))
    estilo.contagem_inteira(eixo)
    figura.tight_layout()
    return estilo.salvar(figura, saida, "rq08_distribuicao")


def figura_dispersao(quadro, teste, saida):
    """Rework rate × CFR (b), um ponto por repositório, com a reta rework = CFR (b)."""
    plt = estilo.aplicar()
    figura, eixo = plt.subplots(figsize=estilo.TAMANHO_SIMPLES)
    pares = quadro.dropna(subset=["rework_rate", "cfr_b"])
    eixo.plot((0, 1), (0, 1), color=estilo.REFERENCIA, linestyle="--", linewidth=0.8, zorder=0,
              label="rework rate = CFR (b)")
    eixo.scatter(pares["cfr_b"], pares["rework_rate"], s=12, alpha=0.6, edgecolors="none",
                 color=estilo.VARIANTE_B, clip_on=False)
    eixo.set(xlabel="CFR (b), proporção", ylabel="rework rate, proporção", xlim=(0, 1), ylim=(0, 1))
    rho = comum.numero(teste["rho"], 3) if math.isfinite(teste["rho"]) else "indefinido"
    p = format(teste["p"], ".3g").replace(".", ",") if math.isfinite(teste["p"]) else "indefinido"
    eixo.set_title(f"Rework rate × CFR (b)\nρ = {rho}; p = {p}; n = {teste['n']}")
    eixo.legend(frameon=False, loc="upper left")
    figura.tight_layout()
    return estilo.salvar(figura, saida, "rq08_rework_cfr_b")


def leitura_correlacao(teste):
    """Descrição da associação, sem causalidade: as duas métricas partem da mesma heurística."""
    if not math.isfinite(teste["rho"]):
        return f"A correlação é indefinida nesta amostra ({teste['motivo']})."
    sinal = "positiva" if teste["rho"] > 0 else "negativa"
    forca = teste["forca"]
    significancia = ("distinguível de zero" if teste["p"] < ALPHA
                     else "não distinguível de zero")
    return (f"A associação é {sinal} e {forca} (ρ = {comum.numero(teste['rho'], 3)}; "
            f"{significancia} ao nível de 5%, sem ajuste por multiplicidade). Como as duas "
            "métricas saem da mesma heurística aplicada às mesmas releases, parte dessa associação "
            "é construção, e não evidência independente sobre a qualidade das entregas.")


def notas(resumo_rework, resumo_cfr, soma, teste, avaliacao, ajustada, origem, conferencia):
    """Rascunho da seção: definição, diferença para o CFR (b), correlação e confiança."""
    numero = comum.numero
    blocos = [
        "# RQ 08 (bônus) — Rework rate",
        comum.paragrafo(
            "O rework rate é a proporção de releases corretivas entre as releases avaliadas de "
            "cada repositório, com a heurística `v1` da RQ 03 (b). Entre os "
            f"{resumo_rework['n']} repositórios com taxa definida, a mediana é "
            f"{numero(resumo_rework['mediana'], 3)} (IQR {numero(resumo_rework['iqr'], 3)}; "
            f"Q1 = {numero(resumo_rework['q1'], 3)}; Q3 = {numero(resumo_rework['q3'], 3)}). "
            f"Somando todas as releases, {soma['corretivas']} de {soma['releases_avaliadas']} "
            f"são corretivas ({numero(soma['taxa_agregada'], 3)}). Fonte: {origem}; a primeira "
            f"release da história de cada repositório ({soma['sem_anterior']} no total) fica fora "
            "do denominador por não ter release anterior para corrigir."),
        "## Em que difere do CFR (b)",
        comum.paragrafo(
            "O CFR (b) marca a release que falhou, isto é, a que foi seguida por uma corretiva em "
            "até 7 dias; o rework rate marca a própria correção, sem janela de tempo. Há três "
            "consequências. Primeiro, uma correção publicada depois de mais de 7 dias é retrabalho "
            "para o rework rate e passa despercebida pelo CFR (b). Segundo, o CFR (b) censura as "
            "releases dos últimos 7 dias da janela e o rework rate não censura ninguém. Terceiro, "
            "uma única corretiva pode ser a 'próxima release' de várias releases recentes da mesma "
            "linha, de modo que o CFR (b) pode contar mais falhas do que o rework rate conta "
            f"correções. Nesta amostra o CFR (b) tem mediana {numero(resumo_cfr['mediana'], 3)} "
            f"(IQR {numero(resumo_cfr['iqr'], 3)}; n = {resumo_cfr['n']}), com "
            f"{soma['cfr_b_falhas']} falhas em {soma['cfr_b_avaliadas']} releases avaliadas "
            f"({numero(soma['cfr_b_agregado'], 3)}), contra {soma['corretivas']} corretivas no "
            "rework rate. Os repositórios em que as duas métricas mais se afastam estão em "
            "`resultados/tabelas/rq08_divergencias.csv`."),
        comum.paragrafo(
            f"Entre os {teste['n']} repositórios com as duas métricas, o Spearman entre rework rate "
            f"e CFR (b) é ρ = {numero(teste['rho'], 3)} (p = "
            f"{format(teste['p'], '.3g').replace('.', ',') if math.isfinite(teste['p']) else '--'}). "
            + leitura_correlacao(teste)),
    ]
    if avaliacao is not None:
        blocos += [
            "## Confiança no valor",
            comum.paragrafo(
                f"O rework rate herda os erros da heurística. Na amostra-ouro de 300 releases, a "
                f"versão {avaliacao['versao']} tem precisão {numero(avaliacao['precisao'], 3)}, "
                f"recall {numero(avaliacao['recall'], 3)} e F1 {numero(avaliacao['f1'], 3)}: ela "
                "marca como corretivas mais releases do que o consenso humano (precisão menor que "
                "o recall), então a taxa observada tende a superestimar o retrabalho. Corrigindo a "
                "taxa agregada por P/R, ela cairia de "
                f"{numero(soma['taxa_agregada'], 3)} para cerca de {numero(ajustada, 3)}. É uma "
                "ordem de grandeza, e não uma correção exata, porque supõe que precisão e recall "
                "da amostra-ouro valem para todas as releases; o refinamento da heurística olhou "
                "para a mesma amostra em que ela foi avaliada, o que também infla o F1."),
        ]
    if conferencia["verificavel"] and conferencia["divergentes"]:
        blocos.append(comum.paragrafo(
            f"Atenção: {len(conferencia['divergentes'])} repositório(s) têm `rework_rate` em "
            "`repositorios.csv` diferente do recalculado a partir de `releases.csv`: "
            + ", ".join(conferencia["divergentes"][:5]) + "."))
    return "\n\n".join(blocos) + "\n"


def executar(dados, saida="resultados"):
    """Gera tabelas, duas figuras, o rascunho de texto e o JSON da RQ 08."""
    saida = Path(saida)
    rework, origem = por_repositorio(dados)
    cfr, _ = cfr_b_por_repositorio(dados)
    quadro = rework.merge(cfr, on="repository", how="left")
    conferencia = conferir_com_csv(quadro, dados)
    resumo_rework, resumo_cfr = comum.resumo(quadro["rework_rate"]), comum.resumo(quadro["cfr_b"])
    teste = correlacao(quadro["rework_rate"], quadro["cfr_b"])
    soma = totais(quadro)
    avaliacao = avaliacao_da_heuristica()
    ajustada = ajustar_pela_heuristica(soma["taxa_agregada"], avaliacao)
    divergentes = divergencias(quadro)
    tabela = pd.DataFrame([
        {"metrica": "Rework rate", **{c: resumo_rework[c] for c in ("n", "mediana", "q1", "q3", "iqr")}},
        {"metrica": "CFR (b)", **{c: resumo_cfr[c] for c in ("n", "mediana", "q1", "q3", "iqr")}}])
    comum.salvar_tabela(tabela, saida, "rq08_resumo", casas=3)
    comum.salvar_tabela(pd.DataFrame([{k: teste[k] for k in ("n", "rho", "p", "forca")}]), saida,
                        "rq08_correlacao", casas=4)
    comum.salvar_tabela(divergentes, saida, "rq08_divergencias", casas=3)
    comum.salvar_csv(quadro, saida, "rq08_por_repositorio")
    figuras = [figura_distribuicao(quadro["rework_rate"], saida).name,
               figura_dispersao(quadro, teste, saida).name]
    comum.salvar_texto(notas(resumo_rework, resumo_cfr, soma, teste, avaliacao, ajustada, origem,
                             conferencia), saida, "notas_rq08")
    resultado = {"origem": origem, "resumo_rework_rate": resumo_rework, "resumo_cfr_b": resumo_cfr,
                 "totais": soma, "correlacao": teste, "avaliacao_heuristica": avaliacao,
                 "taxa_agregada_ajustada": ajustada, "conferencia_com_csv": conferencia,
                 "divergencias": divergentes, "figuras": figuras, "por_repositorio": quadro}
    comum.salvar_json(resultado, saida, "rq08")
    return resultado
