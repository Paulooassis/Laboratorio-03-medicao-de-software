"""Base comum da análise: leitura dos CSVs, mediana/IQR e as saídas para o artigo.

As séries dos testes têm quartis calculáveis à mão: `[1, 2, 3, 4, 5]` tem mediana 3,
Q1 2 e Q3 4 (interpolação linear, o padrão do pandas e do R), logo IQR 2.
"""
import unittest
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from analise import comum, estilo


REPOSITORIOS = """repository,releases_per_week,change_failure_rate,created_at
owner/um,1.5,0.5,2020-01-01T00:00:00Z
owner/dois,,0.25,2021-06-15T12:00:00+00:00
"""
RELEASES = """repository,tag_name,published_at,lead_time_hours,censored,failed
owner/um,v1.0,2025-03-01T00:00:00Z,24,False,True
"""
EPISODIOS = """repository,recovery_hours,recovered,censored
owner/um,6,True,False
"""


class DiretorioDeDados:
    """Os três CSVs em um diretório temporário, como a análise os encontra."""

    def __init__(self, repositorios=REPOSITORIOS, releases=RELEASES, episodios=EPISODIOS):
        self.temporario = TemporaryDirectory()
        self.caminho = Path(self.temporario.name)
        for nome, conteudo in (("repositorios.csv", repositorios), ("releases.csv", releases),
                               ("episodios_falha.csv", episodios)):
            if conteudo is not None:
                (self.caminho / nome).write_text(conteudo, encoding="utf-8")

    def __enter__(self):
        return self.caminho

    def __exit__(self, *erro):
        self.temporario.cleanup()


class ResumoTests(unittest.TestCase):
    def test_median_and_iqr_of_a_known_series(self):
        self.assertEqual(comum.resumo([1, 2, 3, 4, 5]),
                         {"n": 5, "ausentes": 0, "mediana": 3.0, "q1": 2.0, "q3": 4.0, "iqr": 2.0})

    def test_even_sample_interpolates_the_median(self):
        # [2, 4, 6, 8]: mediana (4+6)/2 = 5, Q1 3,5, Q3 6,5, IQR 3.
        self.assertEqual(comum.resumo([2, 4, 6, 8]),
                         {"n": 4, "ausentes": 0, "mediana": 5.0, "q1": 3.5, "q3": 6.5, "iqr": 3.0})

    def test_missing_values_are_counted_and_never_imputed(self):
        resultado = comum.resumo(["", None, 4, 8, "x"])
        self.assertEqual((resultado["n"], resultado["ausentes"]), (2, 3))
        self.assertEqual((resultado["mediana"], resultado["iqr"]), (6.0, 2.0))

    def test_empty_series_has_no_statistics_instead_of_zero(self):
        resultado = comum.resumo([])
        self.assertEqual((resultado["n"], resultado["ausentes"]), (0, 0))
        for chave in ("mediana", "q1", "q3", "iqr"):
            self.assertNotEqual(resultado[chave], resultado[chave], chave)  # NaN

    def test_series_without_any_number_has_no_statistics(self):
        resultado = comum.resumo(["", None])
        self.assertEqual((resultado["n"], resultado["ausentes"]), (0, 2))
        self.assertNotEqual(resultado["mediana"], resultado["mediana"])


