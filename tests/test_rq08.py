"""RQ 08: rework rate. Amostras sintéticas exclusivas dos testes, com resultado feito à mão."""
import json
import math

import pandas as pd
import pytest

from analise import comum, rq08
from analise.__main__ import ANALISES, main


# um: 4 releases, a 1ª sem anterior; 3 avaliadas, 1 corretiva → 1/3; CFR (b) = 1 falha / 4.
# dois: 3 releases, a 1ª sem anterior; 2 avaliadas, 2 corretivas → 1; CFR (b) = 2 falhas / 3.
# tres: 1 release só, sem anterior → nenhuma avaliada, taxa indefinida; CFR (b) = 0.
# quatro: nenhuma release.
RELEASES = (
    "repository,release_id,published_at,corrective,comparison_status,censored,failed\n"
    "owner/um,1,2025-01-01T00:00:00Z,True,no_previous_release,False,False\n"
    "owner/um,2,2025-01-02T00:00:00Z,True,completed,False,True\n"
    "owner/um,3,2025-01-03T00:00:00Z,False,completed,False,False\n"
    "owner/um,4,2025-01-04T00:00:00Z,False,completed,False,False\n"
    "owner/dois,5,2025-01-01T00:00:00Z,False,no_previous_release,False,True\n"
    "owner/dois,6,2025-01-02T00:00:00Z,True,completed,False,True\n"
    "owner/dois,7,2025-01-03T00:00:00Z,True,completed,False,False\n"
    "owner/tres,8,2025-01-01T00:00:00Z,False,no_previous_release,False,False\n")
REPOSITORIOS = ("repository,releases_per_week\nowner/um,1\nowner/dois,2\nowner/tres,3\nowner/quatro,4\n")


@pytest.fixture
def dados(tmp_path):
    (tmp_path / "repositorios.csv").write_text(REPOSITORIOS, encoding="utf-8")
    (tmp_path / "releases.csv").write_text(RELEASES, encoding="utf-8")
    (tmp_path / "episodios_falha.csv").write_text("repository\n", encoding="utf-8")
    return comum.carregar(tmp_path)


def com_repositorios(tmp_path, cabecalho, linhas, releases="repository,release_id\n"):
    (tmp_path / "repositorios.csv").write_text(cabecalho + "\n" + "\n".join(linhas) + "\n", encoding="utf-8")
    (tmp_path / "releases.csv").write_text(releases, encoding="utf-8")
    (tmp_path / "episodios_falha.csv").write_text("repository\n", encoding="utf-8")
    return comum.carregar(tmp_path)


def test_rate_per_repository_by_hand_and_first_release_left_out(dados):
    quadro, origem = rq08.por_repositorio(dados)
    por_nome = quadro.set_index("repository")
    assert origem == "releases.csv"
    assert (por_nome.loc["owner/um", "avaliadas"], por_nome.loc["owner/um", "corretivas"]) == (3, 1)
    assert por_nome.loc["owner/um", "rework_rate"] == pytest.approx(1 / 3)
    assert por_nome.loc["owner/um", "sem_anterior"] == 1
    assert (por_nome.loc["owner/dois", "avaliadas"], por_nome.loc["owner/dois", "rework_rate"]) == (2, 1.0)


def test_repository_without_evaluable_release_is_undefined_not_zero(dados):
    por_nome = rq08.por_repositorio(dados)[0].set_index("repository")
    # tres só tem a primeira release; quatro não tem nenhuma.
    assert por_nome.loc["owner/tres", "sem_anterior"] == 1
    assert math.isnan(por_nome.loc["owner/tres", "rework_rate"])
    assert math.isnan(por_nome.loc["owner/quatro", "rework_rate"])


def test_summary_uses_only_defined_rates_with_median_and_iqr(dados):
    quadro, _ = rq08.por_repositorio(dados)
    resumo = comum.resumo(quadro["rework_rate"])
    assert resumo["n"] == 2 and resumo["ausentes"] == 2
    assert resumo["mediana"] == pytest.approx((1 / 3 + 1) / 2)


def test_totals_pool_all_releases_and_reconcile_with_the_cfr(dados):
    quadro, _ = rq08.por_repositorio(dados)
    cfr, _ = rq08.cfr_b_por_repositorio(dados)
    soma = rq08.totais(quadro.merge(cfr, on="repository"))
    assert (soma["releases_avaliadas"], soma["corretivas"], soma["sem_anterior"]) == (5, 3, 3)
    assert soma["taxa_agregada"] == pytest.approx(3 / 5)
    # O CFR (b) conta todas as 8 releases publicadas e 3 falhas (1 + 2 + 0).
    assert (soma["cfr_b_avaliadas"], soma["cfr_b_falhas"]) == (8, 3)
    assert soma["repositorios_sem_taxa"] == 2


