"""Amostras sintéticas exclusivas dos testes; resultados empíricos usam os CSVs do estudo."""
import json
import math

import pandas as pd
import pytest

from analise import comum, estilo, rq05
from analise.__main__ import ANALISES, main


@pytest.fixture
def dados(tmp_path):
    (tmp_path / "repositorios.csv").write_text(
        "repository,releases_per_week,change_failure_rate,delivery_change_failure_rate\n"
        "owner/um,0,0.1,0.2\nowner/dois,1,0.3,0.4\n"
        "owner/tres,2,0.2,0.6\nowner/quatro,3,0.4,0.8\n", encoding="utf-8")
    # Datas fora de ordem; intervalos por repositório: 20, 10, 5 e 1 dia.
    (tmp_path / "releases.csv").write_text(
        "repository,release_id,published_at\n"
        "owner/um,1,2025-01-21T00:00:00Z\nowner/um,2,2025-01-01T00:00:00Z\n"
        "owner/dois,3,2025-01-01T00:00:00Z\nowner/dois,4,2025-01-11T00:00:00Z\n"
        "owner/tres,5,2025-01-01T00:00:00Z\nowner/tres,6,2025-01-06T00:00:00Z\n"
        "owner/quatro,7,2025-01-01T00:00:00Z\nowner/quatro,8,2025-01-02T00:00:00Z\n",
        encoding="utf-8")
    (tmp_path / "episodios_falha.csv").write_text("repository\n", encoding="utf-8")
    return comum.carregar(tmp_path)


def test_manual_rank_calculation_and_effective_n():
    # Postos x=[1,2,3,4], y=[1,3,2,4]: Σd²=2; ρ=1-6*2/(4*15)=0,8.
    teste = rq05.correlacao([0, 1, 2, 3], [0.1, 0.3, 0.2, 0.4])
    assert teste["n"] == 4 and teste["zeros_df"] == 1
    assert teste["rho"] == pytest.approx(0.8)
    # n=4: a aproximação t bilateral usada pelo SciPy resulta em p=0,2.
    assert teste["p"] == pytest.approx(0.2)
    assert teste["forca"] == "forte"


def test_pairwise_missing_values_keep_different_samples():
    df = [0, 1, None, 3, 4]
    a = rq05.correlacao(df, [0.1, 0.2, 0.8, 0.3, None])
    b = rq05.correlacao(df, [None, 0.4, 0.6, 0.3, 0.2])
    assert (a["n"], b["n"]) == (3, 3)
    assert a["rho"] == pytest.approx(1) and b["rho"] == pytest.approx(-1)
    pares = rq05.pares_validos(pd.Series([1, 2], index=["a", "b"]),
                             pd.Series([0.2, 0.1], index=["b", "a"]))
    assert list(pares.cfr) == [0.1, 0.2]


def test_tied_ranks():
    # Postos [1,2.5,2.5,4] e [1,2,3,4]: ρ=4,5/sqrt(4,5*5).
    teste = rq05.correlacao([0, 1, 1, 2], [0, 0.2, 0.4, 0.8])
    assert teste["rho"] == pytest.approx(4.5 / math.sqrt(4.5 * 5))


@pytest.mark.parametrize("x,y,n", [([], [], 0), ([1], [0.2], 1),
    ([0, 0, 0], [0.1, 0.2, 0.3], 3), ([0, 1, 2], [0.2, 0.2, 0.2], 3)])
def test_undefined_inputs_keep_n(x, y, n):
    teste = rq05.correlacao(x, y)
    assert teste["n"] == n
    assert math.isnan(teste["rho"]) and math.isnan(teste["p"])
    assert teste["forca"] == "indefinida"
    assert "indefinido" in rq05.leitura_dora(teste)


@pytest.mark.parametrize("x,y", [([-1, 1], [0.2, 0.3]), ([1, 2], [0.1, 1.1]),
                                 ([float("inf"), 2], [0.1, 0.2])])
def test_invalid_metrics_are_not_silently_clipped(x, y):
    with pytest.raises(ValueError):
        rq05.correlacao(x, y)


@pytest.mark.parametrize("rho,rotulo", [(0, "desprezível"), (0.09999, "desprezível"),
    (0.1, "fraca"), (0.39999, "fraca"), (0.4, "moderada"), (0.69999, "moderada"),
    (0.7, "forte"), (0.89999, "forte"), (0.9, "muito forte"), (1, "muito forte")])
def test_strength_boundaries_ignore_direction(rho, rotulo):
    assert rq05.interpretar_forca(rho) == rotulo
    assert rq05.interpretar_forca(-rho) == rotulo


def test_cfr_b_reuses_delivery_verdicts_and_excludes_censoring(dados):
    dados.releases["censored"] = pd.Series(False, index=dados.releases.index, dtype="boolean")
    dados.releases["failed"] = pd.Series(False, index=dados.releases.index, dtype="boolean")
    dados.releases.loc[0, "failed"] = True
    dados.releases.loc[1, "censored"] = True
    quadro, origem = rq05.por_repositorio(dados)
    assert origem == "releases.csv"
    assert quadro.loc[0, "cfr_b"] == 1  # Uma falha entre uma release avaliável.
    assert quadro.loc[1, "cfr_b"] == 0
    dados.releases.loc[0, "failed"] = pd.NA
    quadro, _ = rq05.por_repositorio(dados)
    assert pd.isna(quadro.loc[0, "cfr_b"])