class LeituraTests(unittest.TestCase):
    def test_mixed_dates_are_normalized_to_utc_in_every_table(self):
        with DiretorioDeDados(
                repositorios="repository,created_at\na/r,2025-01-01T03:00:00+03:00\nb/r,2025-01-02\n",
                releases="repository,published_at\na/r,2025-01-01T21:00:00-03:00\n",
                episodios="repository,started_at,recovered_at\na/r,2025-01-01,\n") as diretorio:
            dados = comum.carregar(diretorio)
        self.assertEqual(dados.repositorios.created_at.iloc[0], pd.Timestamp("2025-01-01", tz="UTC"))
        self.assertEqual(dados.repositorios.created_at.iloc[1], pd.Timestamp("2025-01-02", tz="UTC"))
        self.assertEqual(dados.releases.published_at.iloc[0], pd.Timestamp("2025-01-02", tz="UTC"))
        self.assertEqual(str(dados.episodios.started_at.dt.tz), "UTC")
        self.assertTrue(pd.isna(dados.episodios.recovered_at.iloc[0]))

    def test_whitespace_and_bom_are_accepted_without_turning_missing_text_into_a_category(self):
        with DiretorioDeDados("\ufeffrepository,language,stars\na/r,  , \n") as diretorio:
            dados = comum.carregar(diretorio)
        self.assertTrue(pd.isna(dados.repositorios.language.iloc[0]))
        self.assertTrue(pd.isna(dados.repositorios.stars.iloc[0]))

    def test_reads_the_three_files_with_the_declared_types(self):
        with DiretorioDeDados() as diretorio:
            dados = comum.carregar(diretorio)
        self.assertEqual(list(dados.repositorios["repository"]), ["owner/um", "owner/dois"])
        self.assertEqual(str(dados.repositorios["created_at"].dt.tz), "UTC")
        self.assertEqual(dados.releases["published_at"].iloc[0].hour, 0)
        self.assertTrue(dados.episodios["recovered"].iloc[0])
        self.assertFalse(dados.episodios["censored"].iloc[0])

    def test_empty_cell_is_missing_and_not_zero(self):
        with DiretorioDeDados() as diretorio:
            dados = comum.carregar(diretorio)
        self.assertTrue(pd.isna(dados.repositorios["releases_per_week"].iloc[1]))

    def test_optional_column_absent_becomes_missing_column(self):
        with DiretorioDeDados() as diretorio:
            dados = comum.carregar(diretorio)
        self.assertIn("recovery_hours", dados.repositorios.columns)
        self.assertTrue(dados.repositorios["recovery_hours"].isna().all())

    def test_alias_of_the_delivery_rate_is_accepted(self):
        with DiretorioDeDados("repository,cfr_entrega\nowner/um,0.4\n") as diretorio:
            dados = comum.carregar(diretorio)
        self.assertEqual(dados.repositorios["delivery_change_failure_rate"].iloc[0], 0.4)

    def test_missing_file_names_the_expected_path(self):
        with DiretorioDeDados(repositorios=None) as diretorio:
            with self.assertRaises(FileNotFoundError) as erro:
                comum.carregar(diretorio)
        self.assertIn("repositorios.csv", str(erro.exception))

    def test_missing_required_column_is_rejected(self):
        with DiretorioDeDados("stars\n10\n") as diretorio:
            with self.assertRaises(ValueError) as erro:
                comum.carregar(diretorio)
        self.assertIn("repository", str(erro.exception))

    def test_file_without_rows_loads_as_an_empty_table(self):
        with DiretorioDeDados(episodios="repository,recovery_hours\n") as diretorio:
            dados = comum.carregar(diretorio)
        self.assertTrue(dados.episodios.empty)
        self.assertIn("observed_hours", dados.episodios.columns)


class BooleanoTests(unittest.TestCase):
    def test_reads_the_usual_spellings_and_keeps_the_unknown_as_na(self):
        serie = comum.para_booleano(pd.Series(["True", "false", "SIM", "nao", "1", "0", "", "talvez"]))
        self.assertEqual(list(serie[:6]), [True, False, True, False, True, False])
        self.assertTrue(serie[6:].isna().all())

    def test_already_boolean_column_is_preserved(self):
        serie = comum.para_booleano(pd.Series([True, False]))
        self.assertEqual(list(serie), [True, False])


