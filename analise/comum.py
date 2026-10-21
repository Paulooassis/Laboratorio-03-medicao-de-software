"""Base comum das análises da Sprint 3: leitura, estatística e exportação.

Todas as RQs partem dos mesmos três arquivos em `data/processed/` e das mesmas
estatísticas. Aqui ficam a leitura com os tipos corretos (datas em UTC, vazios como
NaN, indicadores como booleano com NA), mediana/IQR, testes não paramétricos,
efeitos e correção de Holm. O contrato está em `docs/contrato_csv_analise.md`.

Cada CSV declara as colunas obrigatórias e as opcionais. Uma coluna opcional ausente
entra como NaN, e cada RQ decide se recalcula o valor a partir das tabelas detalhadas
(`releases.csv` e `episodios_falha.csv`) em vez de usar o resumo por repositório.
"""
import json
import math
import textwrap
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

from validacao.concordancia import landis_koch as _landis_koch

DIRETORIO_PADRAO = Path("data/processed")
VERDADEIRO = {"true", "1", "sim", "yes", "t", "y"}
FALSO = {"false", "0", "nao", "não", "no", "f", "n"}
# A barra invertida vem primeiro: as demais trocas introduzem barras.
ESCAPES = (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
           ("_", r"\_"), ("{", r"\{"), ("}", r"\}"), ("~", r"\textasciitilde{}"),
           ("^", r"\textasciicircum{}"))
UNDEFINED = "indefinido"


@dataclass(frozen=True)
class Tabela:
    """Contrato de um CSV: nome do arquivo e o papel de cada coluna conhecida."""
    arquivo: str
    obrigatorias: tuple
    numericas: tuple = ()
    datas: tuple = ()
    booleanas: tuple = ()
    texto: tuple = ()
    apelidos: tuple = ()

    @property
    def colunas(self):
        return self.obrigatorias + self.numericas + self.datas + self.booleanas + self.texto


# Um repositório por linha: métricas DORA e a contabilidade do que ficou de fora.
REPOSITORIOS = Tabela(
    arquivo="repositorios.csv",
    obrigatorias=("repository",),
    numericas=("stars", "contributors", "releases", "releases_per_week",
               "release_lead_time_hours", "commit_lead_time_hours",
               "releases_no_previous", "releases_compare_not_found", "releases_compare_error",
               "releases_no_new_commits", "releases_no_commit_dates", "releases_no_date",
               "considered_runs", "ignored_runs", "change_failure_rate",
               "delivery_change_failure_rate", "recovery_hours", "censored_episodes",
               "median_score"),
    datas=("created_at", "window_start", "window_end"),
    booleanas=("collection_complete",),
    texto=("language", "deployment_frequency_level", "lead_time_level",
           "change_failure_rate_level", "recovery_time_level", "overall"),
    # Os nomes à esquerda são os de `data/processed/repositorios.csv` gerado pelo
    # pipeline; os da direita, os usados nas análises. Sem esses apelidos a análise lê o
    # CSV real sem erro nenhum e devolve estatísticas vazias, que é a pior falha possível.
    apelidos=(("full_name", "repository"),
              ("deployment_frequency_per_week", "releases_per_week"),
              ("lead_time_a_hours", "release_lead_time_hours"),
              ("lead_time_b_hours", "commit_lead_time_hours"),
              ("cfr_a", "change_failure_rate"), ("cfr_a_runs", "considered_runs"),
              ("runs_ignored", "ignored_runs"),
              ("cfr_b", "delivery_change_failure_rate"),
              ("cfr_entrega", "delivery_change_failure_rate"),
              ("change_failure_rate_delivery", "delivery_change_failure_rate"),
              ("recovery_censored", "censored_episodes")))

# Uma release por linha: intervalo de commits do Lead Time (a) e veredito do CFR (b).
RELEASES = Tabela(
    arquivo="releases.csv",
    obrigatorias=("repository",),
    numericas=("release_id", "commits", "measured_commits", "lead_time_hours",
               "median_commit_lead_time_hours"),
    datas=("published_at", "first_commit_author_date", "last_commit_author_date"),
    booleanas=("corrective", "censored", "failed"),
    texto=("tag_name", "previous_tag_name", "status", "comparison_status", "fixed_by_tag_name"),
    # Idem: nomes de `data/processed/releases.csv` à esquerda. `last_commit_author_date`
    # não é exportado pelo pipeline, então o intervalo de commits da RQ 02 fica ausente
    # em vez de estimado.
    apelidos=(("full_name", "repository"), ("lead_time_status", "status"),
              ("lead_time_a_hours", "lead_time_hours"),
              ("lead_time_b_hours", "median_commit_lead_time_hours"),
              ("cfr_b_censored", "censored"), ("cfr_b_failed", "failed")))

