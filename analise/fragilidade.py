"""Fragilidade da classificação DORA perto dos limites das faixas.

Uma replicação independente do nosso dataset reclassificou `FuelLabs/sway` de Low para
Medium (Issue #62). O cálculo dos dois lados estava certo: o repositório fica **1,9 h
acima** do limite de 168 h entre Medium e Low no tempo de recuperação — 1,1% do valor —
e a classificação geral é a mediana das quatro notas arredondada para baixo, então mover
uma única métrica um degrau muda o resultado final.

Este módulo quantifica isso para todos os repositórios: para cada métrica da C1, a
distância até o limite mais próximo da tabela de referência e se mover essa métrica um
degrau, para melhor ou para pior, mudaria a classificação geral. Serve para responder a
Issues de divergência com número em vez de opinião, e alimenta a seção de ameaças à
validade: uma divergência de categoria entre replicações **não implica** erro de cálculo
quando a métrica está a 1% do limite.

As faixas vêm de `dora_selection.rating`, como no resto das análises.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from dora_selection import rating

from . import classificacao_c1 as c1
from . import comum, estilo


# Acima desta margem relativa a métrica não é considerada frágil: está longe do limite.
LIMIAR_FRAGIL = 0.05
# Repositório que motivou a análise, reclassificado por uma replicação independente.
CASO_RELATADO = "FuelLabs/sway"
ROTULOS = c1.ROTULOS


def limites(metrica):
    """Limites numéricos das faixas de uma métrica, do melhor para o pior."""
    return tuple(limite for _, limite in rating.SCALES[metrica].bands if limite is not None)


def margem(metrica, valor):
    """Distância da métrica até o limite de faixa mais próximo.

    `margem_relativa` usa o próprio valor como referência: 169,87 h a 1,87 h do limite de
    168 h dá 1,1%, que é a leitura publicada na resposta à Issue #62.
    """
    vazio = {"valor": np.nan, "nivel": None, "limite": np.nan, "margem": np.nan,
             "margem_relativa": np.nan}
    nivel = c1.nivel(metrica, valor)
    if nivel is None:
        return vazio
    limite = min(limites(metrica), key=lambda alvo: abs(valor - alvo))
    distancia = abs(valor - limite)
    return {"valor": float(valor), "nivel": nivel, "limite": float(limite),
            "margem": float(distancia),
            "margem_relativa": float(distancia / valor) if valor else np.nan}


def vizinhos(nivel):
    """Os níveis imediatamente melhor e pior que o dado, na escala de notas."""
    nota = rating.score(nivel)
    return [rating.level_from_score(nota + passo) for passo in (1, -1)
            if rating.level_from_score(nota + passo) is not None]


def muda_o_geral(niveis, metrica):
    """Mover essa métrica um degrau, para melhor ou para pior, muda a classificação geral?

    Compara a classificação geral atual com a que sairia se só essa métrica mudasse de
    faixa. Métrica sem classificação não é mexida: a ausência não é um degrau.
    """
    atual = rating.overall_classification([niveis[nome] for nome in rating.METRICS])["overall"]
    if niveis.get(metrica) is None:
        return False
    for vizinho in vizinhos(niveis[metrica]):
        trocado = {**niveis, metrica: vizinho}
        if rating.overall_classification(
                [trocado[nome] for nome in rating.METRICS])["overall"] != atual:
            return True
    return False


def fragilidade(repositorios):
    """Uma linha por repositório: a métrica mais próxima de um limite e o efeito de movê-la."""
    linhas = []
    for _, linha in repositorios.iterrows():
        niveis = {metrica: c1.nivel(metrica, linha[coluna])
                  for metrica, coluna in c1.VALORES.items()}
        margens = {metrica: margem(metrica, linha[coluna])
                   for metrica, coluna in c1.VALORES.items()}
        medidas = {metrica: dados for metrica, dados in margens.items()
                   if dados["nivel"] is not None}
        geral = rating.overall_classification([niveis[nome] for nome in rating.METRICS])
        mudam = [metrica for metrica in medidas if muda_o_geral(niveis, metrica)]
        frageis = [metrica for metrica, dados in medidas.items()
                   if dados["margem_relativa"] <= LIMIAR_FRAGIL]
        mais_fragil = min(medidas, key=lambda nome: medidas[nome]["margem_relativa"],
                          default=None)
        dados = medidas.get(mais_fragil, margem("lead_time", np.nan))
        linhas.append({
            "repository": linha["repository"], "overall": geral["overall"],
            "metrica_mais_fragil": ROTULOS.get(mais_fragil, ""),
            "valor": dados["valor"], "nivel": dados["nivel"], "limite": dados["limite"],
            "margem": dados["margem"], "margem_relativa": dados["margem_relativa"],
            "muda_o_geral": mais_fragil in mudam,
            "metricas_que_mudam_o_geral": len(mudam),
            "metricas_proximas_do_limite": len(frageis)})
    return pd.DataFrame(linhas)


def resumo_fragilidade(quadro):
    """Quantos repositórios trocam de categoria se uma única métrica andar um degrau."""
    if quadro.empty:
        return {"repositorios": 0, "com_metrica_sensivel": 0, "proporcao_sensivel": np.nan,
                "margem_minima": np.nan, "mais_fragil": None}
    sensiveis = quadro[quadro["metricas_que_mudam_o_geral"] > 0]
    no_limite = quadro[quadro["margem_relativa"] <= LIMIAR_FRAGIL]
    campeao = quadro.loc[quadro["margem_relativa"].idxmin()]
    return {"repositorios": int(len(quadro)),
            "com_metrica_sensivel": int(len(sensiveis)),
            "proporcao_sensivel": float(len(sensiveis) / len(quadro)),
            "proximos_do_limite": int(len(no_limite)),
            "sensiveis_e_proximos": int(len(quadro[(quadro["margem_relativa"] <= LIMIAR_FRAGIL)
                                                   & quadro["muda_o_geral"]])),
            "margem_minima": float(campeao["margem_relativa"]),
            "mais_fragil": str(campeao["repository"]),
            "mais_fragil_metrica": str(campeao["metrica_mais_fragil"]),
            "mais_fragil_overall": str(campeao["overall"])}


def figura_fragilidade(quadro, saida):
    """Distribuição da margem até o limite mais próximo, com a faixa de risco destacada."""
    plt = estilo.aplicar()
    figura, eixo = plt.subplots(figsize=estilo.TAMANHO_DUPLO)
    margens = quadro["margem_relativa"].dropna()
    positivas = margens[margens > 0]
    if not positivas.empty:
        faixas = np.logspace(np.log10(max(positivas.min(), 1e-4)),
                             np.log10(positivas.max()), 25)
        eixo.hist(positivas, bins=faixas, color=estilo.VARIANTE_A, alpha=0.75,
                  edgecolor="white", linewidth=0.4)
        eixo.set_xscale("log")
        eixo.axvline(LIMIAR_FRAGIL, color=estilo.VARIANTE_B, linestyle="--", linewidth=1.0,
                     label=f"{LIMIAR_FRAGIL:.0%} do valor")
        eixo.legend(frameon=False, loc="upper left")
    estilo.contagem_inteira(eixo)
    eixo.set(xlabel="margem até o limite de faixa mais próximo, em fração do valor (log)",
             ylabel="repositórios",
             title="Quão perto de mudar de categoria cada repositório está")
    figura.tight_layout()
    return estilo.salvar(figura, saida, "fragilidade_limites")


def relato_do_caso(quadro, valor):
    """Parágrafo sobre o repositório que a replicação independente reclassificou.

    Os números saem da tabela, não do texto da Issue: a posição no ranking de fragilidade
    é calculada, para não afirmar que o caso relatado é o mais frágil da amostra quando
    não é.
    """
    ordenado = quadro.dropna(subset=["margem_relativa"]).sort_values("margem_relativa")
    linha = ordenado[ordenado["repository"] == CASO_RELATADO]
    if linha.empty:
        return comum.paragrafo(
            f"`{CASO_RELATADO}` não está nesta amostra, então a divergência relatada na "
            "Issue #62 não pode ser medida aqui.")
    posicao = int(ordenado.index.get_indexer(linha.index)[0]) + 1
    linha = linha.iloc[0]
    return comum.paragrafo(
        f"Uma replicação independente do nosso dataset reclassificou `{CASO_RELATADO}` de "
        f"{linha['overall']} para a categoria seguinte (Issue #62). A tabela explica por "
        f"quê: a métrica {linha['metrica_mais_fragil']} vale {valor(linha['valor'])} "
        f"contra um limite de {valor(linha['limite'])} — margem de "
        f"{valor(linha['margem'])}, ou {valor(linha['margem_relativa'] * 100, 2)}% do "
        f"valor — e {int(linha['metricas_que_mudam_o_geral'])} das suas quatro métricas "
        "mudam a classificação geral se andarem um degrau. Não é o repositório mais "
        f"frágil da amostra: é o {posicao}º de {len(ordenado)}. O cálculo dos dois lados "
        "estava correto; o que diverge é a posição de uma medida contínua em relação a um "
        "limite fixo.")


def notas(quadro, resumo):
    """Rascunho para as ameaças à validade, com o caso que motivou a análise."""
    valor = comum.numero
    if not resumo["repositorios"]:
        return "# Fragilidade da classificação perto dos limites\n\nAmostra vazia.\n"
    piores = quadro.nsmallest(5, "margem_relativa")
    caso = relato_do_caso(quadro, valor)
    lista = "\n".join(
        comum.paragrafo(
            f"- `{linha['repository']}` ({linha['overall']}): {linha['metrica_mais_fragil']} "
            f"em {valor(linha['valor'])} contra o limite de {valor(linha['limite'])} — "
            f"margem de {valor(linha['margem'], 4)} "
            f"({valor(linha['margem_relativa'] * 100, 2)}% do valor)"
            f"{'; mover essa métrica um degrau muda a classificação geral' if linha['muda_o_geral'] else ''}.",
            88, "  ")
        for _, linha in piores.iterrows())
    return f"""# Fragilidade da classificação DORA perto dos limites das faixas