class SaidaTests(unittest.TestCase):
    def test_number_uses_the_decimal_comma_of_the_article(self):
        self.assertEqual(comum.numero(1234.5678), "1.234,57")
        self.assertEqual(comum.numero(0.5, 3), "0,500")
        self.assertEqual(comum.numero(float("nan")), "--")
        self.assertEqual(comum.numero(None), "--")

    def test_latex_escapes_the_characters_of_repository_names(self):
        self.assertEqual(comum.escapar("owner/repo_name & co"), r"owner/repo\_name \& co")

    def test_latex_table_has_a_column_per_field_and_missing_values_as_dash(self):
        quadro = pd.DataFrame({"metrica": ["RQ 01"], "n": [3], "mediana": [1.5],
                               "censurado": [True], "vazio": [float("nan")]})
        tex = comum.tabela_latex(quadro, casas=2)
        self.assertIn(r"\begin{tabular}{lrrrr}", tex)
        self.assertIn(r"RQ 01 & 3 & 1,50 & sim & -- \\", tex)
        self.assertIn(r"\end{tabular}", tex)

    def test_table_is_written_as_csv_and_tex(self):
        quadro = pd.DataFrame({"indicador": ["Episódios"], "valor": [8]})
        with TemporaryDirectory() as saida:
            csv, tex = comum.salvar_tabela(quadro, Path(saida), "exemplo")
            self.assertEqual(csv.read_text(encoding="utf-8").splitlines()[0], "indicador,valor")
            self.assertIn("Episódios & 8", tex.read_text(encoding="utf-8"))

    def test_json_writes_missing_values_as_null(self):
        with TemporaryDirectory() as saida:
            caminho = comum.salvar_json({"mediana": float("nan"), "n": 3}, Path(saida), "numeros")
            self.assertIn('"mediana": null', caminho.read_text(encoding="utf-8"))

    def test_json_keeps_lists_and_renders_dates_as_text(self):
        conteudo = comum.serializavel({"horas": [1.0, float("nan"), pd.NA, None],
                                       "janela": pd.Timestamp("2025-01-01T00:00:00Z")})
        self.assertEqual(conteudo["horas"], [1.0, None, None, None])
        self.assertEqual(conteudo["janela"], "2025-01-01 00:00:00+00:00")

    def test_text_always_ends_with_a_newline(self):
        with TemporaryDirectory() as saida:
            caminho = comum.salvar_texto("rascunho", Path(saida), "notas")
            self.assertEqual(caminho.read_text(encoding="utf-8"), "rascunho\n")


class EfeitoTests(unittest.TestCase):
    def test_epsilon_uses_the_specified_formula(self):
        # H = 3, n = 7: 3/(7-1) = 1/2; não subtrai o número de grupos.
        self.assertEqual(comum.epsilon_quadrado(3, 7), 0.5)
        self.assertEqual(comum.epsilon_quadrado(0, 7), 0.0)

    def test_epsilon_without_observations_is_undefined(self):
        for n in (0, 1):
            self.assertTrue(math.isnan(comum.epsilon_quadrado(0, n)))
        for h in (None, float("nan")):
            self.assertTrue(math.isnan(comum.epsilon_quadrado(h, 4)))
        with self.assertRaises(ValueError):
            comum.epsilon_quadrado(-1, 4)

    def test_delta_counts_wins_losses_and_ties_by_hand(self):
        # x=[1,3], y=[2,3]: uma vitória, duas derrotas e um empate.
        # U1 = 1 + 1/2 = 1,5; δ = 2*1,5/4 - 1 = -1/4.
        self.assertEqual(comum.cliffs_delta([1, 3], [2, 3]), -0.25)
        self.assertEqual(comum.cliffs_delta([2, 3], [1, 3]), 0.25)

    def test_delta_extremes_and_identical_samples(self):
        self.assertEqual(comum.cliffs_delta([3, 4], [1, 2]), 1.0)
        self.assertEqual(comum.cliffs_delta([1, 2], [3, 4]), -1.0)
        self.assertEqual(comum.cliffs_delta([2, 2], [2, 2]), 0.0)

    def test_delta_excludes_missing_values_from_both_denominators(self):
        self.assertEqual(comum.cliffs_delta([1, None, 3], [2, 3, float("nan")]), -0.25)
        for x, y in (([], [1]), ([1], []), ([None], [1])):
            self.assertTrue(math.isnan(comum.cliffs_delta(x, y)))

    def test_romano_boundaries_are_symmetric_and_upper_category_is_inclusive(self):
        for delta, esperado in ((0, "desprezível"), (0.1469, "desprezível"), (0.147, "pequeno"),
                                (0.3299, "pequeno"), (0.33, "médio"), (0.4739, "médio"),
                                (0.474, "grande"), (1, "grande")):
            for sinal in (-1, 1):
                self.assertEqual(comum.interpretar_cliffs_delta(sinal * delta), esperado)
        self.assertEqual(comum.interpretar_cliffs_delta(float("nan")), "indefinido")
        self.assertEqual(comum.interpretar_cliffs_delta(None), "indefinido")
        with self.assertRaises(ValueError):
            comum.interpretar_cliffs_delta(1.01)


