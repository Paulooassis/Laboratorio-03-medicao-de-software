"""Fixtures com resultados calculados à mão e integração com os CSVs congelados."""
import hashlib
import json

import numpy as np
import pandas as pd
import pytest
from statsmodels.stats.inter_rater import cohens_kappa

from replicacao import comparar as c


@pytest.fixture
def csvs(tmp_path):
    def gravar(valores_a, valores_b, amostra=None):
        def linhas(valores):
            return [dict(repo=repo, **{k: valor for k in c.METRICAS},
                         **{k: nivel for k in c.CATEGORIAS}) for repo, valor, nivel in valores]
        a, b, s = (tmp_path/n for n in ("original.csv", "obtido.csv", "amostra.csv"))
        pd.DataFrame(linhas(valores_a)).to_csv(a, index=False)
        pd.DataFrame(linhas(valores_b)).to_csv(b, index=False)
        pd.DataFrame({"repository": amostra or [v[0] for v in valores_a]}).to_csv(s, index=False)
        return a, b, s
    return gravar


@pytest.mark.parametrize("a,b,absoluta,relativa,estado", [
    (2, 2, 0, 0, "comparavel"), (2, 3, 1, .5, "comparavel"),
    (2, 0, -2, -1, "comparavel"), (0, 0, 0, None, "ambos_zero"),
    (0, 3, 3, None, "original_zero"), (np.nan, 1, None, None, "ausente"),
    (1, np.nan, None, None, "ausente")])
def test_diferenca(a, b, absoluta, relativa, estado):
    resultado = c.diferenca(a, b)
    for esperado, real in zip((absoluta, relativa), resultado[:2]):
        assert pd.isna(real) if esperado is None else real == esperado
    assert resultado[2] == estado


def test_join_zero_missing_and_denominators(csvs):
    paths = csvs([("ORG/Igual", 2, "High"), ("o/zero", 0, "Low"),
                  ("o/so_original", 1, "Medium")],
                 [("org/igual", 2, "High"), ("o/zero", 3, "Medium"),
                  ("o/so_obtido", 2, "High")],
                 ["o/so_obtido", "ORG/Igual", "o/zero", "o/so_original", "o/nenhum"])
    dif, resumo, classes, acordo = c.comparar(*paths)
    assert dif.repo.head(5).tolist() == ["o/so_obtido", "org/igual", "o/zero", "o/so_original", "o/nenhum"]
    assert resumo.n_total.eq(5).all()
    assert resumo.n_relativas.eq(1).all()
    assert resumo.n_original_zero.eq(1).all()
    assert resumo.n_ausentes.eq(3).all()
    assert acordo.n_pares.eq(2).all()
    assert acordo.percentual_amostra.eq(20).all()
    assert acordo.percentual_pares.eq(50).all()
    assert not classes.loc[classes.repo == "o/nenhum", "mesma_classificacao"].any()


def test_quantiles_and_original_zero_not_counted(csvs):
    # Razões: 0, 1, 2, 3; Q1=.75, mediana=1.5, Q3=2.25, IQR=1.5.
    paths = csvs([(f"o/r{i}", 1, "High") for i in range(4)],
                 [(f"o/r{i}", i+1, "High") for i in range(4)])
    _, resumo, _, acordo = c.comparar(*paths)
    assert resumo.mediana.eq(1.5).all()
    assert resumo.q1.eq(.75).all()
    assert resumo.q3.eq(2.25).all()
    assert resumo.iqr.eq(1.5).all()
    assert acordo.kappa_linear.isna().all()


