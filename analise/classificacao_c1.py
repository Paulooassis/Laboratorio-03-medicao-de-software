"""C1: a classificação DORA de referência, reproduzida a partir do CSV.

A combinação C1 é o ponto de comparação da análise de sensibilidade (RQ 07) e o
resultado que resume as RQ 01 a 04 no artigo:

| Métrica | Definição na C1 |
| --- | --- |
| Deployment Frequency | deployment = release publicada, em releases por semana |
| Lead Time | variante **(a) por release**: do commit mais antigo do intervalo até a publicação |
| Change Failure Rate | variante **(a) proxy de CI**: falhas sobre workflow runs considerados |
| Tempo de recuperação | da primeira falha ao primeiro sucesso do mesmo workflow |

As faixas vêm de `dora_selection.rating`, que implementa a tabela de referência do
enunciado: a análise não reescreve os limites, para que exista uma definição só no
repositório. O que este módulo faz é recalcular os níveis **a partir das colunas do
CSV** e conferir que batem com o que o pipeline gravou — é essa conferência que mostra
que a classificação é reproduzível sem refazer a coleta.

Duas decisões ficam explícitas aqui, em vez de implícitas no código do pipeline:

1. **Fallback do Lead Time.** `lead_time_rating` usa a variante (a) e, na falta dela,
   cai para a (b) por commit. Um repositório classificado assim não está, a rigor, na
   C1. O módulo calcula as duas leituras lado a lado — `lead_time_level` (C1 estrita,
   só com a variante (a)) e `lead_time_level_com_fallback` (a regra do pipeline) — e
   conta quantos repositórios mudam de nível geral entre as duas, para que a escolha
   seja registrada no artigo com números.
2. **Métrica sem classificação.** O nível geral é a mediana das notas das métricas
   *disponíveis*, arredondada para baixo; o repositório só fica sem nível geral quando
   nenhuma das quatro foi classificada. Nenhuma métrica ausente vira zero ou Elite por
   omissão. A cobertura por repositório vai para a tabela de cobertura.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from dora_selection import rating

from . import comum, estilo


SEM_CLASSIFICACAO = "Sem classificação"
NIVEIS = (*rating.LEVELS, SEM_CLASSIFICACAO)
# Coluna do CSV que alimenta cada métrica da C1.
VALORES = {"deployment_frequency": "releases_per_week",
           "lead_time": "release_lead_time_hours",
           "change_failure_rate": "change_failure_rate",
           "recovery_time": "recovery_hours"}
# Nome da métrica no artigo, na ordem da tabela de referência.
ROTULOS = {"deployment_frequency": "Deployment Frequency",
           "lead_time": "Lead Time (a) por release",
           "change_failure_rate": "Change Failure Rate (a) proxy de CI",
           "recovery_time": "Tempo de recuperação",
           "overall": "Classificação geral (C1)"}
# O que é comparado com o pipeline: a coluna recalculada e a coluna gravada.
CONFERENCIA = (("deployment_frequency_level", "deployment_frequency_level"),
               ("lead_time_level_com_fallback", "lead_time_level"),
               ("change_failure_rate_level", "change_failure_rate_level"),
               ("recovery_time_level", "recovery_time_level"),
               ("overall_com_fallback", "overall"))


def nivel(metrica, valor):
    """Nível DORA de um valor do CSV; ausente continua ausente, nunca vira Low."""
    return rating.SCALES[metrica].level(valor)


def limite_dos_censurados(episodios):
    """Mediana do tempo observado dos episódios censurados, por repositório.

    É o limite inferior que `recovery_time_rating` usa quando o repositório não tem
    nenhum episódio recuperado: sozinho ele não mede a recuperação, mas já basta para
    Low quando passa de uma semana.
    """
    if episodios.empty:
        return pd.Series(dtype="float64")
    censurados = episodios[comum.para_booleano(episodios["censored"]).fillna(False)]
    return censurados.groupby("repository", dropna=False)["observed_hours"].median()


def classificar_repositorio(linha, limite=np.nan):
    """Níveis das quatro métricas da C1 e o nível geral de um repositório."""
    niveis = {metrica: nivel(metrica, linha[coluna]) for metrica, coluna in VALORES.items()}
    base = "mediana_dos_recuperados" if niveis["recovery_time"] else SEM_CLASSIFICACAO
    if niveis["recovery_time"] is None and nivel("recovery_time", limite) == rating.LOW:
        niveis["recovery_time"], base = rating.LOW, "limite_inferior_dos_censurados"
    por_commit = nivel("lead_time", linha["commit_lead_time_hours"])
    com_fallback = niveis["lead_time"] or por_commit
    estrita = rating.overall_classification([niveis[metrica] for metrica in rating.METRICS])
    permissiva = rating.overall_classification(
        [com_fallback if metrica == "lead_time" else niveis[metrica]
         for metrica in rating.METRICS])
    return {
        "repository": linha["repository"],
        **{coluna: linha[coluna] for coluna in VALORES.values()},
        "commit_lead_time_hours": linha["commit_lead_time_hours"],
        **{f"{metrica}_level": niveis[metrica] for metrica in rating.METRICS},
        "lead_time_variante": "(a) por release" if niveis["lead_time"] else SEM_CLASSIFICACAO,
        "lead_time_apenas_com_b": niveis["lead_time"] is None and por_commit is not None,
        "recovery_time_base": base,
        "metricas_classificadas": estrita["classified_metrics"],
        "median_score": estrita["median_score"], "overall_score": estrita["overall_score"],
        "overall": estrita["overall"],
        "lead_time_level_com_fallback": com_fallback,
        "metricas_classificadas_com_fallback": permissiva["classified_metrics"],
        "overall_com_fallback": permissiva["overall"],
        "overall_mudou_sem_fallback": estrita["overall"] != permissiva["overall"],
    }


def valor_ou_nada(linha, coluna):
    """Nível de uma coluna da linha, com o ausente normalizado para None."""
    return linha[coluna] if pd.notna(linha[coluna]) else None


def divergencias(linha):
    """Diferenças entre o recalculado e o que o pipeline gravou, campo a campo."""
    diferencas = []
    for recalculado, gravado in CONFERENCIA:
        obtido = valor_ou_nada(linha, recalculado)
        esperado = valor_ou_nada(linha, f"{gravado}_pipeline")
        if esperado != obtido:
            diferencas.append(f"{gravado}: pipeline {esperado or SEM_CLASSIFICACAO} "
                              f"!= CSV {obtido or SEM_CLASSIFICACAO}")
    return "; ".join(diferencas)


def verificavel(quadro):
    """O CSV traz as colunas do pipeline? Sem elas não há conferência a fazer."""
    colunas = [f"{gravado}_pipeline" for _, gravado in CONFERENCIA]
    return bool(not quadro.empty and quadro.loc[:, colunas].notna().any().any())


def classificar(dados):
    """Uma linha por repositório: níveis da C1, leitura com fallback e conferência."""
    limites = limite_dos_censurados(dados.episodios)
    quadro = pd.DataFrame([
        classificar_repositorio(linha, limites.get(linha["repository"], np.nan))
        for _, linha in dados.repositorios.iterrows()])
    if quadro.empty:
        return quadro
    gravadas = [coluna for _, coluna in CONFERENCIA]
    quadro = quadro.merge(dados.repositorios[["repository", *gravadas]].rename(
        columns={coluna: f"{coluna}_pipeline" for coluna in gravadas}),
        on="repository", how="left")
    quadro["divergencias"] = ([divergencias(linha) for _, linha in quadro.iterrows()]
                              if verificavel(quadro) else "")
    return quadro


def conferencia(quadro):
    """Resumo da conferência contra o pipeline: quantos batem e o que divergiu.

    Um CSV sem as colunas `*_level` e `overall` não é comparável: a conferência fica
    como não verificável, em vez de acusar divergência em todos os repositórios.
    """
    vazio = pd.DataFrame(columns=["repository", "divergencias"])
    if not verificavel(quadro):
        return {"verificavel": False, "repositorios": int(len(quadro)), "conferem": 0,
                "divergentes": 0, "divergencias": vazio}
    divergentes = quadro[quadro["divergencias"] != ""]
    return {"verificavel": True, "repositorios": int(len(quadro)),
            "conferem": int(len(quadro) - len(divergentes)),
            "divergentes": int(len(divergentes)),
            "divergencias": divergentes.loc[:, ["repository", "divergencias"]]}


def contagem_por_nivel(serie):
    """Contagem dos cinco níveis em uma coluna, com o ausente como sem classificação."""
    valores = serie.astype("object").where(serie.notna(), SEM_CLASSIFICACAO)
    return {nivel_: int((valores == nivel_).sum()) for nivel_ in NIVEIS}


def distribuicao(quadro, coluna_geral="overall"):
    """Distribuição Elite/High/Medium/Low/sem classificação por métrica e no geral."""
    colunas = {metrica: f"{metrica}_level" for metrica in rating.METRICS}
    colunas["overall"] = coluna_geral
    linhas = [{"metrica": ROTULOS[nome], **contagem_por_nivel(quadro[coluna])}
              for nome, coluna in colunas.items()] if not quadro.empty else [
        {"metrica": ROTULOS[nome], **{nivel_: 0 for nivel_ in NIVEIS}} for nome in colunas]
    contagens = pd.DataFrame(linhas)
    total = len(quadro)
    percentuais = contagens.copy()
    for nivel_ in NIVEIS:
        percentuais[nivel_] = contagens[nivel_] / total if total else np.nan
    return contagens, percentuais


def cobertura(quadro):
    """Quantos repositórios têm 4, 3, 2, 1 ou nenhuma métrica classificada na C1."""
    linhas = [{"metricas_classificadas": quantidade,
               "repositorios": int((quadro["metricas_classificadas"] == quantidade).sum())
               if not quadro.empty else 0}
              for quantidade in range(len(rating.METRICS), -1, -1)]
    quadro_cobertura = pd.DataFrame(linhas)
    total = len(quadro)
    quadro_cobertura["proporcao"] = (quadro_cobertura["repositorios"] / total if total
                                     else np.nan)
    return quadro_cobertura


def figura_distribuicao(contagens, saida):
    """Barras empilhadas da distribuição de níveis por métrica e no geral."""
    plt = estilo.aplicar()
    figura, eixo = plt.subplots(figsize=(estilo.LARGURA, 2.9))
    posicoes = range(len(contagens))
    acumulado = np.zeros(len(contagens))
    for nivel_ in NIVEIS:
        valores = contagens[nivel_].to_numpy(dtype="float64")
        eixo.barh(posicoes, valores, left=acumulado, height=0.62, label=nivel_,
                  color=estilo.NIVEIS[nivel_], edgecolor="white", linewidth=0.5)
        acumulado += valores
    eixo.set(yticks=list(posicoes), yticklabels=list(contagens["metrica"]),
             xlabel="repositórios", xlim=(0, max(acumulado.max(), 1)))
    eixo.invert_yaxis()
    eixo.grid(axis="y", visible=False)
    estilo.contagem_inteira(eixo, das_contagens="x")
    eixo.legend(ncols=len(NIVEIS), frameon=False, loc="lower center",
                bbox_to_anchor=(0.5, 1.0), columnspacing=1.0, handlelength=1.2)
    figura.tight_layout()
    return estilo.salvar(figura, saida, "classificacao_c1_distribuicao")


def notas(quadro, contagens, cobertura_, checagem):
    """Rascunho com a definição da C1, as duas decisões e o resultado da conferência."""
    valor, total = comum.numero, len(quadro)
    geral = dict(zip(contagens["metrica"], contagens.to_dict(orient="records"))).get(
        ROTULOS["overall"], {nivel_: 0 for nivel_ in NIVEIS})
    apenas_b = int(quadro["lead_time_apenas_com_b"].sum()) if total else 0
    mudam = int(quadro["overall_mudou_sem_fallback"].sum()) if total else 0
    completos = int(cobertura_.iloc[0]["repositorios"]) if total else 0
    sem_geral = int(cobertura_.iloc[-1]["repositorios"]) if total else 0
    distribuicao_geral = ", ".join(
        f"{nivel_} {geral[nivel_]} ({valor(geral[nivel_] / total * 100, 1)}%)"
        for nivel_ in NIVEIS) if total else "amostra vazia"
    blocos = [
        "# C1 — classificação DORA de referência",
        comum.paragrafo(
            "Gerado por `python -m analise`. A C1 é a combinação de referência da análise de "
            "sensibilidade (RQ 07) e o resultado que resume as RQ 01 a 04: deployment = release "
            "publicada, Lead Time pela variante (a) por release, Change Failure Rate pela "
            "variante (a) proxy de CI e tempo de recuperação da primeira falha ao primeiro "
            "sucesso do mesmo workflow. As faixas são as da tabela de referência do enunciado, "
            "implementadas em `dora_selection/rating.py` — a análise não as reescreve, para que "
            "exista uma definição só no repositório."),

        "## Decisão 1 — o fallback do Lead Time",
        comum.paragrafo(
            f"`lead_time_rating` classifica pela variante (a) e, quando ela não existe, cai para "
            f"a (b) por commit. {apenas_b} de {total} repositórios foram classificados assim e, a "
            f"rigor, não estão na C1. As duas leituras saem no mesmo CSV:"),
        "\n".join((
            comum.paragrafo(
                "- `lead_time_level` e `overall`: C1 **estrita**, só com a variante (a); sem ela "
                "o Lead Time fica sem classificação e o nível geral sai da mediana das outras "
                "três métricas.", 88, "  "),
            comum.paragrafo(
                "- `lead_time_level_com_fallback` e `overall_com_fallback`: a regra de hoje do "
                "pipeline.", 88, "  "))),
        comum.paragrafo(
            f"A escolha muda o nível geral de {comum.quantos(mudam, 'repositório', 'repositórios')}. "
            "**A decisão do grupo precisa ser registrada aqui**: (1) manter o fallback e "
            "documentá-lo ou (2) deixar esses repositórios sem classificação de Lead Time na C1. "
            "Enquanto ela não é tomada, a tabela e a figura da distribuição usam a C1 estrita, "
            "que é a definição literal da combinação, e a coluna com fallback fica disponível "
            "para a RQ 07 sem refazer a análise."),

        "## Decisão 2 — métrica sem classificação",
        comum.paragrafo(
            "O nível geral é a **mediana das notas das métricas disponíveis** (Elite = 4 a "
            "Low = 1), arredondada para baixo; o repositório só fica sem nível geral quando "
            "nenhuma das quatro métricas foi classificada. Uma métrica ausente nunca é tratada "
            "como zero nem como Elite e não entra na mediana — é por isso que um repositório com "
            "três métricas ainda recebe nível geral, calculado sobre essas três."),
        comum.paragrafo(
            f"{completos} de {total} repositórios têm as quatro métricas classificadas na C1, "
            f"{total - completos} têm menos de quatro e {sem_geral} ficaram sem nenhuma, portanto "
            "sem nível geral. A distribuição completa está em "
            "`resultados/tabelas/classificacao_c1_cobertura.csv`."),

        "## Reprodutibilidade a partir do CSV",
        comum.paragrafo(
            f"Os níveis foram recalculados a partir das colunas de `repositorios.csv` e "
            f"comparados com o que o pipeline gravou: {checagem['conferem']} de "
            f"{checagem['repositorios']} repositórios batem em todas as quatro métricas e no "
            f"nível geral, e {checagem['divergentes']} divergem (detalhe em "
            "`resultados/tabelas/classificacao_c1_divergencias.csv`)."
            if checagem["verificavel"] else
            "Este `repositorios.csv` não traz as colunas `*_level` nem `overall`, então não há o "
            "que comparar: a classificação foi recalculada, mas a conferência contra o pipeline "
            "fica pendente de um CSV gerado por ele."),
        comum.paragrafo(
            "A comparação usa a leitura com fallback, que é a regra implementada no pipeline; o "
            "tempo de recuperação sem nenhum episódio recuperado é reconstruído do limite "
            "inferior dos censurados em `episodios_falha.csv`, como faz `recovery_time_rating`."),

        "## Distribuição",
        comum.paragrafo(
            f"Classificação geral (C1 estrita): {distribuicao_geral}. A distribuição por métrica "
            "está em `resultados/tabelas/classificacao_c1_distribuicao.csv` (contagem) e "
            "`classificacao_c1_distribuicao_percentual.csv` (proporção), e na figura "
            "`resultados/figuras/classificacao_c1_distribuicao.pdf`."),
    ]
    return "\n\n".join(blocos) + "\n"


def executar(dados, saida="resultados"):
    """Reproduz a C1 a partir do CSV, confere com o pipeline e grava a distribuição."""
    saida = Path(saida)
    quadro = classificar(dados)
    checagem = conferencia(quadro)
    contagens, percentuais = distribuicao(quadro)
    cobertura_ = cobertura(quadro)
    comum.salvar_csv(quadro, saida, "classificacao_c1")
    comum.salvar_tabela(contagens, saida, "classificacao_c1_distribuicao", casas=0)
    comum.salvar_tabela(percentuais, saida, "classificacao_c1_distribuicao_percentual")
    comum.salvar_tabela(cobertura_, saida, "classificacao_c1_cobertura")
    comum.salvar_tabela(checagem["divergencias"], saida, "classificacao_c1_divergencias")
    figura = figura_distribuicao(contagens, saida)
    comum.salvar_texto(notas(quadro, contagens, cobertura_, checagem), saida,
                       "notas_classificacao_c1")
    resultado = {"repositorios": int(len(quadro)), "conferencia": checagem,
                 "distribuicao": contagens, "distribuicao_percentual": percentuais,
                 "cobertura": cobertura_, "figura": figura.name,
                 "lead_time_apenas_com_b": int(quadro["lead_time_apenas_com_b"].sum())
                 if not quadro.empty else 0,
                 "overall_muda_sem_fallback": int(quadro["overall_mudou_sem_fallback"].sum())
                 if not quadro.empty else 0,
                 "por_repositorio": quadro}
    comum.salvar_json(resultado, saida, "classificacao_c1")
    return resultado
