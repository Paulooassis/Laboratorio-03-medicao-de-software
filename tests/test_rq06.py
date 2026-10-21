"""Dados sintéticos somente para verificar a análise; não são resultados do estudo."""
import math

import numpy as np
import pandas as pd
import pytest

from analise import comum, rq06
from analise.__main__ import ANALISES, main


@pytest.fixture
def dados(tmp_path):
    n = 60
    repos = pd.DataFrame({
        "repository": [f"teste/r{i}" for i in range(n)],
        "language": ["A"] * 20 + ["B"] * 20 + ["C"] * 20,
        "stars": range(n), "contributors": range(n),
        "created_at": [f"{1960+i}-01-01T00:00:00Z" for i in range(n)],
        "window_end": "2025-12-31T00:00:00Z",
        "releases_per_week": range(n), "release_lead_time_hours": range(n),
        "commit_lead_time_hours": range(n), "change_failure_rate": np.arange(n) / n,
        "delivery_change_failure_rate": np.arange(n) / n, "recovery_hours": range(n)})
    repos.to_csv(tmp_path / "repositorios.csv", index=False)
    for arquivo in ("releases.csv", "episodios_falha.csv"):
        (tmp_path / arquivo).write_text("repository\n", encoding="utf-8")
    return comum.carregar(tmp_path)


def test_manual_kw_and_two_group_mw():
    quadro = pd.DataFrame({"df": range(1, 16)})
    grupos = pd.Series(["A"] * 5 + ["B"] * 5 + ["C"] * 5)
    teste, _ = rq06.teste_global(quadro, grupos, "df", "linguagem")
    # Postos médios 3,8,13; H=12/(15*16)*(15²/5+40²/5+65²/5)-48=12,5.
    assert teste["n"] == 15 and teste["h"] == pytest.approx(12.5)
    assert teste["p"] == pytest.approx(math.exp(-12.5 / 2))  # χ² com 2 graus.
    assert teste["epsilon_quadrado"] == pytest.approx(12.5 / 14)
    assert teste["interpretacao"] == "grande"
    teste, _ = rq06.teste_global(quadro.iloc[:4], pd.Series(["A", "A", "B", "B"]),
                                "df", "linguagem")
    assert teste["teste"] == "MW" and teste["u"] == 0
    assert teste["delta"] == -1 and teste["p"] == pytest.approx(1 / 3)
    assert math.isnan(teste["h"]) and math.isnan(teste["epsilon_quadrado"])


def test_quartile_boundaries_ties_constant_and_missing():
    grupos, cortes = rq06.quartis(pd.Series(range(1, 9)), "estrelas", "estrelas")
    assert [linha["limite_superior"] for linha in cortes] == [2.75, 4.5, 6.25, 8]
    assert list(grupos) == ["Q1", "Q1", "Q2", "Q2", "Q3", "Q3", "Q4", "Q4"]
    grupos, cortes = rq06.quartis(pd.Series([0] * 6 + [1] * 2 + [None]), "x", "x")
    assert len(cortes) < 4 and grupos.iloc[:6].nunique() == 1
    assert pd.isna(grupos.iloc[-1])
    grupos, cortes = rq06.quartis(pd.Series([2, 2, None]), "x", "x")
    assert len(cortes) == 1 and list(grupos[:2]) == ["Q1", "Q1"]
    grupos, cortes = rq06.quartis(pd.Series([None]), "x", "x")
    assert grupos.isna().all() and cortes == []
    with pytest.raises(ValueError):
        rq06.quartis(pd.Series([float("inf")]), "x", "x")


def test_language_minimum_rare_and_missing():
    grupos, cortes = rq06.linguagens(pd.Series(["A"] * 31 + ["B"] * 19 + ["C"] * 11
        + ["D"] * 10 + ["E"] * 10 + ["F"] * 8 + ["G"] * 10 + [None]))
    assert {linha["grupo"]: linha["n"] for linha in cortes} == {"A": 31, "B": 19, "Outras": 49}
    assert pd.isna(grupos.iloc[-1])
    # Outras n=4 absorve B (15), em vez de criar grupo abaixo do mínimo.
    _, cortes = rq06.linguagens(pd.Series(["A"] * 30 + ["B"] * 15 + ["C"] * 4))
    assert {linha["grupo"]: linha["n"] for linha in cortes} == {"A": 30, "Outras": 19}
    _, cortes = rq06.linguagens(pd.Series(["A"] * 20 + ["B"] * 20))
    assert len(cortes) == 2  # não cria Outras vazio


def test_age_is_at_window_end_and_cuts_do_not_follow_metric_missingness(dados):
    grupos, cortes = rq06.definir_grupos(dados.repositorios)
    antes = cortes.copy()
    dados.repositorios.loc[:20, "recovery_hours"] = np.nan
    dados.repositorios.loc[:20, "release_lead_time_hours"] = np.nan
    novamente, depois = rq06.definir_grupos(dados.repositorios)
    pd.testing.assert_frame_equal(antes, depois)
    for fator in grupos:
        pd.testing.assert_series_equal(grupos[fator], novamente[fator])
    idade_maxima = (pd.Timestamp("2025-12-31", tz="UTC") - pd.Timestamp("1960-01-01", tz="UTC")).days
    assert cortes[cortes.fator.eq("idade")].limite_superior.max() == idade_maxima
    quadro, _ = rq06.base_metricas(dados)
    tabela, _ = rq06.familia(quadro, grupos, rq06.PRINCIPAIS, "principal")
    assert tabela[tabela.metrica.eq("recuperacao")].n.max() == 39
    assert tabela[tabela.metrica.eq("df")].n.max() == 60


