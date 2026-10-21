"""RQ 07: sensibilidade da classificação DORA. Cenário sintético com resultado feito à mão.

Faixas usadas (`dora_selection.rating`): DF Elite ≥ 7, High ≥ 1, Medium ≥ ~0,23 por semana;
Lead Time Elite < 24 h, High < 168 h, Medium < 720 h; CFR Elite ≤ 0,15, High ≤ 0,30, Medium
≤ 0,45; recuperação Elite < 1 h, High < 24 h, Medium < 168 h. Nível geral = mediana das notas
(Elite 4 … Low 1), arredondada para baixo.

Níveis gerais por repositório e combinação (C1 release/LT a/CFR a; C2 release+pré-release/b/b;
C3 tag/b/a; C4 release/b/b):

| repo | C1 | C2 | C3 | C4 | por quê |
| A | Elite | Elite | Elite | Elite | tudo Elite |
| B | High | High | High | Medium | LT b = 800 h e CFR b = 0,5 derrubam a C4 |
| C | Low | High | Medium | Low | release+pré-release e tag salvam o repositório |
| D | High | High | —    | High | coleta das tags falhou (collection_complete = False) |
| E | —    | —    | —    | —    | ausente de variantes.csv |
"""
import json
import math

import pandas as pd
import pytest

from analise import comum, rq05, rq07
from analise.__main__ import ANALISES, main


REPOSITORIOS = (
    "repository,deployment_frequency_per_week,lead_time_a_hours,lead_time_b_hours,cfr_a,cfr_b,recovery_hours\n"
    "owner/a,10,10,12,0.1,0.1,0.5\n"
    "owner/b,2,100,800,0.2,0.5,10\n"
    "owner/c,0,1000,20,0.5,0.4,200\n"
    "owner/d,3,50,60,0.1,0.1,0.5\n"
    "owner/e,5,5,5,0.3,0.3,5\n")
VARIANTES = (
    "repository,unit,deployment_frequency_per_week,lead_time_a_hours,lead_time_b_hours,cfr_b,collection_complete\n"
    "owner/a,release,10,10,12,0.1,True\nowner/a,release_prerelease,20,,10,0.1,True\nowner/a,tag,30,,5,0.5,True\n"
    "owner/b,release,2,100,800,0.5,True\nowner/b,release_prerelease,8,,30,0.1,True\nowner/b,tag,0.1,,3,0.5,True\n"
    "owner/c,release,0,1000,20,0.4,True\nowner/c,release_prerelease,0.5,,20,0.1,True\nowner/c,tag,3,,20,0.5,True\n"
    "owner/d,release,3,50,60,0.1,True\nowner/d,release_prerelease,4,,60,0.1,True\nowner/d,tag,0,,,,False\n")
GERAL = {"owner/a": ["Elite"] * 4, "owner/b": ["High", "High", "High", "Medium"],
         "owner/c": ["Low", "High", "Medium", "Low"], "owner/d": ["High", "High", None, "High"],
         "owner/e": [None] * 4}


def carregar(tmp_path, variantes=VARIANTES):
    (tmp_path / "repositorios.csv").write_text(REPOSITORIOS, encoding="utf-8")
    (tmp_path / "releases.csv").write_text("repository\n", encoding="utf-8")
    (tmp_path / "episodios_falha.csv").write_text("repository\n", encoding="utf-8")
    if variantes is not None:
        (tmp_path / "variantes.csv").write_text(variantes, encoding="utf-8")
    return comum.carregar(tmp_path)


@pytest.fixture
def dados(tmp_path):
    return carregar(tmp_path)


@pytest.fixture
def wide(dados):
    return rq07.classificar_combinacoes(dados)


def test_overall_levels_of_every_repository_and_combination_by_hand(wide):
    esperado = wide.set_index("repository")[[f"{nome}_geral" for nome in rq07.NOMES]]
    for repositorio, niveis in GERAL.items():
        obtido = [None if pd.isna(nivel) else nivel for nivel in esperado.loc[repositorio]]
        assert obtido == niveis, repositorio