class TestesNaoParametricosTests(unittest.TestCase):
    def test_kruskal_wallis_ranks_calculated_by_hand(self):
        # Postos [1,2] e [3,4]: H = 12/(4*5)*(3²/2+7²/2)-3*5 = 2,4.
        resultado = comum.kruskal_wallis([1, 2, None], [3, 4])
        self.assertEqual(resultado["n"], 4)
        self.assertAlmostEqual(resultado["h"], 2.4)
        self.assertAlmostEqual(resultado["epsilon_quadrado"], 0.8)
        self.assertAlmostEqual(resultado["p"], math.erfc(math.sqrt(1.2)))

    def test_kruskal_constant_or_empty_groups(self):
        self.assertEqual(comum.kruskal_wallis([1, 1], [1]),
                         {"n": 3, "h": 0.0, "p": 1.0, "epsilon_quadrado": 0.0})
        self.assertTrue(math.isnan(comum.kruskal_wallis([], [1])["p"]))
        with self.assertRaises(ValueError):
            comum.kruskal_wallis([1])

    def test_mann_whitney_exact_probability_and_direction(self):
        # [1,2] vs [3,4]: U1=0, δ=-1. Entre C(4,2)=6 partições,
        # duas são tão extremas quanto a observada: p bilateral = 2/6 = 1/3.
        resultado = comum.mann_whitney([1, 2, None], [3, 4])
        self.assertEqual((resultado["n1"], resultado["n2"], resultado["u"]), (2, 2, 0.0))
        self.assertAlmostEqual(resultado["p"], 1 / 3)
        self.assertEqual((resultado["delta"], resultado["interpretacao"]), (-1, "grande"))
        self.assertEqual(comum.mann_whitney([1, 3], [2, 3])["delta"], -0.25)

    def test_empty_mann_whitney_is_undefined(self):
        resultado = comum.mann_whitney([], [1])
        self.assertTrue(math.isnan(resultado["p"]))
        self.assertEqual(resultado["interpretacao"], "indefinido")


class HolmTests(unittest.TestCase):
    def test_holm_restores_original_order_and_enforces_monotonicity(self):
        # Ordenados: 0,01*3=0,03; 0,03*2=0,06; 0,04*1=0,04.
        # Máximos acumulados: 0,03; 0,06; 0,06. Ordem original: 0,06; 0,03; 0,06.
        resultado = comum.holm(pd.Series([0.04, 0.01, 0.03], index=["c", "a", "b"]))
        self.assertEqual(list(resultado.index), ["c", "a", "b"])
        for valor, esperado in zip(resultado.p_holm, [0.06, 0.03, 0.06]):
            self.assertAlmostEqual(valor, esperado)
        self.assertEqual(list(resultado.rejeita), [False, True, False])

    def test_missing_p_is_kept_undefined_and_does_not_contaminate_valid_tests(self):
        resultado = comum.holm([0.01, None, 0.04])
        self.assertEqual(list(resultado.p_holm.dropna()), [0.02, 0.04])
        self.assertTrue(pd.isna(resultado.rejeita.iloc[1]))
        self.assertTrue(comum.holm([]).empty)
        self.assertTrue(comum.holm([None]).p_holm.isna().all())

    def test_holm_caps_at_one_and_respects_custom_alpha(self):
        resultado = comum.holm([0.9, 0.8])
        self.assertEqual(list(resultado.p_holm), [1.0, 1.0])
        self.assertEqual(list(comum.holm([0.04], alpha=0.01).rejeita), [False])

    def test_invalid_probabilities_and_alpha_are_rejected(self):
        for p in (-0.1, 1.1, float("inf")):
            with self.assertRaises(ValueError):
                comum.holm([p])
        for alpha in (0, 1, float("nan")):
            with self.assertRaises(ValueError):
                comum.holm([0.5], alpha=alpha)