{comum.paragrafo(
    "Gerado por `python -m analise`. A classificação geral é a mediana das quatro notas "
    "arredondada para baixo, e cada nota vem de uma faixa com limite fixo. Quando uma "
    "métrica cai perto de um limite, uma diferença pequena de coleta — uma janela "
    "deslocada em horas, um episódio de falha a mais — muda a nota e pode mudar a "
    "categoria geral. Esta análise mede essa distância para todos os repositórios.")}

{comum.paragrafo(
    f"Em {resumo['com_metrica_sensivel']} dos {resumo['repositorios']} repositórios "
    f"({valor(resumo['proporcao_sensivel'] * 100, 1)}%), mover **uma única métrica** um "
    f"degrau já muda a classificação geral. Em {resumo['proximos_do_limite']} deles a "
    f"métrica mais próxima está a {valor(LIMIAR_FRAGIL * 100, 0)}% ou menos do limite, e "
    f"em {resumo['sensiveis_e_proximos']} as duas coisas valem ao mesmo tempo: estão "
    "perto do limite **e** a troca mudaria a categoria.")}

## Os cinco mais frágeis

{lista}

{comum.paragrafo(
    f"O mais frágil da amostra é `{resumo['mais_fragil']}`, a "
    f"{valor(resumo['margem_minima'] * 100, 2)}% de distância do limite "
    f"de {resumo['mais_fragil_metrica']}.")}

