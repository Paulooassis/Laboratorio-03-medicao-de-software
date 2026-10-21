"""Fragilidade perto dos limites: margem até a faixa vizinha e efeito na categoria geral.

O caso de referência é o que motivou a análise (Issue #62): tempo de recuperação de
169,87 h contra o limite de 168 h entre Medium e Low — 1,87 h, ou 1,10% do valor. Com as
notas (2, 3, 1, 1) a mediana é 1,5 e a categoria geral é Low; se a recuperação sobe um
degrau, as notas viram (2, 3, 1, 2), a mediana vira 2,0 e a categoria vira Medium.
"""
import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from analise import comum, fragilidade
from dora_selection.rating import ELITE, HIGH, LOW, MEDIUM


SWAY = {"repository": "FuelLabs/sway", "deployment_frequency_per_week": 0.4794520547945205,
        "lead_time_a_hours": 154.53722222222223, "cfr_a": 0.4934210526315789,
        "recovery_hours": 169.87444444444444}
CAMPOS = list(SWAY)


class Amostra:
    """CSVs mínimos com os nomes de coluna do pipeline, não os apelidos da análise."""

    def __init__(self, linhas):
        self.temporario = TemporaryDirectory()
        self.raiz = Path(self.temporario.name)
        self.dados_em, self.saida = self.raiz / "dados", self.raiz / "resultados"
        self.dados_em.mkdir()
        with (self.dados_em / "repositorios.csv").open("w", encoding="utf-8", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=CAMPOS, extrasaction="ignore")
            escritor.writeheader()
            escritor.writerows(linhas)
        for nome, cabecalho in (("releases.csv", "repository,published_at\n"),
                                ("episodios_falha.csv", "repository\n")):
            (self.dados_em / nome).write_text(cabecalho, encoding="utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *erro):
        self.temporario.cleanup()

    def carregar(self):
        return comum.carregar(self.dados_em)


class MargemTests(unittest.TestCase):
    def test_measures_the_distance_to_the_nearest_band_boundary(self):
        resultado = fragilidade.margem("recovery_time", 169.87444444444444)
        self.assertEqual(resultado["nivel"], LOW)
        self.assertEqual(resultado["limite"], 168.0)
        self.assertAlmostEqual(resultado["margem"], 1.87444444, places=6)
        self.assertAlmostEqual(resultado["margem_relativa"], 0.011034, places=5)

    def test_picks_the_nearest_boundary_and_not_the_first(self):
        # 23,99 h está a 0,01 h de 24 h (Elite/High) e a 144 h de 168 h.
        resultado = fragilidade.margem("lead_time", 23.99)
        self.assertEqual((resultado["nivel"], resultado["limite"]), (ELITE, 24.0))

    def test_a_missing_value_has_no_margin(self):
        resultado = fragilidade.margem("lead_time", float("nan"))
        self.assertIsNone(resultado["nivel"])
        self.assertNotEqual(resultado["margem"], resultado["margem"])

    def test_boundaries_come_from_the_reference_table(self):
        self.assertEqual(fragilidade.limites("recovery_time"), (1.0, 24.0, 168.0))
        self.assertEqual(fragilidade.limites("change_failure_rate"), (0.15, 0.30, 0.45))


class DegrauTests(unittest.TestCase):
    def test_neighbours_of_a_middle_level_are_both_sides(self):
        self.assertEqual(set(fragilidade.vizinhos(MEDIUM)), {HIGH, LOW})

    def test_the_extremes_have_a_single_neighbour(self):
        self.assertEqual(fragilidade.vizinhos(ELITE), [HIGH])
        self.assertEqual(fragilidade.vizinhos(LOW), [MEDIUM])

    def test_one_step_in_recovery_changes_the_overall_of_the_reported_case(self):
        # Notas (2, 3, 1, 1): mediana 1,5 -> Low. Recuperação um degrau acima -> Medium.
        niveis = {"deployment_frequency": MEDIUM, "lead_time": HIGH,
                  "change_failure_rate": LOW, "recovery_time": LOW}
        self.assertTrue(fragilidade.muda_o_geral(niveis, "recovery_time"))
        self.assertTrue(fragilidade.muda_o_geral(niveis, "change_failure_rate"))

    def test_a_metric_far_from_deciding_does_not_change_the_overall(self):
        # Quatro Elite: mover uma delas para High mantém a mediana em 4 -> Elite.
        niveis = {nome: ELITE for nome in ("deployment_frequency", "lead_time",
                                           "change_failure_rate", "recovery_time")}
        self.assertFalse(fragilidade.muda_o_geral(niveis, "lead_time"))

    def test_an_unclassified_metric_is_not_a_step(self):
        niveis = {"deployment_frequency": MEDIUM, "lead_time": None,
                  "change_failure_rate": LOW, "recovery_time": LOW}
        self.assertFalse(fragilidade.muda_o_geral(niveis, "lead_time"))


class TabelaTests(unittest.TestCase):
    def test_the_reported_case_is_measured_as_in_the_issue(self):
        with Amostra([SWAY]) as amostra:
            quadro = fragilidade.fragilidade(amostra.carregar().repositorios)
        linha = quadro.iloc[0]
        self.assertEqual(linha["overall"], LOW)
        self.assertEqual(linha["metrica_mais_fragil"], "Tempo de recuperação")
        self.assertAlmostEqual(linha["margem"], 1.87444444, places=6)
        self.assertAlmostEqual(linha["margem_relativa"], 0.011034, places=5)
        self.assertTrue(linha["muda_o_geral"])
        self.assertEqual(linha["metricas_que_mudam_o_geral"], 3)

    def test_a_repository_without_metrics_has_no_margin(self):
        with Amostra([{"repository": "owner/vazio"}]) as amostra:
            quadro = fragilidade.fragilidade(amostra.carregar().repositorios)
        linha = quadro.iloc[0]
        self.assertIsNone(linha["overall"])
        self.assertEqual(linha["metrica_mais_fragil"], "")
        self.assertEqual(linha["metricas_que_mudam_o_geral"], 0)

    def test_the_summary_counts_the_sensitive_repositories(self):
        longe = {"repository": "owner/longe", "deployment_frequency_per_week": 10.0,
                 "lead_time_a_hours": 1.0, "cfr_a": 0.01, "recovery_hours": 0.5}
        with Amostra([SWAY, longe]) as amostra:
            quadro = fragilidade.fragilidade(amostra.carregar().repositorios)
        resumo = fragilidade.resumo_fragilidade(quadro)
        self.assertEqual(resumo["repositorios"], 2)
        self.assertEqual(resumo["mais_fragil"], "FuelLabs/sway")
        self.assertEqual(resumo["proximos_do_limite"], 1)

    def test_an_empty_sample_has_an_empty_summary(self):
        resumo = fragilidade.resumo_fragilidade(fragilidade.fragilidade(
            comum.serie_numerica([]).to_frame("repository").iloc[0:0]))
        self.assertEqual(resumo["repositorios"], 0)
        self.assertIsNone(resumo["mais_fragil"])


class SaidasTests(unittest.TestCase):
    def test_writes_the_table_the_figure_and_the_draft(self):
        with Amostra([SWAY]) as amostra:
            fragilidade.executar(amostra.carregar(), amostra.saida)
            tabelas = {caminho.name for caminho in (amostra.saida / "tabelas").iterdir()}
            texto = (amostra.saida / "texto" / "notas_fragilidade.md").read_text(encoding="utf-8")
            self.assertIn("fragilidade_limites.csv", tabelas)
            self.assertIn("fragilidade_limites.tex", tabelas)
            self.assertTrue((amostra.saida / "figuras" / "fragilidade_limites.pdf").is_file())
        self.assertIn("FuelLabs/sway", texto)
        self.assertIn("1,10% do valor", texto)
        self.assertIn("ameaças à validade", texto)

    def test_the_draft_does_not_claim_the_reported_case_is_the_most_fragile(self):
        # Com um repositório ainda mais perto do limite, o texto precisa dizer a posição.
        beira = {"repository": "owner/beira", "deployment_frequency_per_week": 2.0,
                 "lead_time_a_hours": 23.99, "cfr_a": 0.01, "recovery_hours": 0.5}
        with Amostra([SWAY, beira]) as amostra:
            fragilidade.executar(amostra.carregar(), amostra.saida)
            texto = (amostra.saida / "texto" / "notas_fragilidade.md").read_text(encoding="utf-8")
        self.assertIn("é o 2º de 2", texto)
        self.assertIn("owner/beira", texto)

    def test_a_sample_without_the_reported_case_says_so(self):
        outro = {"repository": "owner/outro", "deployment_frequency_per_week": 2.0,
                 "lead_time_a_hours": 100.0, "cfr_a": 0.2, "recovery_hours": 10.0}
        with Amostra([outro]) as amostra:
            fragilidade.executar(amostra.carregar(), amostra.saida)
            texto = (amostra.saida / "texto" / "notas_fragilidade.md").read_text(encoding="utf-8")
        self.assertIn("não está nesta amostra", texto)


if __name__ == "__main__":
    unittest.main()