def test_levels_per_metric_follow_the_unit_and_the_variant(wide):
    b = wide.set_index("repository").loc["owner/b"]
    # C1: release, LT (a) 100 h = High, CFR (a) 0,2 = High. C4: LT (b) 800 h = Low, CFR (b) 0,5 = Low.
    assert (b["C1_lt"], b["C1_cfr"], b["C4_lt"], b["C4_cfr"]) == ("High", "High", "Low", "Low")
    # C3: tag, DF 0,1/semana = Low, mas LT (b) 3 h = Elite e CFR (a) = High; o CFR (a) não depende da unidade.
    assert (b["C3_df"], b["C3_lt"], b["C3_cfr"]) == ("Low", "Elite", "High")
    # A recuperação é a mesma em toda combinação.
    assert {b[f"{nome}_rec"] for nome in rq07.NOMES} == {"High"}


def test_failed_unit_collection_is_not_zero_deploys_and_not_elite_by_two_metrics(wide):
    d = wide.set_index("repository").loc["owner/d"]
    assert pd.isna(d["C3_df"]) and pd.isna(d["C3_lt"]) and pd.isna(d["C3_geral"])
    # O CFR (a) e a recuperação continuam existindo, mas não sustentam um nível geral sozinhos.
    assert (d["C3_cfr"], d["C3_rec"]) == ("Elite", "Elite")


def test_pairs_by_hand_percentage_and_weighted_kappa(wide):
    pares = rq07.tabela_de_pares(wide)

    def geral(par):
        return rq07.linha_do_par(pares, par)

    # C1 × C2: só o C muda (Low → High), n = 4. κ linear = 1 − (1/6)/(7/24) = 3/7.
    c1c2 = geral("C1 × C2")
    assert (c1c2["n"], c1c2["mudaram"], c1c2["pct_mudou"]) == (4, 1, 0.25)
    assert c1c2["kappa"] == pytest.approx(3 / 7)
    # C1 × C3: D não está classificado na C3 (n = 3), só C muda (Low → Medium). κ = 8/11.
    c1c3 = geral("C1 × C3")
    assert (c1c3["n"], c1c3["so_na_primeira"], c1c3["mudaram"]) == (3, 1, 1)
    assert c1c3["kappa"] == pytest.approx(8 / 11)
    # C1 × C4 (só as variantes): só o B muda (High → Medium). κ = 0,8.
    c1c4 = geral("C1 × C4")
    assert (c1c4["n"], c1c4["mudaram"], c1c4["pct_mudou"]) == (4, 1, 0.25)
    assert c1c4["kappa"] == pytest.approx(0.8)
    # C2 × C4 (só a unidade, variantes iguais): B e C mudam. κ = 1/3.
    c2c4 = geral("C2 × C4")
    assert (c2c4["mudaram"], c2c4["pct_mudou"]) == (2, 0.5)
    assert c2c4["kappa"] == pytest.approx(1 / 3)
    assert geral("C2 × C3")["kappa"] == pytest.approx(4 / 7)


def test_per_metric_change_counts_only_repositories_classified_in_both(wide):
    pares = rq07.tabela_de_pares(wide)
    df = rq07.linha_do_par(pares, "C1 × C2", "Deployment Frequency")
    # C1: Elite, High, Low, High; C2: Elite, Elite, Medium, High → B e C mudam.
    assert (df["n"], df["mudaram"]) == (4, 2)
    # O CFR (a) é o mesmo na C1 e na C3, então nada muda entre as duas.
    assert rq07.linha_do_par(pares, "C1 × C3", "Change Failure Rate")["pct_mudou"] == 0.0