# Um episódio de falha por linha: da primeira falha ao primeiro sucesso do mesmo workflow.
EPISODIOS = Tabela(
    arquivo="episodios_falha.csv",
    obrigatorias=("repository",),
    numericas=("workflow_id", "failure_run_id", "failures", "recovery_hours", "observed_hours"),
    datas=("started_at", "recovered_at"),
    booleanas=("recovered", "censored", "inconsistent"),
    apelidos=(("full_name", "repository"),))


@dataclass(frozen=True)
class Dados:
    """Os três CSVs já tipados, como entram em toda análise da sprint."""
    repositorios: pd.DataFrame
    releases: pd.DataFrame
    episodios: pd.DataFrame
    diretorio: Path = DIRETORIO_PADRAO


def para_booleano(serie):
    """`True`/`False` em qualquer caixa; o que não decide vira NA, nunca False."""
    if serie.dtype == bool:
        return serie.astype("boolean")
    texto = serie.astype("string").str.strip().str.lower()
    return texto.map(lambda valor: True if valor in VERDADEIRO else
                     (False if valor in FALSO else pd.NA)).astype("boolean")


def serie_numerica(valores):
    """Série de ponto flutuante; o que não é número vira NaN, sem erro."""
    serie = valores if isinstance(valores, pd.Series) else pd.Series(list(valores), dtype="object")
    return pd.to_numeric(serie, errors="coerce").astype("float64")


def ler(diretorio, tabela):
    """Lê um CSV do contrato: renomeia apelidos, converte tipos e completa com NaN."""
    caminho = Path(diretorio) / tabela.arquivo
    if not caminho.is_file():
        raise FileNotFoundError(f"{caminho} não existe; gere os CSVs do pipeline antes da análise.")
    quadro = pd.read_csv(caminho, dtype="object", keep_default_na=True, encoding="utf-8-sig")
    quadro = quadro.replace(r"^\s*$", float("nan"), regex=True)
    quadro = quadro.rename(columns={velho: novo for velho, novo in tabela.apelidos
                                    if velho in quadro.columns and novo not in quadro.columns})
    ausentes = [coluna for coluna in tabela.obrigatorias if coluna not in quadro.columns]
    if ausentes:
        raise ValueError(f"{caminho} não tem a(s) coluna(s) {', '.join(ausentes)}.")
    for coluna in tabela.colunas:
        if coluna not in quadro.columns:
            quadro[coluna] = pd.NA
    for coluna in tabela.numericas:
        quadro[coluna] = serie_numerica(quadro[coluna])
    for coluna in tabela.datas:
        quadro[coluna] = pd.to_datetime(quadro[coluna], utc=True, errors="coerce", format="mixed")
    for coluna in tabela.booleanas:
        quadro[coluna] = para_booleano(quadro[coluna])
    for coluna in tabela.obrigatorias + tabela.texto:
        quadro[coluna] = quadro[coluna].astype("string").str.strip()
    return quadro.loc[:, list(dict.fromkeys(tabela.colunas))]


def carregar(diretorio=DIRETORIO_PADRAO):
    """Os três CSVs da análise; erro explícito quando algum falta ou está incompleto."""
    diretorio = Path(diretorio)
    return Dados(repositorios=ler(diretorio, REPOSITORIOS), releases=ler(diretorio, RELEASES),
                 episodios=ler(diretorio, EPISODIOS), diretorio=diretorio)


def resumo(valores):
    """n, ausentes, mediana, Q1, Q3 e IQR de uma série; sem média nem desvio-padrão.

    Q1 e Q3 usam interpolação linear (quantis do tipo 7, padrão do pandas e do R).
    Série sem nenhum valor devolve n = 0 e NaN nas estatísticas, em vez de erro.
    """
    serie = serie_numerica(valores)
    presentes = serie.dropna()
    if presentes.empty:
        return {"n": 0, "ausentes": int(serie.size), "mediana": float("nan"),
                "q1": float("nan"), "q3": float("nan"), "iqr": float("nan")}
    q1, q3 = (float(presentes.quantile(quantil)) for quantil in (0.25, 0.75))
    return {"n": int(presentes.size), "ausentes": int(serie.size - presentes.size),
            "mediana": float(presentes.median()), "q1": q1, "q3": q3, "iqr": q3 - q1}


def epsilon_quadrado(H, n):
    """ε² = H / (n − 1), com n válido total do Kruskal-Wallis, sem truncamento.

    Sem H ou com n ≤ 1, o efeito é indefinido (NaN).
    """
    if H is None or pd.isna(H) or n <= 1:
        return float("nan")
    if not math.isfinite(H) or H < 0 or not math.isfinite(n):
        raise ValueError("H deve ser finito e não negativo; n deve ser finito.")
    return float(H / (n - 1))