def test_duplicate_repositories_cannot_inflate_n(dados):
    dados.repositorios.loc[1, "repository"] = "owner/um"
    with pytest.raises(ValueError, match="único"):
        rq05.por_repositorio(dados)


def test_gaps_sort_dates_keep_simultaneous_releases_and_do_not_impute(dados):
    releases = dados.releases.copy()
    releases.loc[0, "published_at"] = releases.loc[1, "published_at"]
    tabela = rq05.intervalos_por_repositorio(releases).set_index("repository")
    assert tabela.loc["owner/um", "mediana_intervalo_dias"] == 0
    assert tabela.loc["owner/um", "fracao_intervalos_ate7"] == 1
    dados.releases.loc[1, "published_at"] = pd.NaT
    tabela = rq05.intervalos_por_repositorio(dados.releases).set_index("repository")
    assert tabela.loc["owner/um", "intervalos"] == 0
    assert pd.isna(tabela.loc["owner/um", "mediana_intervalo_dias"])


def test_artifact_compares_extreme_quartiles(dados):
    quadro, origem = rq05.por_repositorio(dados)
    assert origem == "repositorios.csv"
    resultado = rq05.artefato(quadro, dados.releases)
    assert resultado["q1_df"] == 0.75 and resultado["q3_df"] == 2.25
    tabela = resultado["tabela"].set_index("grupo")
    assert list(tabela.mediana_dias) == [20, 1]
    assert list(tabela.fracao_ate7) == [0, 1]
    assert list(tabela.n) == [1, 1]


def test_coincident_quartiles_cannot_overlap_groups(dados):
    quadro, _ = rq05.por_repositorio(dados)
    quadro["df"] = 1
    resultado = rq05.artefato(quadro, dados.releases)
    assert not resultado["grupos_separaveis"]
    assert resultado["tabela"].n.sum() == 0


def test_empty_dataset_writes_undefined_results(dados, tmp_path):
    vazio = comum.Dados(dados.repositorios.iloc[:0], dados.releases.iloc[:0], dados.episodios)
    resultado = rq05.executar(vazio, tmp_path / "vazio")
    assert resultado["correlacoes"].n.sum() == 0
    assert resultado["correlacoes"].rho.isna().all()


def test_scatter_preserves_zeros_and_has_the_same_n_as_the_test(tmp_path, monkeypatch):
    capturado, salvar = {}, estilo.salvar
    def inspecionar(fig, saida, nome):
        eixo = fig.axes[0]
        capturado.update(escala=eixo.get_xscale(), ylim=eixo.get_ylim(),
                         pontos=eixo.collections[0].get_offsets().copy())
        return salvar(fig, saida, nome)
    monkeypatch.setattr(estilo, "salvar", inspecionar)
    teste = rq05.correlacao([0, 1, None, 3], [0.1, 0.2, 0.3, 0.4])
    pdf = rq05.figura([0, 1, None, 3], [0.1, 0.2, 0.3, 0.4], teste, "a", tmp_path)
    assert capturado["escala"] == "symlog" and capturado["ylim"] == (0, 1)
    assert len(capturado["pontos"]) == teste["n"] == 3
    assert capturado["pontos"][0, 0] == 0
    assert pdf.read_bytes().startswith(b"%PDF-") and b"/Subtype /Image" not in pdf.read_bytes()


def test_registered_command_produces_tables_figures_and_discussion(dados, tmp_path):
    assert ANALISES["rq05"] is rq05.executar
    saida = tmp_path / "saida"
    assert main(["--dados", str(dados.diretorio), "--saida", str(saida), "--analise", "rq05"]) == 0
    tabela = pd.read_csv(saida / "tabelas/rq05_correlacoes.csv")
    assert list(tabela.columns) == ["variante", "n", "rho", "p", "forca"]
    assert list(tabela.n) == [4, 4] and list(tabela.rho) == pytest.approx([0.8, 1])
    assert len(list((saida / "figuras").glob("rq05*.pdf"))) == 2
    assert (saida / "tabelas/rq05_artefato_cfr_b.tex").exists()
    assert (saida / "rq05_por_repositorio.csv").exists()
    notas = (saida / "texto/notas_rq05.md").read_text(encoding="utf-8")
    for trecho in ("0,8000", "20,00 dias", "Schober", "não implica causalidade", "não falha em produção",
                   "descritivo", "symlog", "sem ajuste por multiplicidade"):
        assert trecho in notas
    assert json.loads((saida / "rq05.json").read_text(encoding="utf-8"))["testes"]["a"]["n"] == 4


def test_discussion_follows_the_result_and_preserves_small_p_values():
    assert "tensão aparente" in rq05.leitura_dora({"rho": 0.5, "p": 0.001})
    assert "compatível" in rq05.leitura_dora({"rho": -0.5, "p": 0.001})
    assert "não confirma nem refuta" in rq05.leitura_dora({"rho": 0.1, "p": 0.8})
    assert "e-" in rq05.p_texto(1.23456e-12)
    assert rq05.p_texto(float("nan")) == "--"