## O caso relatado na Issue #62

{caso}

## Para a seção de ameaças à validade

{comum.paragrafo(
    "A classificação DORA em faixas é uma discretização de medidas contínuas, e nada no "
    "método avisa quando um repositório está à beira de uma faixa. Duas consequências "
    "para quem lê os nossos resultados: (1) uma divergência de categoria entre duas "
    "execuções não implica erro de cálculo em nenhuma delas — pode ser uma métrica a 1% "
    "do limite; (2) comparações de categoria entre grupos ou entre combinações (RQ 07) "
    "deveriam reportar, junto, quantos repositórios estavam perto de um limite, porque é "
    "deles que vem a instabilidade. A tabela "
    "`resultados/tabelas/fragilidade_limites.csv` traz a margem de cada repositório para "
    "esse fim.")}
"""


def executar(dados, saida="resultados"):
    """Mede a fragilidade de cada repositório e grava a tabela, a figura e o rascunho."""
    saida = Path(saida)
    quadro = fragilidade(dados.repositorios)
    resumo = resumo_fragilidade(quadro)
    comum.salvar_tabela(quadro, saida, "fragilidade_limites", casas=4)
    figura = figura_fragilidade(quadro, saida)
    comum.salvar_texto(notas(quadro, resumo), saida, "notas_fragilidade")
    comum.salvar_json({"resumo": resumo, "por_repositorio": quadro}, saida, "fragilidade")
    return {**resumo, "figura": figura.name, "por_repositorio": quadro}
