"""Base comum das análises da Sprint 3: leitura dos CSVs e estatística descritiva.

Todas as RQs partem dos mesmos três arquivos em `data/processed/` e das mesmas
estatísticas. Aqui ficam a leitura com os tipos corretos (datas em UTC, vazios como
NaN, indicadores como booleano com NA) e `resumo`, que devolve mediana e IQR — nunca
média e desvio-padrão, como pede o enunciado.

Cada CSV declara as colunas obrigatórias e as opcionais. Uma coluna opcional ausente
entra como NaN, e cada RQ decide se recalcula o valor a partir das tabelas detalhadas
(`releases.csv` e `episodios_falha.csv`) em vez de usar o resumo por repositório.
"""
import json
import textwrap
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


DIRETORIO_PADRAO = Path("data/processed")
VERDADEIRO = {"true", "1", "sim", "yes", "t", "y"}
FALSO = {"false", "0", "nao", "não", "no", "f", "n"}
# A barra invertida vem primeiro: as demais trocas introduzem barras.
ESCAPES = (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
           ("_", r"\_"), ("{", r"\{"), ("}", r"\}"), ("~", r"\textasciitilde{}"),
           ("^", r"\textasciicircum{}"))


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
    apelidos=(("full_name", "repository"), ("cfr_entrega", "delivery_change_failure_rate"),
              ("change_failure_rate_delivery", "delivery_change_failure_rate")))

# Uma release por linha: intervalo de commits do Lead Time (a) e veredito do CFR (b).
RELEASES = Tabela(
    arquivo="releases.csv",
    obrigatorias=("repository",),
    numericas=("release_id", "commits", "measured_commits", "lead_time_hours",
               "median_commit_lead_time_hours"),
    datas=("published_at", "first_commit_author_date", "last_commit_author_date"),
    booleanas=("corrective", "censored", "failed"),
    texto=("tag_name", "previous_tag_name", "status", "comparison_status", "fixed_by_tag_name"),
    apelidos=(("full_name", "repository"),))

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
    quadro = pd.read_csv(caminho, dtype="object", keep_default_na=True)
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