def test_falls_back_to_the_repository_columns_without_a_release_verdict(tmp_path):
    dados = com_repositorios(
        tmp_path, "repository,rework_rate,rework_evaluated,rework_corrective,rework_no_previous",
        ["owner/um,0.25,4,1,1", "owner/dois,,0,0,1"])
    quadro, origem = rq08.por_repositorio(dados)
    assert origem == "repositorios.csv"
    assert quadro["rework_rate"].iloc[0] == 0.25 and math.isnan(quadro["rework_rate"].iloc[1])


def test_without_any_source_the_analysis_is_unavailable_but_does_not_fail(tmp_path):
    dados = com_repositorios(tmp_path, "repository", ["owner/um"])
    quadro, origem = rq08.por_repositorio(dados)
    assert origem == "indisponivel" and quadro["rework_rate"].isna().all()


def test_duplicated_repository_is_refused(tmp_path):
    dados = com_repositorios(tmp_path, "repository", ["owner/um", "owner/um"])
    with pytest.raises(ValueError):
        rq08.por_repositorio(dados)


def test_recalculation_is_checked_against_the_pipeline_column(tmp_path):
    certo = com_repositorios(tmp_path, "repository,rework_rate", ["owner/um,0.5"],
                             "repository,published_at,corrective,comparison_status\n"
                             "owner/um,2025-01-02T00:00:00Z,True,completed\n"
                             "owner/um,2025-01-03T00:00:00Z,False,completed\n")
    quadro, _ = rq08.por_repositorio(certo)
    assert rq08.conferir_com_csv(quadro, certo) == {"verificavel": True, "divergentes": []}
    errado = com_repositorios(tmp_path, "repository,rework_rate", ["owner/um,0.9"],
                              "repository,published_at,corrective,comparison_status\n"
                              "owner/um,2025-01-02T00:00:00Z,True,completed\n"
                              "owner/um,2025-01-03T00:00:00Z,False,completed\n")
    quadro, _ = rq08.por_repositorio(errado)
    assert rq08.conferir_com_csv(quadro, errado)["divergentes"] == ["owner/um"]


def test_check_is_not_possible_without_the_pipeline_column(dados):
    quadro, _ = rq08.por_repositorio(dados)
    assert rq08.conferir_com_csv(quadro, dados)["verificavel"] is False


def test_spearman_by_hand_and_effective_n():
    # Postos x=[1,2,3,4], y=[1,3,2,4]: Σd²=2, ρ = 1 − 6·2/(4·15) = 0,8.
    teste = rq08.correlacao([0.1, 0.2, 0.3, 0.4], [0.1, 0.3, 0.2, 0.4])
    assert teste["n"] == 4 and teste["rho"] == pytest.approx(0.8) and teste["forca"] == "forte"
    # Ausentes saem par a par.
    assert rq08.correlacao([0.1, None, 0.3, 0.4], [0.1, 0.5, None, 0.4])["n"] == 2


@pytest.mark.parametrize("x,y,motivo", [([], [], "menos de dois pares"), ([0.1], [0.2], "menos de dois pares"),
                                        ([0.1, 0.1, 0.1], [0.1, 0.2, 0.3], "variável constante")])
def test_undefined_correlation_keeps_n_and_says_why(x, y, motivo):
    teste = rq08.correlacao(x, y)
    assert math.isnan(teste["rho"]) and math.isnan(teste["p"]) and teste["motivo"] == motivo
    assert "indefinida" in rq08.leitura_correlacao(teste)


def test_rates_outside_zero_one_are_not_clipped():
    with pytest.raises(ValueError):
        rq08.correlacao([0.1, 1.2], [0.1, 0.2])


def test_correlation_reading_never_claims_causality():
    texto = rq08.leitura_correlacao({"rho": 0.5, "p": 0.001, "forca": "moderada", "motivo": "ok"})
    assert "moderada" in texto and "construção" in texto
    assert "não distinguível" in rq08.leitura_correlacao({"rho": 0.1, "p": 0.5, "forca": "fraca", "motivo": "ok"})