def test_kappa_edge_cases():
    assert rq07.kappa_ponderado(["Elite", "Low"], ["Elite", "Low"]) == pytest.approx(1.0)
    # Todos na mesma categoria dos dois lados: 0/0, indefinido e sem erro.
    assert math.isnan(rq07.kappa_ponderado(["High", "High"], ["High", "High"]))
    assert math.isnan(rq07.kappa_ponderado(["High"], ["High"]))
    assert math.isnan(rq07.kappa_ponderado([], []))
    # Elite→High pesa menos do que Elite→Low.
    perto = rq07.kappa_ponderado(["Elite", "Low", "Medium"], ["High", "Low", "Medium"])
    longe = rq07.kappa_ponderado(["Elite", "Low", "Medium"], ["Low", "Low", "Medium"])
    assert perto > longe


def test_transition_matrix_and_distribution(wide):
    matriz = rq07.matriz_transicao(wide, "C1", "C2").set_index(rq07.matriz_transicao(wide, "C1", "C2").columns[0])
    assert matriz.loc["Elite", "Elite"] == 1 and matriz.loc["High", "High"] == 2
    assert matriz.loc["Low", "High"] == 1
    assert matriz.loc[rq07.SEM_NIVEL, rq07.SEM_NIVEL] == 1 and int(matriz.to_numpy().sum()) == 5
    distribuicao = rq07.distribuicao(wide).set_index("combinacao")
    assert distribuicao.loc["C1", ["Elite", "High", "Medium", "Low", rq07.SEM_NIVEL]].tolist() == [1, 2, 0, 1, 1]
    assert distribuicao.loc["C3", rq07.SEM_NIVEL] == 2


def test_spearman_robustness_by_hand(dados):
    por_unidade = rq07.metricas_por_unidade(dados)
    series = {nome: rq07.series_da_combinacao(dados, por_unidade, nome) for nome in rq07.NOMES}
    tabela = rq07.robustez_spearman(series).set_index("combinacao")
    # C1: ρ = −4,5 / √22,5 (postos com empate no CFR), n = 4.
    assert tabela.loc["C1", "n"] == 4 and tabela.loc["C1", "rho"] == pytest.approx(-4.5 / math.sqrt(22.5))
    assert tabela.loc["C1", "sinal"] == "negativo" and bool(tabela.loc["C1", "conclusao_mantida"])
    # C4 mantém o sinal; C3 tem n = 3 (o D não tem DF por tag) e ρ = −0,5.
    assert bool(tabela.loc["C4", "mantem_sinal"])
    assert tabela.loc["C3", "n"] == 3 and tabela.loc["C3", "rho"] == pytest.approx(-0.5)
    # C2: CFR (b) constante em 0,1 → correlação indefinida, e a conclusão não se mantém.
    assert tabela.loc["C2", "sinal"] == "indefinido" and not bool(tabela.loc["C2", "conclusao_mantida"])


def test_descriptive_robustness_medians_and_change_against_c1(dados):
    por_unidade = rq07.metricas_por_unidade(dados)
    series = {nome: rq07.series_da_combinacao(dados, por_unidade, nome) for nome in rq07.NOMES}
    tabela = rq07.robustez_descritiva(series)
    df = tabela[tabela["metrica"] == "Deployment Frequency"].set_index("combinacao")
    # DF por release: [10, 2, 0, 3] → mediana 2,5; release + pré-release: [20, 8, 0,5, 4] → 6.
    assert df.loc["C1", "mediana"] == 2.5 and df.loc["C2", "mediana"] == 6.0
    assert df.loc["C2", "variacao_mediana_vs_c1"] == pytest.approx(6 / 2.5 - 1)
    assert df.loc["C1", "variacao_mediana_vs_c1"] == 0.0


def test_rq06_robustness_compares_the_rejected_sets_with_the_c1(dados):
    por_unidade = rq07.metricas_por_unidade(dados)
    series = {nome: rq07.series_da_combinacao(dados, por_unidade, nome) for nome in rq07.NOMES}
    tabela = rq07.robustez_rq06(dados, series)
    assert list(tabela["combinacao"]) == list(rq07.NOMES)
    # Cinco repositórios não sustentam nenhum Kruskal-Wallis (grupos com n < 5).
    assert tabela["rejeitam_h0"].sum() == 0 and tabela["so_nesta"].sum() == 0