def test_main_16_and_supplement_8_are_independent_holm_families(dados, monkeypatch):
    quadro, _ = rq06.base_metricas(dados)
    grupos, _ = rq06.definir_grupos(dados.repositorios)
    # Todos os testes com p=0,01: Holm é 0,16 na principal e 0,08 na suplementar.
    monkeypatch.setattr(comum, "kruskal_wallis", lambda *args:
        {"n": sum(map(len, args)), "h": 3.0, "p": 0.01, "epsilon_quadrado": 0.05})
    principal, _ = rq06.familia(quadro, grupos, rq06.PRINCIPAIS, "principal")
    suplemento, _ = rq06.familia(quadro, grupos, rq06.SUPLEMENTARES, "suplementar")
    assert len(principal) == 16 and principal.p_holm.eq(0.16).all()
    assert len(suplemento) == 8 and suplemento.p_holm.eq(0.08).all()
    assert not principal.rejeita.any() and not suplemento.rejeita.any()


def test_posthoc_gate_and_holm_within_factor_across_metrics():
    quadro = pd.DataFrame({"df": range(1, 16), "lt_a": range(1, 16)})
    grupos = {"estrelas": pd.Series(["A"] * 5 + ["B"] * 5 + ["C"] * 5)}
    tabela, selecoes = rq06.familia(quadro, grupos, ["df", "lt_a"], "principal")
    pares = rq06.posthoc(tabela, selecoes)
    assert len(pares) == 6
    # Cada par separado: U=0, p bilateral=2/C(10,5)=1/126; seis comparações.
    assert pares.p_holm.astype(float).to_numpy() == pytest.approx([6 / 126] * 6)
    assert pares.delta.eq(-1).all() and pares.rejeita.all()
    assert "favorável a B" in pares[pares.metrica.eq("df")].iloc[0].direcao
    assert "favorável a A" in pares[pares.metrica.eq("lt_a")].iloc[0].direcao
    tabela["rejeita"] = False
    assert rq06.posthoc(tabela, selecoes).empty
    assert rq06.direcao(0, "df") == "sem dominância"
    assert rq06.direcao(np.nan, "df") == "indefinida"


def test_type_labels_collapse_releases_and_keep_unlabelled_missing(dados, tmp_path):
    arquivo = tmp_path / "rotulos_grupo.csv"
    arquivo.write_text("repository,project_type\nTESTE/R0,cli\nteste/r0,cli\n"
                       "teste/r1,library/framework\nteste/r2,other\n", encoding="utf-8")
    grupos, origem = rq06.tipos_projeto(dados.repositorios, arquivo)
    assert grupos.notna().sum() == 2 and grupos.iloc[0] == "cli"
    assert "provisórios" in origem and "1 do tipo other" in origem
    arquivo.write_text("repository,project_type\nteste/r0,cli\nteste/r0,application/service\n",
                       encoding="utf-8")
    with pytest.raises(ValueError, match="conflitantes"):
        rq06.tipos_projeto(dados.repositorios, arquivo)
    assert rq06.tipos_projeto(dados.repositorios, tmp_path / "ausente.csv")[0].isna().all()


def test_small_type_group_uses_two_largest_with_own_n():
    quadro = pd.DataFrame({"df": range(14)})
    grupos = pd.Series(["cli"] * 2 + ["library/framework"] * 7 + ["application/service"] * 5)
    teste, conjuntos = rq06.teste_global(quadro, grupos, "df", "tipo", exploratorio=True)
    assert teste["teste"] == "MW" and teste["n"] == 12
    assert "cli" not in conjuntos and "dois maiores" in teste["restricao"]
    teste, _ = rq06.teste_global(quadro, grupos, "df", "tipo")
    assert math.isnan(teste["p"]) and "n < 5" in teste["status"]


def test_constant_and_insufficient_data_are_explicit():
    quadro = pd.DataFrame({"df": [1] * 15})
    grupos = pd.Series(["A"] * 5 + ["B"] * 5 + ["C"] * 5)
    teste, _ = rq06.teste_global(quadro, grupos, "df", "x")
    assert teste["h"] == 0 and teste["p"] == 1 and teste["epsilon_quadrado"] == 0
    teste, _ = rq06.teste_global(quadro, pd.Series([pd.NA] * 15), "df", "x")
    assert teste["n"] == 0 and math.isnan(teste["p"])


@pytest.mark.parametrize("valor,nome", [(0, "desprezível"), (0.01, "pequeno"),
    (0.08, "médio"), (0.26, "grande"), (np.nan, "indefinido")])
