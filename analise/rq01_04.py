"""RQ 01 a 04: estatística descritiva das métricas DORA (mediana, IQR e censura).

Responde "quanto valem as métricas DORA nos repositórios populares que usam CI/CD"
com mediana e IQR — nunca média e desvio-padrão — e, nas RQ 02 e 03, com as duas
variantes obrigatórias lado a lado:

- RQ 01, Deployment Frequency: releases por semana;
- RQ 02, Lead Time: (a) por release, do commit mais antigo do intervalo até a
  publicação, e (b) por commit, de cada commit até a publicação;
- RQ 03, Change Failure Rate: (a) proxy de CI, falhas sobre runs considerados, e
  (b) proxy de entrega, releases seguidas de uma corretiva em até 7 dias;
- RQ 04, tempo de recuperação: da primeira falha ao primeiro sucesso do workflow.

Nada é estimado para "fechar a conta": releases fora do Lead Time são contadas por
motivo, releases dos últimos 7 dias da janela ficam censuradas no CFR (b) e episódios
sem sucesso posterior ficam censurados na RQ 04. Em todos os casos o total excluído é
publicado junto com a estatística, e a RQ 04 traz também o limite inferior que trata
os censurados como recuperados no fim da janela.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from . import comum, estilo


HORAS_POR_DIA = 24.0
# Quantos repositórios entram na inspeção manual da divergência entre (a) e (b).
TOPO_RAZAO = 5
# Acima desta razão entre o intervalo da release e a mediana dos seus commits, o
# intervalo é dominado por um commit antigo "esquecido", não pelo ritmo do trabalho.
LIMIAR_COMMIT_ESQUECIDO = 2.0
# Motivo da exclusão: coluna no resumo por repositório, rótulo e os valores
# equivalentes de `status` e de `comparison_status` em releases.csv.
MOTIVOS_IGNORADAS = (
    ("releases_no_previous", "Sem release anterior", ("no_previous_release",), ()),
    ("releases_compare_not_found", "compare com 404", (), ("not_found",)),
    ("releases_compare_error", "compare com erro", (), ("error",)),
    ("releases_no_new_commits", "Sem commits novos", ("no_commits",), ()),
    ("releases_no_commit_dates", "Commits sem data", ("no_commit_dates",), ()),
    ("releases_no_date", "Sem data de publicação", ("no_date",), ()),
)


def total(quadro, coluna):
    """Soma inteira de uma coluna de contagem; ausências contam como zero."""
    return int(comum.serie_numerica(quadro[coluna]).fillna(0).sum())


def bandeira(quadro, coluna):
    """Coluna booleana como `bool` puro: NA vira False, para somar e filtrar."""
    return quadro[coluna].astype("boolean").fillna(False).astype(bool)


def alinhar(repositorios, por_repositorio, coluna):
    """Traz uma coluna agregada para a ordem de `repositorios.csv`, preservando os sem valor.

    Só é chamada quando a tabela detalhada decidiu algum valor; repositório sem linha
    na tabela fica com NaN, em vez de entrar na mediana com zero.
    """
    juncao = repositorios[["repository"]].merge(por_repositorio, on="repository", how="left")
    return comum.serie_numerica(juncao[coluna]).set_axis(repositorios.index)


# --------------------------------------------------------------------------- RQ 01

def rq01(dados, saida):
    """Deployment Frequency: releases por semana entre repositórios."""
    serie = comum.serie_numerica(dados.repositorios["releases_per_week"])
    estatisticas = comum.resumo(serie)
    figura = figura_rq01(serie, saida)
    return {"resumo": estatisticas, "repositorios": int(serie.size),
            "repositorios_sem_release": int((serie == 0).sum()),
            "repositorios_sem_valor": estatisticas["ausentes"], "figura": figura.name}


def figura_rq01(serie, saida):
    """Distribuição das releases por semana: histograma e boxplot em escala log."""
    plt = estilo.aplicar()
    valores = serie.dropna()
    positivos = valores[valores > 0]
    figura, (esquerda, direita) = plt.subplots(1, 2, figsize=estilo.TAMANHO_DUPLO)
    if not positivos.empty:
        faixas = np.logspace(np.log10(positivos.min()), np.log10(positivos.max()), 13)
        esquerda.hist(positivos, bins=faixas, color=estilo.VARIANTE_A, alpha=0.75,
                      edgecolor="white", linewidth=0.4)
        esquerda.set_xscale("log")
        estilo.caixa(direita, [positivos.to_numpy()], ["releases/semana"], [estilo.VARIANTE_A])
        direita.set_yscale("log")
    estilo.contagem_inteira(esquerda)
    esquerda.set(xlabel="releases por semana (log)", ylabel="repositórios",
                 title=f"Distribuição (n = {positivos.size})")
    direita.set(ylabel="releases por semana (log)", title="Mediana e IQR")
    figura.tight_layout()
    return estilo.salvar(figura, saida, "rq01_deployment_frequency")


# --------------------------------------------------------------------------- RQ 02

def releases_ignoradas(dados):
    """Releases fora do Lead Time por motivo, do resumo por repositório ou das releases.

    Prefere as contagens de `repositorios.csv`, que separam o `compare` com 404 do
    `compare` com erro; quando elas não existem, recai sobre `status` e
    `comparison_status` em `releases.csv`.
    """
    observadas = int(dados.releases.shape[0])
    linhas = []
    for coluna, rotulo, estados, comparacoes in MOTIVOS_IGNORADAS:
        resumo_coluna = comum.serie_numerica(dados.repositorios[coluna])
        if resumo_coluna.notna().any():
            quantidade, origem = int(resumo_coluna.fillna(0).sum()), comum.REPOSITORIOS.arquivo
        else:
            quantidade = int(dados.releases["status"].isin(estados).sum()
                             + dados.releases["comparison_status"].isin(comparacoes).sum())
            origem = comum.RELEASES.arquivo
        linhas.append({"motivo": rotulo, "coluna": coluna, "releases": quantidade,
                       "origem": origem})
    quadro = pd.DataFrame(linhas)
    quadro.loc[len(quadro)] = {"motivo": "Total ignorado", "coluna": "",
                               "releases": int(quadro["releases"].sum()), "origem": ""}
    quadro["proporcao_das_releases_observadas"] = (quadro["releases"] / observadas if observadas
                                        else np.nan)
    return quadro


def razao_lead_time(repositorios):
    """Razão (a)/(b) por repositório: quanto o intervalo da release excede o do commit."""
    quadro = repositorios.loc[:, ["repository"]].copy()
    quadro["lead_time_a_horas"] = comum.serie_numerica(repositorios["release_lead_time_hours"])
    quadro["lead_time_b_horas"] = comum.serie_numerica(repositorios["commit_lead_time_hours"])
    quadro["razao_a_b"] = (quadro["lead_time_a_horas"]
                           / quadro["lead_time_b_horas"].where(lambda serie: serie > 0))
    return quadro


def commit_esquecido(releases, repositorio):
    """Indício do commit antigo "esquecido" na release de maior intervalo do repositório.

    Compara o intervalo da release (do commit mais antigo até a publicação) com a
    mediana dos seus próprios commits: quando o primeiro é muito maior, um único
    commit antigo — e não o ritmo de trabalho — define o Lead Time da variante (a).
    """
    candidatas = releases[(releases["repository"] == repositorio)
                          & releases["lead_time_hours"].notna()]
    if candidatas.empty:
        return {"tag_name": pd.NA, "commits": np.nan, "release_horas": np.nan,
                "mediana_commits_horas": np.nan, "razao_release_commits": np.nan,
                "intervalo_commits_dias": np.nan, "commit_antigo_esquecido": pd.NA}
    release = candidatas.loc[candidatas["lead_time_hours"].idxmax()]
    mediana = release["median_commit_lead_time_hours"]
    razao = release["lead_time_hours"] / mediana if mediana == mediana and mediana > 0 else np.nan
    intervalo = release["last_commit_author_date"] - release["first_commit_author_date"]
    return {"tag_name": release["tag_name"], "commits": release["commits"],
            "release_horas": release["lead_time_hours"], "mediana_commits_horas": mediana,
            "razao_release_commits": razao,
            "intervalo_commits_dias": (intervalo.total_seconds() / 3600 / HORAS_POR_DIA
                                       if pd.notna(intervalo) else np.nan),
            "commit_antigo_esquecido": bool(razao >= LIMIAR_COMMIT_ESQUECIDO)
            if razao == razao else pd.NA}


def maiores_razoes(dados, razoes, topo=TOPO_RAZAO):
    """Os repositórios com maior razão (a)/(b), com a release que explica a divergência."""
    maiores = razoes.dropna(subset=["razao_a_b"]).nlargest(topo, "razao_a_b")
    if maiores.empty:
        return maiores.assign(**{chave: [] for chave in commit_esquecido(dados.releases, "")})
    evidencias = pd.DataFrame([commit_esquecido(dados.releases, repositorio)
                               for repositorio in maiores["repository"]], index=maiores.index)
    return pd.concat([maiores, evidencias], axis="columns")


def rq02(dados, saida):
    """Lead Time nas duas variantes obrigatórias, em horas e em dias."""
    variante_a = comum.serie_numerica(dados.repositorios["release_lead_time_hours"])
    variante_b = comum.serie_numerica(dados.repositorios["commit_lead_time_hours"])
    razoes = razao_lead_time(dados.repositorios)
    maiores = maiores_razoes(dados, razoes)
    ignoradas = releases_ignoradas(dados)
    figura = figura_rq02(variante_a, variante_b, saida)
    return {
        "a_release": {"horas": comum.resumo(variante_a),
                      "dias": comum.resumo(variante_a / HORAS_POR_DIA)},
        "b_commit": {"horas": comum.resumo(variante_b),
                     "dias": comum.resumo(variante_b / HORAS_POR_DIA)},
        "razao_a_b": comum.resumo(razoes["razao_a_b"]),
        "maiores_razoes": maiores,
        "repositorios_com_commit_antigo_esquecido": int(
            bandeira(maiores, "commit_antigo_esquecido").sum()),
        "releases_ignoradas": ignoradas,
        "releases_ignoradas_total": int(
            ignoradas.loc[ignoradas["motivo"] == "Total ignorado", "releases"].iloc[0]),
        "releases_observadas": int(dados.releases.shape[0]), "figura": figura.name}


def figura_rq02(variante_a, variante_b, saida):
    """(a) × (b): boxplots lado a lado e dispersão com a diagonal a = b."""
    plt = estilo.aplicar()
    figura, (esquerda, direita) = plt.subplots(1, 2, figsize=estilo.TAMANHO_DUPLO)
    amostras = [serie.dropna()[lambda valores: valores > 0].to_numpy()
                for serie in (variante_a, variante_b)]
    if all(amostra.size for amostra in amostras):
        estilo.caixa(esquerda, amostras, ["(a) release", "(b) commit"],
                     [estilo.VARIANTE_A, estilo.VARIANTE_B])
        esquerda.set_yscale("log")
    esquerda.set(ylabel="Lead Time mediano, horas (log)", title="Variantes lado a lado")
    direita.scatter(variante_b, variante_a, s=8, color=estilo.NEUTRO, alpha=0.7,
                    edgecolors="none")
    if estilo.diagonal(direita, variante_b, variante_a):
        direita.legend(loc="lower right", frameon=False)
    direita.set(xlabel="(b) por commit, horas (log)", ylabel="(a) por release, horas (log)",
                title="Dispersão a × b")
    figura.tight_layout()
    return estilo.salvar(figura, saida, "rq02_lead_time_variantes")


# --------------------------------------------------------------------------- RQ 03

def cfr_entrega_por_repositorio(releases):
    """CFR (b) por repositório: releases que falharam sobre releases avaliáveis.

    Releases dos últimos 7 dias da janela não têm 7 dias observados: ficam fora do
    denominador e entram em `censuradas`. Releases sem data de publicação não são
    avaliáveis e não entram em nenhuma das duas contagens.

    Sem nenhum veredito em `censored`/`failed` a tabela não decide nada: devolve vazio,
    para que a RQ 03 use o resumo por repositório em vez de contar zero falha em todos.
    """
    quadro = releases[releases["published_at"].notna()].copy()
    decidido = not quadro.empty and bool(quadro[["censored", "failed"]].notna().any().any())
    if not decidido:
        return pd.DataFrame(columns=["repository", "releases_cfr", "censuradas", "avaliadas",
                                     "falhas", "cfr_entrega"])
    quadro["censurada"] = bandeira(quadro, "censored")
    quadro["falhou"] = bandeira(quadro, "failed") & ~quadro["censurada"]
    agregado = quadro.groupby("repository", dropna=False).agg(
        releases_cfr=("repository", "size"), censuradas=("censurada", "sum"),
        falhas=("falhou", "sum")).reset_index()
    agregado["avaliadas"] = agregado["releases_cfr"] - agregado["censuradas"]
    agregado["cfr_entrega"] = (agregado["falhas"]
                               / agregado["avaliadas"].where(lambda serie: serie > 0))
    return agregado


def rq03(dados, saida):
    """Change Failure Rate nas duas variantes: proxy de CI e proxy de entrega."""
    variante_a = comum.serie_numerica(dados.repositorios["change_failure_rate"])
    por_repositorio = cfr_entrega_por_repositorio(dados.releases)
    coluna_resumo = comum.serie_numerica(dados.repositorios["delivery_change_failure_rate"])
    if por_repositorio.empty or not por_repositorio["cfr_entrega"].notna().any():
        variante_b, origem = coluna_resumo, comum.REPOSITORIOS.arquivo
    else:
        variante_b = alinhar(dados.repositorios, por_repositorio, "cfr_entrega")
        origem = comum.RELEASES.arquivo
    figura = figura_rq03(variante_a, variante_b, saida)
    return {
        "a_ci": {"resumo": comum.resumo(variante_a),
                 "runs_considerados": total(dados.repositorios, "considered_runs"),
                 "runs_ignorados": total(dados.repositorios, "ignored_runs"),
                 "repositorios_sem_run_considerado": int(
                     (comum.serie_numerica(dados.repositorios["considered_runs"]) == 0).sum())},
        "b_entrega": {"resumo": comum.resumo(variante_b), "origem": origem,
                      "releases_avaliadas": int(por_repositorio["avaliadas"].sum())
                      if not por_repositorio.empty else 0,
                      "releases_que_falharam": int(por_repositorio["falhas"].sum())
                      if not por_repositorio.empty else 0,
                      "releases_censuradas": int(por_repositorio["censuradas"].sum())
                      if not por_repositorio.empty else 0},
        "por_repositorio": por_repositorio, "figura": figura.name}


def figura_rq03(variante_a, variante_b, saida):
    """CFR (a) × (b): boxplots lado a lado e dispersão com a diagonal a = b."""
    plt = estilo.aplicar()
    figura, (esquerda, direita) = plt.subplots(1, 2, figsize=estilo.TAMANHO_DUPLO)
    amostras = [serie.dropna().to_numpy() for serie in (variante_a, variante_b)]
    if all(amostra.size for amostra in amostras):
        estilo.caixa(esquerda, amostras, ["(a) CI", "(b) entrega"],
                     [estilo.VARIANTE_A, estilo.VARIANTE_B])
    esquerda.set(ylabel="Change Failure Rate", ylim=(-0.02, 1.02),
                 title="Variantes lado a lado")
    direita.scatter(variante_b, variante_a, s=8, color=estilo.NEUTRO, alpha=0.7,
                    edgecolors="none")
    direita.plot([0, 1], [0, 1], color=estilo.REFERENCIA, linestyle="--", linewidth=0.8,
                 zorder=0, label="a = b")
    direita.set(xlabel="(b) proxy de entrega", ylabel="(a) proxy de CI",
                xlim=(-0.02, 1.02), ylim=(-0.02, 1.02), title="Dispersão a × b")
    direita.legend(loc="lower right", frameon=False)
    figura.tight_layout()
    return estilo.salvar(figura, saida, "rq03_cfr_variantes")


# --------------------------------------------------------------------------- RQ 04

def recuperacao_por_repositorio(episodios):
    """Por repositório: mediana dos episódios recuperados, censura e limite inferior.

    `mediana_horas` usa só episódios recuperados e consistentes, como manda a métrica,
    e por isso subestima o tempo real. `mediana_limite_horas` é o limite inferior do
    viés: trata cada episódio censurado como recuperado no fim da observação
    (`observed_hours`), que é o maior valor que a janela permite afirmar.
    """
    colunas = ["repository", "episodios", "recuperados", "censurados", "inconsistentes",
               "mediana_horas", "mediana_limite_horas", "proporcao_censurada"]
    if episodios.empty:
        return pd.DataFrame(columns=colunas)
    quadro = episodios.copy()
    recuperado = bandeira(quadro, "recovered")
    inconsistente = bandeira(quadro, "inconsistent")
    censurado = quadro["censored"].astype("boolean").fillna(pd.Series(
        ~recuperado, index=quadro.index, dtype="boolean")).astype(bool)
    quadro["recuperado"], quadro["inconsistente"], quadro["censurado"] = (
        recuperado, inconsistente, censurado)
    quadro["horas_validas"] = quadro["recovery_hours"].where(recuperado & ~inconsistente)
    quadro["horas_limite"] = quadro["horas_validas"].fillna(
        quadro["observed_hours"].where(censurado))
    agregado = quadro.groupby("repository", dropna=False).agg(
        episodios=("repository", "size"), recuperados=("recuperado", "sum"),
        censurados=("censurado", "sum"), inconsistentes=("inconsistente", "sum"),
        mediana_horas=("horas_validas", "median"),
        mediana_limite_horas=("horas_limite", "median")).reset_index()
    agregado["proporcao_censurada"] = agregado["censurados"] / agregado["episodios"]
    return agregado.loc[:, colunas]


def rq04(dados, saida):
    """Tempo de recuperação entre repositórios, com a censura quantificada."""
    por_repositorio = recuperacao_por_repositorio(dados.episodios)
    coluna_resumo = comum.serie_numerica(dados.repositorios["recovery_hours"])
    if por_repositorio.empty or not por_repositorio["mediana_horas"].notna().any():
        recuperados, origem = coluna_resumo, comum.REPOSITORIOS.arquivo
        limite = pd.Series(np.nan, index=dados.repositorios.index, dtype="float64")
        censura = limite
    else:
        recuperados = alinhar(dados.repositorios, por_repositorio, "mediana_horas")
        limite = alinhar(dados.repositorios, por_repositorio, "mediana_limite_horas")
        censura = alinhar(dados.repositorios, por_repositorio, "proporcao_censurada")
        origem = comum.EPISODIOS.arquivo
    recuperados_resumo, limite_resumo = comum.resumo(recuperados), comum.resumo(limite)
    figura = figura_rq04(recuperados, limite, censura, saida)
    return {
        "recuperados": {"horas": recuperados_resumo,
                        "dias": comum.resumo(recuperados / HORAS_POR_DIA), "origem": origem},
        "limite_inferior": {"horas": limite_resumo,
                            "dias": comum.resumo(limite / HORAS_POR_DIA)},
        "vies_da_censura_horas": limite_resumo["mediana"] - recuperados_resumo["mediana"],
        "episodios": {chave: int(por_repositorio[coluna].sum()) if not por_repositorio.empty else 0
                      for chave, coluna in (("total", "episodios"), ("recuperados", "recuperados"),
                                            ("censurados", "censurados"),
                                            ("inconsistentes", "inconsistentes"))},
        "proporcao_censurada": comum.resumo(censura),
        "por_repositorio": por_repositorio, "figura": figura.name}


def figura_rq04(recuperados, limite, censura, saida):
    """Tempo de recuperação com e sem os censurados, e a censura por repositório."""
    plt = estilo.aplicar()
    figura, (esquerda, direita) = plt.subplots(1, 2, figsize=estilo.TAMANHO_DUPLO)
    amostras = [serie.dropna()[lambda valores: valores > 0].to_numpy()
                for serie in (recuperados, limite)]
    if all(amostra.size for amostra in amostras):
        estilo.caixa(esquerda, amostras, ["recuperados", "limite inferior"],
                     [estilo.VARIANTE_A, estilo.VARIANTE_B])
        esquerda.set_yscale("log")
    esquerda.set(ylabel="recuperação mediana, horas (log)", title="Efeito da censura")
    proporcoes = censura.dropna()
    if not proporcoes.empty:
        direita.hist(proporcoes, bins=np.linspace(0, 1, 11), color=estilo.VARIANTE_B,
                     alpha=0.75, edgecolor="white", linewidth=0.4)
    estilo.contagem_inteira(direita)
    direita.set(xlabel="episódios censurados no repositório", ylabel="repositórios",
                xlim=(0, 1), title=f"Censura (n = {proporcoes.size})")
    figura.tight_layout()
    return estilo.salvar(figura, saida, "rq04_tempo_de_recuperacao")


# ------------------------------------------------------------------ síntese e saídas

ESTATISTICAS = ("n", "ausentes", "mediana", "q1", "q3", "iqr")


def sintese(resultados):
    """Tabela-síntese única: métrica × variante × (n, mediana, Q1, Q3, IQR, unidade)."""
    um, dois, tres, quatro = (resultados[chave] for chave in ("rq01", "rq02", "rq03", "rq04"))
    linhas = (
        ("RQ 01 Deployment Frequency", "única", "releases/semana", um["resumo"]),
        ("RQ 02 Lead Time", "(a) por release", "horas", dois["a_release"]["horas"]),
        ("RQ 02 Lead Time", "(a) por release", "dias", dois["a_release"]["dias"]),
        ("RQ 02 Lead Time", "(b) por commit", "horas", dois["b_commit"]["horas"]),
        ("RQ 02 Lead Time", "(b) por commit", "dias", dois["b_commit"]["dias"]),
        ("RQ 02 Lead Time", "razão (a)/(b)", "vezes", dois["razao_a_b"]),
        ("RQ 03 Change Failure Rate", "(a) proxy de CI", "proporção", tres["a_ci"]["resumo"]),
        ("RQ 03 Change Failure Rate", "(b) proxy de entrega", "proporção",
         tres["b_entrega"]["resumo"]),
        ("RQ 04 Tempo de recuperação", "episódios recuperados", "horas",
         quatro["recuperados"]["horas"]),
        ("RQ 04 Tempo de recuperação", "episódios recuperados", "dias",
         quatro["recuperados"]["dias"]),
        ("RQ 04 Tempo de recuperação", "limite inferior com censurados", "horas",
         quatro["limite_inferior"]["horas"]),
        ("RQ 04 Tempo de recuperação", "limite inferior com censurados", "dias",
         quatro["limite_inferior"]["dias"]),
        ("RQ 04 Censura", "episódios censurados por repositório", "proporção",
         quatro["proporcao_censurada"]),
    )
    return pd.DataFrame([{"metrica": metrica, "variante": variante, "unidade": unidade,
                          **{chave: estatisticas[chave] for chave in ESTATISTICAS}}
                         for metrica, variante, unidade, estatisticas in linhas])


def indicadores(pares):
    """Tabela de contagens no formato indicador × valor, para o artigo."""
    return pd.DataFrame([{"indicador": rotulo, "valor": valor} for rotulo, valor in pares],
                        dtype=object)


def cobertura_rq03(resultado):
    """O que entrou e o que ficou de fora em cada variante do Change Failure Rate."""
    ci, entrega = resultado["a_ci"], resultado["b_entrega"]
    return indicadores((
        ("(a) runs considerados", ci["runs_considerados"]),
        ("(a) runs ignorados", ci["runs_ignorados"]),
        ("(a) repositórios sem run considerado", ci["repositorios_sem_run_considerado"]),
        ("(b) releases avaliadas", entrega["releases_avaliadas"]),
        ("(b) releases que falharam", entrega["releases_que_falharam"]),
        ("(b) releases censuradas nos últimos 7 dias", entrega["releases_censuradas"])))


def censura_rq04(resultado):
    """Episódios por desfecho e o tamanho do viés que a censura introduz."""
    episodios, proporcao = resultado["episodios"], resultado["proporcao_censurada"]
    return indicadores((
        ("Episódios de falha", episodios["total"]),
        ("Episódios recuperados", episodios["recuperados"]),
        ("Episódios censurados", episodios["censurados"]),
        ("Episódios inconsistentes", episodios["inconsistentes"]),
        ("Proporção censurada por repositório, mediana", proporcao["mediana"]),
        ("Proporção censurada por repositório, Q1", proporcao["q1"]),
        ("Proporção censurada por repositório, Q3", proporcao["q3"]),
        ("Proporção censurada por repositório, IQR", proporcao["iqr"]),
        ("Mediana dos recuperados, horas", resultado["recuperados"]["horas"]["mediana"]),
        ("Mediana do limite inferior, horas", resultado["limite_inferior"]["horas"]["mediana"]),
        ("Viés da censura, horas", resultado["vies_da_censura_horas"])))


def notas(resultados):
    """Rascunhos com os números já no texto, para a seção de Resultados do artigo."""
    um, dois, tres, quatro = (resultados[chave] for chave in ("rq01", "rq02", "rq03", "rq04"))
    valor, frequencia = comum.numero, um["resumo"]
    sem_release = um["repositorios_sem_release"]
    a_horas, b_horas = dois["a_release"]["horas"], dois["b_commit"]["horas"]
    ci, entrega = tres["a_ci"], tres["b_entrega"]
    recuperados, limite, episodios = (quatro["recuperados"], quatro["limite_inferior"],
                                      quatro["episodios"])
    itens = [comum.paragrafo(
        f"- `{linha['repository']}`: razão {valor(linha['razao_a_b'])}× ((a) "
        f"{valor(linha['lead_time_a_horas'])} h contra (b) {valor(linha['lead_time_b_horas'])} h); "
        f"maior intervalo em `{linha['tag_name']}`, {valor(linha['release_horas'])} h contra "
        f"{valor(linha['mediana_commits_horas'])} h da mediana dos seus commits "
        f"({valor(linha['razao_release_commits'])}×), commits espalhados por "
        f"{valor(linha['intervalo_commits_dias'])} dias.", 88).replace("\n", "\n  ")
        for _, linha in dois["maiores_razoes"].iterrows()]
    blocos = [
        "# RQ 01 a 04 — números e rascunhos para a seção de Resultados",
        comum.paragrafo("Gerado por `python -m analise`. Todos os valores vêm das tabelas em "
                  "`resultados/tabelas/`; nenhum número aqui foi digitado à mão."),

        "## RQ 01 — Deployment Frequency",
        comum.paragrafo(
            f"Mediana de {valor(frequencia['mediana'])} releases por semana (IQR "
            f"{valor(frequencia['iqr'])}; Q1 {valor(frequencia['q1'])}, Q3 "
            f"{valor(frequencia['q3'])}) em {comum.quantos(frequencia['n'], 'repositório', 'repositórios')}. "
            f"{comum.quantos(sem_release, 'repositório não publicou', 'repositórios não publicaram')} "
            f"nenhuma release na janela e {'entra' if sem_release == 1 else 'entram'} na mediana "
            f"com zero; {comum.quantos(frequencia['ausentes'], 'ficou sem valor', 'ficaram sem valor')}."),

        "## RQ 02 — Lead Time: por que (a) e (b) divergem",
        comum.paragrafo(
            "A variante (a), por release, mede o intervalo inteiro coberto pela release: do commit "
            "mais antigo do `compare` até a publicação. A variante (b), por commit, mede cada "
            "commit até a publicação da sua release. Como (a) é definida pelo commit mais antigo e "
            "(b) pela mediana de todos eles, basta um commit antigo \"esquecido\" no intervalo — um "
            "branch retomado, um cherry-pick, um pull request parado — para (a) subir sem que o "
            "ritmo de trabalho tenha mudado. É por isso que as duas não medem a mesma coisa: (a) "
            "responde \"quanto tempo cabe dentro de uma entrega\" e (b), \"quanto tempo um commit "
            "típico espera para ser entregue\"."),
        comum.paragrafo(
            f"Medianas: (a) {valor(a_horas['mediana'])} h "
            f"({valor(dois['a_release']['dias']['mediana'])} d, IQR {valor(a_horas['iqr'])} h, "
            f"n = {a_horas['n']}) contra (b) {valor(b_horas['mediana'])} h "
            f"({valor(dois['b_commit']['dias']['mediana'])} d, IQR {valor(b_horas['iqr'])} h, "
            f"n = {b_horas['n']}). A razão (a)/(b) por repositório tem mediana "
            f"{valor(dois['razao_a_b']['mediana'])}× (IQR {valor(dois['razao_a_b']['iqr'])}, "
            f"n = {dois['razao_a_b']['n']})."),
        comum.paragrafo(f"Os {len(dois['maiores_razoes'])} repositórios com maior razão, inspecionados "
                  "em `releases.csv`:") if itens else
        comum.paragrafo("Nenhum repositório tem as duas variantes, então não há razão (a)/(b) a inspecionar."),
        *(["\n".join(itens)] if itens else []),
        comum.paragrafo(
            f"Em {dois['repositorios_com_commit_antigo_esquecido']} deles a release de maior "
            f"intervalo tem razão de pelo menos "
            f"{valor(LIMIAR_COMMIT_ESQUECIDO, 1)}× entre o intervalo da release e a mediana dos "
            "seus próprios commits, o indício de que um commit antigo — e não o ritmo de trabalho "
            "— define o Lead Time da variante (a)."),
        comum.paragrafo(
            f"Releases fora do Lead Time: {dois['releases_ignoradas_total']} de "
            f"{dois['releases_observadas']} observadas, detalhadas por motivo em "
            "`resultados/tabelas/rq02_releases_ignoradas.csv`. Nenhuma foi estimada nem tratada "
            "como intervalo zero."),

        "## RQ 03 — falha de pipeline não é falha em produção",
        comum.paragrafo(
            f"As duas variantes do Change Failure Rate medem objetos diferentes. A variante (a) é "
            f"um proxy de CI: falhas sobre {ci['runs_considerados']} workflow runs considerados "
            f"({ci['runs_ignorados']} ignorados, por estarem cancelados, em andamento ou com "
            f"conclusão desconhecida), com mediana {valor(ci['resumo']['mediana'])} (IQR "
            f"{valor(ci['resumo']['iqr'])}, n = {ci['resumo']['n']}). A variante (b) é um proxy de "
            f"entrega: releases seguidas em até 7 dias por uma release corretiva da mesma linha — "
            f"{entrega['releases_que_falharam']} de {entrega['releases_avaliadas']} releases "
            f"avaliadas, mediana {valor(entrega['resumo']['mediana'])} (IQR "
            f"{valor(entrega['resumo']['iqr'])}, n = {entrega['resumo']['n']})."),
        comum.paragrafo(
            "A diferença entre as duas é a própria interpretação da métrica. Um run vermelho é, na "
            "maior parte das vezes, um teste quebrado em um pull request: é barato, é detectado "
            "antes da entrega e muitas vezes é exatamente o CI fazendo o seu trabalho. Uma release "
            "seguida de uma corretiva em até 7 dias é um defeito que passou pelo pipeline e chegou "
            "ao usuário. Por isso a variante (a) tende a ser a mais alta das duas sem que isso "
            "signifique produção instável: ela conta falhas que nunca viraram incidente. Tratar as "
            "duas como a mesma métrica — e comparar qualquer uma delas direto com as faixas do "
            "relatório DORA, que falam de mudanças em produção — superestima a taxa de falha dos "
            f"repositórios. {entrega['releases_censuradas']} releases dos últimos 7 dias da janela "
            "não têm 7 dias observados e ficaram fora do denominador de (b), em vez de entrarem "
            "como sucesso."),

        "## RQ 04 — viés da censura no tempo de recuperação",
        comum.paragrafo(
            f"Mediana entre repositórios de {valor(recuperados['horas']['mediana'])} h "
            f"({valor(recuperados['dias']['mediana'])} d, IQR "
            f"{valor(recuperados['horas']['iqr'])} h, n = {recuperados['horas']['n']}), calculada "
            f"**apenas sobre episódios recuperados**: dos {episodios['total']} episódios de falha, "
            f"{episodios['recuperados']} foram recuperados — "
            f"{comum.quantos(episodios['inconsistentes'], 'deles tem', 'deles têm')} datas contraditórias "
            f"e também {'fica' if episodios['inconsistentes'] == 1 else 'ficam'} fora da mediana — e "
            f"{episodios['censurados']} ficaram censurados, "
            "sem nenhum sucesso posterior do mesmo workflow dentro da janela. A proporção censurada "
            f"por repositório tem mediana {valor(quatro['proporcao_censurada']['mediana'])} (IQR "
            f"{valor(quatro['proporcao_censurada']['iqr'])})."),
        comum.paragrafo(
            "Essa mediana subestima o tempo real de recuperação: justamente os episódios mais "
            "longos são os que não terminaram dentro da janela e, por isso, são os excluídos. Para "
            "medir o tamanho do viés, o limite inferior trata cada episódio censurado como "
            "recuperado no fim da observação (`observed_hours`), o maior valor que a janela permite "
            f"afirmar: a mediana sobe para {valor(limite['horas']['mediana'])} h "
            f"({valor(limite['dias']['mediana'])} d), uma diferença de "
            f"{valor(quatro['vies_da_censura_horas'])} h. O valor real está acima da primeira "
            "mediana, e mesmo esse limite ainda é otimista: um episódio censurado pode ter levado "
            "muito mais tempo do que o que sobrou da janela."),
    ]
    return "\n\n".join(bloco for bloco in blocos if bloco) + "\n"


def executar(dados, saida="resultados"):
    """Gera a tabela-síntese, as figuras e os números de censura das RQ 01 a 04."""
    saida = Path(saida)
    resultados = {"rq01": rq01(dados, saida), "rq02": rq02(dados, saida),
                  "rq03": rq03(dados, saida), "rq04": rq04(dados, saida)}
    tabela = sintese(resultados)
    comum.salvar_tabela(tabela, saida, "sintese_rq01_04")
    comum.salvar_tabela(resultados["rq02"]["releases_ignoradas"], saida,
                        "rq02_releases_ignoradas", casas=4)
    comum.salvar_tabela(resultados["rq02"]["maiores_razoes"], saida, "rq02_razao_lead_time")
    comum.salvar_tabela(cobertura_rq03(resultados["rq03"]), saida, "rq03_cobertura")
    comum.salvar_tabela(resultados["rq03"]["por_repositorio"], saida,
                        "rq03_cfr_entrega_por_repositorio")
    comum.salvar_tabela(censura_rq04(resultados["rq04"]), saida, "rq04_censura")
    comum.salvar_tabela(resultados["rq04"]["por_repositorio"], saida,
                        "rq04_recuperacao_por_repositorio")
    comum.salvar_texto(notas(resultados), saida, "notas_rq01_04")
    comum.salvar_json({"sintese": tabela, **resultados}, saida, "rq01_04")
    resultados["sintese"] = tabela
    return resultados