def test_release_unit_is_checked_against_the_pipeline_and_c1(dados, wide):
    confere = rq07.conferencia(dados, rq07.metricas_por_unidade(dados), wide)
    # Só o E, ausente de variantes.csv, diverge em cada coluna e na C1.
    assert set(confere["unidade_release_vs_repositorios"].values()) == {1}
    assert confere["c1_diverge_da_classificacao_c1"] == 1 and confere["repositorios"] == 5


def test_duplicated_repository_and_unit_is_an_error(tmp_path):
    repetido = VARIANTES + "owner/a,release,10,10,12,0.1,True\n"
    with pytest.raises(ValueError, match="repete"):
        rq07.metricas_por_unidade(carregar(tmp_path, repetido))


def test_unit_missing_from_the_file_is_all_missing_not_zero(tmp_path):
    sem_tag = "\n".join(linha for linha in VARIANTES.splitlines() if ",tag," not in linha) + "\n"
    dados = carregar(tmp_path, sem_tag)
    assert rq07.metricas_por_unidade(dados)["tag"]["df"].isna().all()
    assert rq07.classificar_combinacoes(dados)["C3_geral"].isna().all()


def test_end_to_end_writes_tables_figures_text_and_json(dados, tmp_path):
    saida = tmp_path / "resultados"
    resultado = rq07.executar(dados, saida)
    assert resultado["disponivel"] and resultado["repositorios"] == 5
    for arquivo in ("tabelas/rq07_pares.csv", "tabelas/rq07_distribuicao.tex", "tabelas/rq07_robustez_spearman.csv",
                    "tabelas/rq07_robustez_descritiva.csv", "tabelas/rq07_robustez_rq06.csv",
                    "tabelas/rq07_transicao_C1_C2.csv", "figuras/rq07_distribuicao.pdf",
                    "figuras/rq07_transicao_C1_C2.pdf", "figuras/rq07_transicao_C1_C3.pdf",
                    "figuras/rq07_transicao_C1_C4.pdf", "texto/notas_rq07.md", "rq07_por_repositorio.csv",
                    "rq07.json"):
        assert (saida / arquivo).is_file(), arquivo
    texto = (saida / "texto" / "notas_rq07.md").read_text(encoding="utf-8")
    assert "C1 × C4" in texto and "C2 × C4" in texto and "tag" in texto
    assert json.loads((saida / "rq07.json").read_text(encoding="utf-8"))["repositorios"] == 5


def test_without_variants_the_analysis_says_so_instead_of_inventing_results(tmp_path):
    dados = carregar(tmp_path, None)
    assert dados.variantes.empty
    resultado = rq07.executar(dados, tmp_path / "resultados")
    assert resultado["disponivel"] is False
    assert "indisponível" in (tmp_path / "resultados" / "texto" / "notas_rq07.md").read_text(encoding="utf-8")


def test_command_registers_the_analysis_and_never_fails_without_variants(tmp_path, capsys):
    carregar(tmp_path, None)
    assert "rq07" in ANALISES
    assert main(["--dados", str(tmp_path), "--saida", str(tmp_path / "o"), "--analise", "rq07"]) == 0
    assert "rq07:" in capsys.readouterr().out


def test_c1_here_agrees_with_the_spearman_of_the_rq05(dados):
    por_unidade = rq07.metricas_por_unidade(dados)
    serie = rq07.series_da_combinacao(dados, por_unidade, "C1")
    direto = rq05.correlacao(pd.Series([10, 2, 0, 3, None]), pd.Series([0.1, 0.2, 0.5, 0.1, 0.3]))
    assert rq05.correlacao(serie["df"], serie["cfr"])["rho"] == pytest.approx(direto["rho"])
