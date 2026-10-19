"""Base comum da análise: leitura dos CSVs, mediana/IQR e as saídas para o artigo.

As séries dos testes têm quartis calculáveis à mão: `[1, 2, 3, 4, 5]` tem mediana 3,
Q1 2 e Q3 4 (interpolação linear, o padrão do pandas e do R), logo IQR 2.
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from analise import comum


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


if __name__ == "__main__":
    unittest.main()