def test_kappa_uses_linear_ordinal_weights():
    a = ["Low", "Low", "Medium", "High", "Elite", None]
    b = ["Low", "Medium", "High", "High", "Elite", "Low"]
    table = np.array([[1, 1, 0, 0], [0, 0, 1, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
    expected = cohens_kappa(table, weights=np.arange(4), wt="linear", return_results=False)
    assert c.kappa_ponderado(a, b) == pytest.approx(expected)
    assert c.kappa_ponderado(["Low", "Elite"], ["Low", "Elite"]) == 1
    assert np.isnan(c.kappa_ponderado(["Low"], ["Low"]))
    assert np.isnan(c.kappa_ponderado([None], [None]))
    assert c.kappa_ponderado(["Low", "Low"], ["Elite", "Elite"]) == 0


@pytest.mark.parametrize("problema", ["duplicado", "chave_vazia", "sem_chave", "sem_metrica", "categoria", "infinito", "texto", "amostra_vazia"])
def test_invalid_input_fails(csvs, problema):
    a, b, s = csvs([("o/r", 1, "Low")], [("o/r", 1, "Low")])
    dados = pd.read_csv(a)
    if problema == "duplicado":
        dados = pd.concat([dados, dados.assign(repo="O/R")])
    elif problema == "chave_vazia":
        dados.loc[0, "repo"] = ""
    elif problema == "sem_chave":
        dados = dados.drop(columns="repo")
    elif problema == "sem_metrica":
        dados = dados.drop(columns="cfr_ci")
    elif problema == "categoria":
        dados.loc[0, "categoria_dora_cfr"] = "Desconhecida"
    elif problema in ("infinito", "texto"):
        dados["cfr_ci"] = "inf" if problema == "infinito" else "texto"
    else:
        pd.DataFrame(columns=["repo"]).to_csv(s, index=False)
    dados.to_csv(a, index=False)
    with pytest.raises(ValueError):
        c.comparar(a, b, s)


def test_all_values_and_categories_missing(csvs):
    paths = csvs([("o/r", None, None)], [("o/r", None, None)])
    _, resumo, _, acordo = c.comparar(*paths)
    assert resumo.mediana.isna().all()
    assert resumo.n_ausentes.eq(1).all()
    assert acordo.n_pares.eq(0).all()
    assert acordo.percentual_amostra.eq(0).all()
    assert acordo.percentual_pares.isna().all()


def test_cli_and_artifacts(csvs, tmp_path):
    a, b, s = csvs([("o/r", 0, "Low"), ("o/s", 2, "Elite")],
                   [("o/r", 0, "Low"), ("o/s", 4, "High")])
    # Manifesto inválido é exposto, sem impedir a comparação do CSV congelado.
    a.with_name("MANIFEST.json").write_text(json.dumps({"dataset": {"sha256": "errado"}}))
    saida = tmp_path/"resultado"
    args = ["--original", str(a), "--obtido", str(b), "--amostra", str(s), "--saida", str(saida)]
    c.main(args)
    arquivos = list(saida.rglob("*.*"))
    antes = {p.relative_to(saida): p.read_bytes() for p in arquivos}
    c.main(args)
    assert all((saida/p).read_bytes() == conteudo for p, conteudo in antes.items())
    assert (saida/"figuras/replicacao_comparacao.pdf").read_bytes().startswith(b"%PDF")
    notas = (saida/"texto/notas_replicacao.md").read_text(encoding="utf-8")
    assert "Manifesto inconsistente" in notas
    assert "ambos zero=1" in notas
    with pytest.raises(SystemExit) as erro:
        c.main(["--original", str(tmp_path/"inexistente.csv")])
    assert erro.value.code == 2


def test_real_data_regression():
    _, resumo, _, acordo = c.comparar(c.BASE/"resultados_originais/dataset.csv",
                                     c.BASE/"resultados_obtidos/dataset.csv", c.BASE/"subamostra.csv")
    assert resumo.n_total.eq(30).all()
    assert resumo.mediana.eq(0).all()
    assert resumo.iqr.eq(0).all()
    assert acordo.iloc[-1].n_iguais == 29
    assert acordo.iloc[-1].kappa_linear == pytest.approx(.9598930481283422)
    assert acordo.iloc[3].n_pares == 23
    assert acordo.iloc[3].n_iguais == 21
    assert c.proveniencia(c.BASE/"resultados_originais/dataset.csv")["manifesto_confere"] is False
    assert c.proveniencia(c.BASE/"resultados_obtidos/dataset.csv")["manifesto_confere"] is True


def test_original_snapshots_preserve_github_blob_bytes():
    pasta = c.BASE/"resultados_originais"
    origem = json.loads((pasta/"ORIGEM.json").read_text(encoding="utf-8"))
    for arquivo in origem["arquivos"]:
        dados = (pasta/arquivo["arquivo"]).read_bytes()
        git_blob = b"blob " + str(len(dados)).encode() + b"\0" + dados
        assert hashlib.sha1(git_blob).hexdigest() == arquivo["git_blob_sha"]