def test_epsilon_thresholds(valor, nome):
    assert rq06.interpretar_epsilon(valor) == nome


def test_no_fallback_to_b_and_invalid_metrics_rejected(dados):
    dados.repositorios["release_lead_time_hours"] = np.nan
    quadro, _ = rq06.base_metricas(dados)
    assert quadro.lt_a.isna().all() and quadro.lt_b.notna().all()
    dados.repositorios.loc[0, "commit_lead_time_hours"] = -1
    quadro, _ = rq06.base_metricas(dados)
    assert quadro.loc[0, "lt_b"] == -1
    assert quadro.attrs["duracoes_negativas"] == {"lt_b": 1}
    assert dados.repositorios.loc[0, "commit_lead_time_hours"] == -1
    dados.repositorios.loc[0, "change_failure_rate"] = 1.5
    with pytest.raises(ValueError, match="CFR"):
        rq06.base_metricas(dados)
    dados.repositorios.loc[0, "change_failure_rate"] = np.inf
    with pytest.raises(ValueError, match="finita"):
        rq06.base_metricas(dados)


def test_boxplots_preserve_zero_and_negative_lt_and_bound_cfr(tmp_path, monkeypatch):
    figuras = []
    monkeypatch.setattr(rq06.estilo, "salvar", lambda fig, *_: figuras.append(fig))
    conjuntos = {"A": pd.Series([-2, 0, 1]), "B": pd.Series([2, 3, 4])}
    teste = {"metrica": "lt_b", "teste": "MW", "delta": -0.5, "familia": "suplementar",
             "fator": "idade", "p_holm": 0.01, "n": 6}
    rq06.boxplot(conjuntos, teste, tmp_path)
    assert figuras[-1].axes[0].get_yscale() == "symlog"
    assert figuras[-1].axes[0].get_ylim()[0] < -2
    assert "δ=" in figuras[-1].axes[0].get_title()
    conjuntos = {"A": pd.Series([0, 0.1, 0.2]), "B": pd.Series([0.5, 0.8, 1])}
    rq06.boxplot(conjuntos, {**teste, "metrica": "cfr_b"}, tmp_path)
    assert figuras[-1].axes[0].get_ylim() == (0, 1)
    for figura in figuras:
        rq06.estilo.plt.close(figura)


def test_registered_cli_generates_only_requested_artifacts(dados, tmp_path, monkeypatch):
    # A ausência do arquivo humano não bloqueia a análise dos metadados.
    original = rq06.tipos_projeto
    monkeypatch.setattr(rq06, "tipos_projeto", lambda repos:
        original(repos, tmp_path / "rotulos_ausentes.csv"))
    saida = tmp_path / "resultados"
    assert ANALISES["rq06"] is rq06.executar
    assert main(["--dados", str(dados.diretorio), "--saida", str(saida), "--analise", "rq06"]) == 0
    assert len(list((saida / "tabelas").glob("rq06_*.csv"))) == 5
    assert len(list((saida / "tabelas").glob("rq06_*.tex"))) == 5
    assert not list(saida.glob("*.json")) and not list(saida.glob("*.csv"))
    principal = pd.read_csv(saida / "tabelas/rq06_testes_principal.csv")
    assert len(principal) == 16
    assert principal.n.eq(60).all()
    exploratoria = pd.read_csv(saida / "tabelas/rq06_testes_exploratoria.csv")
    assert len(exploratoria) == 4 and exploratoria.n.eq(0).all()
    assert exploratoria.p_holm.isna().all()
    pdfs = list((saida / "figuras").glob("rq06_*.pdf"))
    assert len(pdfs) == int(principal.rejeita.sum()) + 8
    assert all(arquivo.read_bytes().startswith(b"%PDF-") for arquivo in pdfs)
    texto = (saida / "texto/notas_rq06.md").read_text(encoding="utf-8")
    assert "60 repositórios" in texto and "Rótulos de tipo ausentes" in texto
    latex = (saida / "tabelas/rq06_testes_principal.tex").read_text(encoding="utf-8")
    assert r"\varepsilon" in latex and "p Holm" in latex


def test_empty_csvs_do_not_invent_test_results(tmp_path, monkeypatch):
    for nome in ("repositorios.csv", "releases.csv", "episodios_falha.csv"):
        (tmp_path / nome).write_text("repository\n", encoding="utf-8")
    monkeypatch.setattr(rq06, "tipos_projeto", lambda repos:
        (pd.Series(pd.NA, index=repos.index, dtype="string"), "sem rótulos"))
    figuras = tmp_path / "saida/figuras"
    figuras.mkdir(parents=True)
    obsoleta = figuras / "rq06_principal_linguagem_df.pdf"
    obsoleta.write_bytes(b"resultado anterior")
    outra_rq = figuras / "rq05_df_cfr_a.pdf"
    outra_rq.write_bytes(b"outra analise")
    resultado = rq06.executar(comum.carregar(tmp_path), tmp_path / "saida")
    assert all(tabela.p.isna().all() for tabela in resultado["testes"].values())
    assert resultado["posthoc"].empty
    assert not obsoleta.exists() and outra_rq.read_bytes() == b"outra analise"