def interpretar_cliffs_delta(delta):
    """Magnitude de |δ| segundo Romano et al. (2006); o sinal indica a direção."""
    if delta is None or pd.isna(delta):
        return UNDEFINED
    if not math.isfinite(delta) or abs(delta) > 1:
        raise ValueError("Cliff's delta deve estar entre -1 e 1.")
    for limite, rotulo in ((0.147, "desprezível"), (0.33, "pequeno"), (0.474, "médio")):
        if abs(delta) < limite:
            return rotulo
    return "grande"


def cliffs_delta(x, y):
    """δ = 2 U₁ / (n₁ n₂) − 1; positivo quando x tende a ser maior que y.

    Ausentes são removidos em cada amostra independentemente; amostra vazia
    resulta em NaN. Empates contam como meia vitória no U₁ retornado pelo SciPy.
    O método assintótico evita calcular p exato só para obter U₁.
    """
    x, y = (serie_numerica(amostra).dropna() for amostra in (x, y))
    if x.empty or y.empty:
        return float("nan")
    u = stats.mannwhitneyu(x, y, alternative="two-sided", method="asymptotic").statistic
    return float(2 * u / (len(x) * len(y)) - 1)


def mann_whitney(x, y):
    """Mann-Whitney bilateral com método auto do SciPy e efeito de Cliff.

    O método é exato para amostras pequenas sem empates e assintótico com
    correção de empates nos demais casos. Amostra vazia produz NaN em U e p.
    """
    x, y = (serie_numerica(amostra).dropna() for amostra in (x, y))
    u, p = float("nan"), float("nan")
    if not x.empty and not y.empty:
        resultado = stats.mannwhitneyu(x, y, alternative="two-sided", method="auto")
        u, p = float(resultado.statistic), float(resultado.pvalue)
    delta = float(2 * u / (len(x) * len(y)) - 1) if len(x) * len(y) else float("nan")
    return {"n1": len(x), "n2": len(y), "u": u, "p": p, "delta": delta,
            "interpretacao": interpretar_cliffs_delta(delta)}


def kruskal_wallis(*grupos):
    """Kruskal-Wallis com correção de empates, p e ε² sobre o n válido total.

    Exige dois ou mais grupos. Grupo vazio torna o teste indefinido; se todos
    os valores são iguais, retorna H = 0, p = 1 e ε² = 0 (nenhuma diferença).
    """
    if len(grupos) < 2:
        raise ValueError("Kruskal-Wallis exige pelo menos dois grupos.")
    amostras = [serie_numerica(grupo).dropna() for grupo in grupos]
    n = sum(len(amostra) for amostra in amostras)
    h, p = float("nan"), float("nan")
    if all(not amostra.empty for amostra in amostras):
        if pd.concat(amostras).nunique() == 1:
            h, p = 0.0, 1.0
        else:
            resultado = stats.kruskal(*amostras)
            h, p = float(resultado.statistic), float(resultado.pvalue)
    return {"n": n, "h": h, "p": p, "epsilon_quadrado": epsilon_quadrado(h, n)}