def test_largest_divergences_are_ordered_and_labeled(dados):
    quadro, _ = rq08.por_repositorio(dados)
    cfr, _ = rq08.cfr_b_por_repositorio(dados)
    tabela = rq08.divergencias(quadro.merge(cfr, on="repository"))
    # um: 1/3 − 0,25 = 0,083 (mais retrabalho); dois: 1 − 2/3 = 0,333 (mais retrabalho).
    assert list(tabela["repository"]) == ["owner/dois", "owner/um"]
    assert tabela["diferenca"].iloc[0] == pytest.approx(1 / 3)
    assert set(tabela["leitura"]) == {"mais retrabalho que falha"}


def test_divergence_labels_the_opposite_direction():
    quadro = pd.DataFrame({"repository": ["a"], "rework_rate": [0.2], "cfr_b": [0.6], "avaliadas": [5],
                           "corretivas": [1], "cfr_b_avaliadas": [5], "cfr_b_falhas": [3],
                           "cfr_b_censuradas": [0]})
    assert rq08.divergencias(quadro)["leitura"].iloc[0] == "mais falha que retrabalho"
    assert rq08.divergencias(quadro.iloc[:0]).empty


def test_heuristic_adjustment_uses_precision_over_recall(tmp_path):
    pasta = tmp_path / "v1-20260101"
    pasta.mkdir()
    (pasta / "resultado.json").write_text(json.dumps(
        {"version": "v1", "precision": 0.6, "recall": 0.8, "f1": 0.6857}), encoding="utf-8")
    avaliacao = rq08.avaliacao_da_heuristica(tmp_path)
    assert avaliacao["precisao"] == 0.6 and avaliacao["recall"] == 0.8
    # Precisão menor que recall: a taxa observada superestima, a ajustada é menor (0,6 × 0,75).
    assert rq08.ajustar_pela_heuristica(0.6, avaliacao) == pytest.approx(0.45)
    assert rq08.ajustar_pela_heuristica(0.99, {"precisao": 1.0, "recall": 0.5}) == 1.0
    assert math.isnan(rq08.ajustar_pela_heuristica(0.6, None))


@pytest.mark.parametrize("conteudo", ["não é json", '{"precision": 0.5}', '{"precision": 0, "recall": 0.5}'])
def test_unreadable_or_invalid_evaluation_is_ignored(tmp_path, conteudo):
    pasta = tmp_path / "v1-x"
    pasta.mkdir()
    (pasta / "resultado.json").write_text(conteudo, encoding="utf-8")
    assert rq08.avaliacao_da_heuristica(tmp_path) is None
    assert rq08.avaliacao_da_heuristica(tmp_path / "ausente") is None


def test_end_to_end_writes_tables_figures_text_and_json(dados, tmp_path):
    saida = tmp_path / "resultados"
    resultado = rq08.executar(dados, saida)
    assert resultado["origem"] == "releases.csv"
    assert resultado["resumo_rework_rate"]["n"] == 2
    for arquivo in ("tabelas/rq08_resumo.csv", "tabelas/rq08_correlacao.tex", "tabelas/rq08_divergencias.csv",
                    "figuras/rq08_distribuicao.pdf", "figuras/rq08_rework_cfr_b.pdf",
                    "texto/notas_rq08.md", "rq08_por_repositorio.csv", "rq08.json"):
        assert (saida / arquivo).is_file(), arquivo
    texto = (saida / "texto" / "notas_rq08.md").read_text(encoding="utf-8")
    assert "Rework rate" in texto and "CFR (b)" in texto
    assert json.loads((saida / "rq08.json").read_text(encoding="utf-8"))["totais"]["corretivas"] == 3


def test_end_to_end_without_data_does_not_crash(tmp_path):
    dados = com_repositorios(tmp_path, "repository", ["owner/um"])
    resultado = rq08.executar(dados, tmp_path / "resultados")
    assert resultado["origem"] == "indisponivel" and resultado["resumo_rework_rate"]["n"] == 0
    assert (tmp_path / "resultados" / "figuras" / "rq08_distribuicao.pdf").is_file()


def test_command_registers_and_runs_only_this_analysis(dados, tmp_path, capsys):
    assert "rq08" in ANALISES
    assert main(["--dados", str(dados.diretorio), "--saida", str(tmp_path / "o"), "--analise", "rq08"]) == 0
    assert "rq08:" in capsys.readouterr().out
    assert (tmp_path / "o" / "tabelas" / "rq08_resumo.csv").is_file()