class KappaTests(unittest.TestCase):
    def test_landis_koch_inclusive_boundaries(self):
        for kappa, esperado in ((-0.1, "pobre"), (0, "leve"), (0.2, "leve"),
                                (0.2001, "razoável"), (0.4, "razoável"), (0.4001, "moderada"),
                                (0.6, "moderada"), (0.6001, "substancial"), (0.8, "substancial"),
                                (0.8001, "quase perfeita"), (1, "quase perfeita")):
            self.assertEqual(comum.landis_koch(kappa), esperado)
        for kappa in (None, float("nan"), float("inf")):
            self.assertEqual(comum.landis_koch(kappa), "indefinido")

class ReproducaoTests(unittest.TestCase):
    def test_clean_copy_with_only_source_and_csvs_runs_the_module_twice(self):
        raiz = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as temporario:
            clone = Path(temporario)
            for pacote in ("analise", "dora_selection", "validacao"):
                shutil.copytree(raiz / pacote, clone / pacote,
                                ignore=shutil.ignore_patterns("__pycache__", "*.csv"))
            with DiretorioDeDados(repositorios=REPOSITORIOS.replace("owner/dois,,", "owner/dois,3,")) as dados:
                shutil.copytree(dados, clone / "data/processed")
            ambiente = dict(os.environ, MPLCONFIGDIR=str(clone / "mplconfig"), PYTHONUTF8="1")
            ambiente.pop("GITHUB_TOKEN", None)
            ambiente.pop("PYTHONPATH", None)
            # A cópia é um programa independente: não deve misturar cobertura
            # de fontes temporárias (apagadas depois) com a suíte do clone real.
            for chave in tuple(ambiente):
                if chave.startswith("COV_CORE_") or chave == "COVERAGE_PROCESS_START":
                    ambiente.pop(chave)
            comando = [sys.executable, "-m", "analise"]
            primeira = subprocess.run(comando, cwd=clone, env=ambiente, capture_output=True, text=True,
                                      encoding="utf-8", timeout=90)
            self.assertEqual(primeira.returncode, 0, primeira.stdout + primeira.stderr)
            self.assertIn("rq01_04:", primeira.stdout)
            self.assertIn("classificacao_c1:", primeira.stdout)
            saidas = {str(p.relative_to(clone)): p.read_bytes()
                      for p in (clone / "resultados").rglob("*") if p.is_file()}
            self.assertTrue(any(p.endswith(".csv") for p in saidas))
            self.assertTrue(any(p.endswith(".tex") for p in saidas))
            pdfs = [p for p in saidas if p.endswith(".pdf")]
            self.assertGreaterEqual(len(pdfs), 5)
            for p in pdfs:
                self.assertTrue(saidas[p].startswith(b"%PDF-"))
                self.assertNotIn(b"/Subtype /Image", saidas[p])
                self.assertIn(b"/FontFile2", saidas[p])
            segunda = subprocess.run(comando, cwd=clone, env=ambiente, capture_output=True, text=True,
                                     encoding="utf-8", timeout=90)
            self.assertEqual(segunda.returncode, 0, segunda.stdout + segunda.stderr)
            self.assertEqual(saidas, {str(p.relative_to(clone)): p.read_bytes()
                                     for p in (clone / "resultados").rglob("*") if p.is_file()})

    def test_shared_figure_defaults_and_pdf_writer(self):
        plt = estilo.aplicar()
        self.assertEqual(list(plt.rcParams["figure.figsize"]), list(estilo.TAMANHO_SIMPLES))
        self.assertEqual(plt.rcParams["font.size"], 8)
        self.assertEqual(plt.rcParams["pdf.fonttype"], 42)
        with TemporaryDirectory() as temporario:
            fig, eixo = plt.subplots()
            eixo.plot([1, 2], [2, 3])
            caminho = estilo.salvar(fig, temporario, "exemplo")
            self.assertTrue(caminho.read_bytes().startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