def holm(p_valores, alpha=0.05):
    """Corrige uma família de testes com multipletests(method='holm').

    Retorna DataFrame com p, p_holm e rejeita, na ordem/índice de entrada.
    Testes indefinidos não entram na família e permanecem ausentes, inclusive
    na decisão. A família inclui todos os p válidos, mesmo não significativos.
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha deve estar entre 0 e 1, exclusive.")
    p = serie_numerica(p_valores)
    if ((p < 0) | (p > 1)).any():
        raise ValueError("p-valores devem estar entre 0 e 1.")
    saida = pd.DataFrame({"p": p, "p_holm": float("nan"),
                          "rejeita": pd.Series(pd.NA, index=p.index, dtype="boolean")})
    validos = p.notna()
    if validos.any():
        rejeita, corrigidos, _, _ = multipletests(p[validos], alpha=alpha, method="holm")
        saida.loc[validos, "p_holm"] = corrigidos
        saida.loc[validos, "rejeita"] = rejeita
    return saida


def landis_koch(kappa):
    """Reutiliza a escala da validação na RQ 07; kappa ausente é indefinido."""
    if kappa is None or pd.isna(kappa) or not math.isfinite(kappa):
        return UNDEFINED
    return _landis_koch(kappa)


def escapar(texto):
    """Escapa no LaTeX o que aparece em nome de repositório e de tag (`_`, `&`, `#`)."""
    for alvo, troca in ESCAPES:
        texto = texto.replace(alvo, troca)
    return texto


def celula(valor, casas):
    """Valor de uma célula no formato do artigo: vírgula decimal e travessão no ausente."""
    if valor is None or valor is pd.NA or valor is pd.NaT or (isinstance(valor, float)
                                                             and valor != valor):
        return "--"
    if pd.api.types.is_bool(valor):
        return "sim" if valor else "não"
    if pd.api.types.is_integer(valor):
        return numero(valor, 0)
    if pd.api.types.is_float(valor):
        return numero(valor, casas)
    return escapar(str(valor))


def tabela_latex(quadro, casas=3):
    """Tabela em LaTeX puro (`tabular` com `\\hline`), sem pacote extra no template da SBC."""
    alinhamento = "".join("l" if indice == 0 else "r" for indice in range(len(quadro.columns)))
    cabecalho = " & ".join(escapar(str(coluna)) for coluna in quadro.columns)
    corpo = [" & ".join(celula(valor, casas) for valor in linha)
             for linha in quadro.itertuples(index=False, name=None)]
    return "\n".join([f"\\begin{{tabular}}{{{alinhamento}}}", "\\hline", f"{cabecalho} \\\\",
                       "\\hline", *(f"{linha} \\\\" for linha in corpo), "\\hline",
                       "\\end{tabular}", ""])


def salvar_tabela(quadro, diretorio, nome, casas=3):
    """Grava a tabela em `resultados/tabelas/` em `.csv` e em `.tex`, pronta para o `\\input{}`."""
    diretorio = Path(diretorio) / "tabelas"
    diretorio.mkdir(parents=True, exist_ok=True)
    csv, tex = diretorio / f"{nome}.csv", diretorio / f"{nome}.tex"
    quadro.to_csv(csv, index=False)
    tex.write_text(tabela_latex(quadro, casas), encoding="utf-8")
    return csv, tex


def paragrafo(texto, largura=90, recuo=""):
    """Reflui um parágrafo do rascunho: o texto é escrito em uma linha e quebrado aqui."""
    return textwrap.fill(" ".join(texto.split()), largura, subsequent_indent=recuo)


def quantos(quantidade, singular, plural):
    """Concordância de número nos rascunhos: "1 repositório", "3 repositórios"."""
    return f"{quantidade} {singular if quantidade == 1 else plural}"


def salvar_csv(quadro, diretorio, nome):
    """Grava em `resultados/<nome>.csv` um artefato de dados, não uma tabela do artigo."""
    diretorio = Path(diretorio)
    diretorio.mkdir(parents=True, exist_ok=True)
    caminho = diretorio / f"{nome}.csv"
    quadro.to_csv(caminho, index=False)
    return caminho


def salvar_texto(conteudo, diretorio, nome):
    """Grava os rascunhos de texto do artigo em `resultados/texto/<nome>.md`."""
    diretorio = Path(diretorio) / "texto"
    diretorio.mkdir(parents=True, exist_ok=True)
    caminho = diretorio / f"{nome}.md"
    caminho.write_text(conteudo if conteudo.endswith("\n") else conteudo + "\n", encoding="utf-8")
    return caminho


def numero(valor, casas=2):
    """Número no formato do artigo (vírgula decimal); ausente vira travessão."""
    if valor is None or valor != valor:
        return "--"
    inteiro, _, decimal = f"{valor:,.{casas}f}".partition(".")
    inteiro = inteiro.replace(",", ".")
    return f"{inteiro},{decimal}" if decimal else inteiro


def serializavel(valor):
    """Converte tipos do pandas/NumPy para JSON; NaN e NaT viram null, não `NaN`."""
    if isinstance(valor, dict):
        return {str(chave): serializavel(item) for chave, item in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [serializavel(item) for item in valor]
    if isinstance(valor, pd.DataFrame):
        return serializavel(valor.to_dict(orient="records"))
    if valor is None or valor is pd.NA or valor is pd.NaT:
        return None
    if isinstance(valor, (bool, str)):
        return valor
    if isinstance(valor, (int, float)) or hasattr(valor, "item"):
        numero_ = valor.item() if hasattr(valor, "item") else valor
        if isinstance(numero_, float) and numero_ != numero_:
            return None
        return numero_
    return str(valor)


def salvar_json(conteudo, diretorio, nome):
    """Grava os números da análise em `resultados/<nome>.json`, prontos para o artigo."""
    diretorio = Path(diretorio)
    diretorio.mkdir(parents=True, exist_ok=True)
    caminho = diretorio / f"{nome}.json"
    caminho.write_text(json.dumps(serializavel(conteudo), ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    return caminho
