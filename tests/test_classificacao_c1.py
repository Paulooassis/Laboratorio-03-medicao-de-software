"""C1: reprodução da classificação DORA a partir do CSV e distribuição das categorias.

O teste central não inventa níveis: monta um repositório com as funções do pipeline
(`repository_metrics` e `classify_repository`), grava os três CSVs a partir dessas
estruturas e confere que a classificação recalculada do CSV bate, métrica a métrica e no
nível geral, com o que o pipeline gravou.

As faixas do enunciado (`dora_selection/rating.py`) dão os valores usados aqui: Elite é
frequência >= 7 releases/semana, Lead Time < 24 h, CFR <= 0,15 e recuperação < 1 h; Low é
frequência < 0,23/semana, Lead Time >= 720 h, CFR > 0,45 e recuperação >= 168 h.
"""
import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from analise import classificacao_c1, comum
from analise.__main__ import main
from dora_selection.metrics import repository_metrics
from dora_selection.output import DORA_FIELDS, dora_row
from dora_selection.rating import ELITE, HIGH, LOW, MEDIUM, classify_repository
from dora_selection.selection import Window, timestamp


REPOSITORIO = "owner/repo"
# As mesmas quatro semanas ISO completas dos testes dos Cards 5 e 6.
JANELA = Window(timestamp("2026-01-05T00:00:00Z"), timestamp("2026-02-01T23:59:59Z"))
# Valores que caem no meio de cada faixa, um por nível, para montar notas conhecidas.
VALORES = {"deployment_frequency": {ELITE: 10.0, HIGH: 2.0, MEDIUM: 0.5, LOW: 0.1},
           "lead_time": {ELITE: 1.0, HIGH: 100.0, MEDIUM: 300.0, LOW: 1000.0},
           "change_failure_rate": {ELITE: 0.10, HIGH: 0.25, MEDIUM: 0.40, LOW: 0.80},
           "recovery_time": {ELITE: 0.5, HIGH: 10.0, MEDIUM: 100.0, LOW: 300.0}}
COLUNAS = {"deployment_frequency": "releases_per_week", "lead_time": "release_lead_time_hours",
           "change_failure_rate": "change_failure_rate", "recovery_time": "recovery_hours"}


def release(numero, published, commits=(), **mudancas):
    return {"repository": REPOSITORIO, "release_id": numero, "tag_name": f"v{numero}",
            "published_at": published, "comparison_status": "completed",
            "commits": list(commits), **mudancas}


def commit(sha, author_date):
    return {"repository": REPOSITORIO, "sha": sha, "author_date": author_date, "message": sha}


def run(numero, classification="success", created="2026-01-05T00:00:00Z", updated=None, **mudancas):
    return {"repository": REPOSITORIO, "workflow_id": 7, "id": numero,
            "classification": classification, "created_at": created,
            "updated_at": updated or created, **mudancas}


def amostra_de_referencia():
    """Releases e workflows com cada métrica conhecida: High, High, Low e High."""
    releases = [
        release(1, "2026-01-06T12:00:00Z", comparison_status="no_previous_release"),
        release(2, "2026-01-13T12:00:00Z", [commit("a", "2026-01-12T12:00:00Z"),
                                            commit("b", "2026-01-13T06:00:00Z")]),
        release(3, "2026-01-20T12:00:00Z", [commit("c", "2026-01-18T12:00:00Z")]),
        release(4, "2026-01-27T12:00:00Z"),
    ]
    ci = [run(1, "success", "2026-01-05T10:00:00Z"),
          run(2, "failure", "2026-01-06T10:00:00Z"),
          run(3, "failure", "2026-01-06T12:00:00Z"),
          run(4, "ignored", "2026-01-06T13:00:00Z"),
          run(5, "success", "2026-01-06T15:00:00Z", "2026-01-06T16:00:00Z"),
          run(6, "failure", "2026-01-10T00:00:00Z"),
          run(7, "success", "2026-01-10T01:30:00Z", "2026-01-10T02:00:00Z"),
          run(8, "ignored", "2026-01-11T00:00:00Z")]
    deploy = [run(9, "success", "2026-01-29T00:00:00Z", workflow_id=8),
              run(10, "failure", "2026-01-30T00:00:00Z", "2026-01-30T00:10:00Z", workflow_id=8)]
    return releases, [{"repository": REPOSITORIO, "workflow_id": 7, "name": "CI", "runs": ci},
                      {"repository": REPOSITORIO, "workflow_id": 8, "name": "Deploy", "runs": deploy}]


class Amostra:
    """Os três CSVs em disco, escritos a partir das estruturas do pipeline."""

    def __init__(self, linhas=None, releases=None, episodios=None):
        self.temporario = TemporaryDirectory()
        self.raiz = Path(self.temporario.name)
        self.dados_em, self.saida = self.raiz / "dados", self.raiz / "resultados"
        self.dados_em.mkdir()
        self.escrever("repositorios.csv", DORA_FIELDS, linhas or [])
        self.escrever("releases.csv", ["repository", "release_id", "tag_name", "published_at",
                                       "status", "commits", "measured_commits", "lead_time_hours",
                                       "median_commit_lead_time_hours"], releases or [])
        self.escrever("episodios_falha.csv",
                      ["repository", "workflow_id", "failure_run_id", "started_at", "recovered_at",
                       "recovery_hours", "observed_hours", "recovered", "censored", "inconsistent"],
                      episodios or [])

    def escrever(self, nome, campos, linhas):
        with (self.dados_em / nome).open("w", encoding="utf-8", newline="") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=campos, extrasaction="ignore")
            escritor.writeheader()
            escritor.writerows(linhas)

    def __enter__(self):
        return self

    def __exit__(self, *erro):
        self.temporario.cleanup()

    def carregar(self):
        return comum.carregar(self.dados_em)

    def classificar(self):
        return classificacao_c1.classificar(self.carregar())


def do_pipeline(releases, workflows, nome=REPOSITORIO):
    """A linha de `repositorios.csv`, as releases e os episódios como o pipeline os grava."""
    metricas = repository_metrics(JANELA, releases, workflows, nome)
    classificacao = classify_repository(metricas)
    linha = dora_row({"full_name": nome, "stars": 5000, "language": "Python",
                      "created_at": "2020-01-01T00:00:00Z", "contributors": 20},
                     metricas, classificacao, True)
    episodios = [episodio for workflow in metricas["recovery_time"]["workflows"]
                 for episodio in workflow["episodes"]]
    return linha, metricas["lead_time_per_release"]["releases"], episodios, classificacao


def com_niveis(**niveis):
    """Linha de CSV cujos valores caem nas faixas dos níveis pedidos."""
    return {"repository": REPOSITORIO,
            **{COLUNAS[metrica]: VALORES[metrica][nivel] for metrica, nivel in niveis.items()}}


class ReproducaoDoPipelineTests(unittest.TestCase):
    """O CSV basta para reconstruir a classificação, sem refazer a coleta."""

    def test_every_level_matches_what_the_pipeline_wrote(self):
        linha, releases, episodios, classificacao = do_pipeline(*amostra_de_referencia())
        with Amostra([linha], releases, episodios) as amostra:
            quadro = amostra.classificar()
        reproduzido = quadro.iloc[0]
        self.assertEqual(reproduzido["divergencias"], "")
        for metrica in ("deployment_frequency", "lead_time", "change_failure_rate",
                        "recovery_time"):
            self.assertEqual(reproduzido[f"{metrica}_level"],
                             classificacao["ratings"][metrica]["level"], metrica)
        self.assertEqual(reproduzido["overall_com_fallback"], classificacao["overall"])

    def test_the_reference_sample_is_high_overall(self):
        linha, releases, episodios, _ = do_pipeline(*amostra_de_referencia())
        with Amostra([linha], releases, episodios) as amostra:
            reproduzido = amostra.classificar().iloc[0]
        # Frequência 1/semana High, Lead Time 36 h High, CFR 0,5 Low e recuperação 4 h High.
        self.assertEqual([reproduzido["deployment_frequency_level"], reproduzido["lead_time_level"],
                          reproduzido["change_failure_rate_level"],
                          reproduzido["recovery_time_level"]], [HIGH, HIGH, LOW, HIGH])
        self.assertEqual(reproduzido["overall"], HIGH)

    def test_the_check_reports_that_every_repository_agrees(self):
        linha, releases, episodios, _ = do_pipeline(*amostra_de_referencia())
        with Amostra([linha], releases, episodios) as amostra:
            checagem = classificacao_c1.conferencia(amostra.classificar())
        self.assertEqual((checagem["verificavel"], checagem["conferem"], checagem["divergentes"]),
                         (True, 1, 0))

    def test_recovery_without_any_recovered_episode_uses_the_censored_bound(self):
        # Única falha da janela, nunca recuperada: o limite inferior já passa de uma semana.
        workflows = [{"repository": REPOSITORIO, "workflow_id": 7, "name": "CI",
                      "runs": [run(1, "success", "2026-01-05T00:00:00Z"),
                               run(2, "failure", "2026-01-06T00:00:00Z")]}]
        linha, releases, episodios, classificacao = do_pipeline([], workflows)
        self.assertEqual(classificacao["ratings"]["recovery_time"]["basis"],
                         "censored_lower_bound")
        with Amostra([linha], releases, episodios) as amostra:
            reproduzido = amostra.classificar().iloc[0]
        self.assertEqual(reproduzido["recovery_time_level"], LOW)
        self.assertEqual(reproduzido["recovery_time_base"], "limite_inferior_dos_censurados")
        self.assertEqual(reproduzido["divergencias"], "")

    def test_a_wrong_level_in_the_csv_is_reported_as_a_divergence(self):
        linha, releases, episodios, _ = do_pipeline(*amostra_de_referencia())
        with Amostra([{**linha, "change_failure_rate_level": ELITE}], releases,
                     episodios) as amostra:
            checagem = classificacao_c1.conferencia(amostra.classificar())
        self.assertEqual(checagem["divergentes"], 1)
        self.assertIn("change_failure_rate_level: pipeline Elite != CSV Low",
                      checagem["divergencias"].iloc[0]["divergencias"])

    def test_csv_without_the_pipeline_columns_is_not_comparable(self):
        with Amostra([com_niveis(deployment_frequency=HIGH)]) as amostra:
            checagem = classificacao_c1.conferencia(amostra.classificar())
        self.assertFalse(checagem["verificavel"])
        self.assertEqual(checagem["divergentes"], 0)


class NivelGeralTests(unittest.TestCase):
    """Mediana das quatro notas, arredondada para baixo, como manda o enunciado."""

    def test_scores_4_3_3_1_have_median_3_and_give_high(self):
        with Amostra([com_niveis(deployment_frequency=ELITE, lead_time=HIGH,
                                 change_failure_rate=HIGH, recovery_time=LOW)]) as amostra:
            linha = amostra.classificar().iloc[0]
        self.assertEqual(linha["median_score"], 3.0)
        self.assertEqual(linha["overall"], HIGH)

    def test_fractional_median_2_5_is_rounded_down_to_medium(self):
        with Amostra([com_niveis(deployment_frequency=ELITE, lead_time=HIGH,
                                 change_failure_rate=MEDIUM, recovery_time=LOW)]) as amostra:
            linha = amostra.classificar().iloc[0]
        self.assertEqual(linha["median_score"], 2.5)
        self.assertEqual((linha["overall_score"], linha["overall"]), (2, MEDIUM))

    def test_missing_metric_leaves_the_median_to_the_available_ones(self):
        with Amostra([com_niveis(deployment_frequency=ELITE, lead_time=ELITE,
                                 change_failure_rate=LOW)]) as amostra:
            linha = amostra.classificar().iloc[0]
        # Três métricas classificadas: notas 4, 4 e 1, mediana 4, sem contar a ausente.
        self.assertEqual((linha["metricas_classificadas"], linha["median_score"]), (3, 4.0))
        self.assertEqual(linha["overall"], ELITE)

    def test_repository_without_any_metric_has_no_overall_level(self):
        with Amostra([{"repository": REPOSITORIO}]) as amostra:
            linha = amostra.classificar().iloc[0]
        self.assertEqual(linha["metricas_classificadas"], 0)
        self.assertIsNone(linha["overall"])

    def test_zero_releases_is_a_measurement_and_not_a_missing_value(self):
        with Amostra([{"repository": REPOSITORIO, "releases_per_week": 0.0}]) as amostra:
            linha = amostra.classificar().iloc[0]
        self.assertEqual(linha["deployment_frequency_level"], LOW)
        self.assertEqual((linha["metricas_classificadas"], linha["overall"]), (1, LOW))


class FallbackDoLeadTimeTests(unittest.TestCase):
    """A C1 estrita só aceita a variante (a); o fallback fica na coluna ao lado."""

    def test_only_the_commit_variant_leaves_the_c1_lead_time_unclassified(self):
        with Amostra([{"repository": REPOSITORIO, "commit_lead_time_hours": 1.0,
                       "releases_per_week": 10.0}]) as amostra:
            linha = amostra.classificar().iloc[0]
        self.assertIsNone(linha["lead_time_level"])
        self.assertEqual(linha["lead_time_variante"], classificacao_c1.SEM_CLASSIFICACAO)
        self.assertTrue(linha["lead_time_apenas_com_b"])
        self.assertEqual(linha["lead_time_level_com_fallback"], ELITE)

    def test_counts_when_the_overall_level_changes_between_the_two_readings(self):
        # Sem a variante (a): notas 4 e 1, mediana 2,5, Medium. Com ela: 4, 4, 1, mediana 4.
        with Amostra([{"repository": REPOSITORIO, "commit_lead_time_hours": 1.0,
                       "releases_per_week": 10.0, "change_failure_rate": 0.80}]) as amostra:
            linha = amostra.classificar().iloc[0]
        self.assertEqual(linha["overall"], MEDIUM)
        self.assertEqual(linha["overall_com_fallback"], ELITE)
        self.assertTrue(linha["overall_mudou_sem_fallback"])

    def test_the_release_variant_is_preferred_when_both_exist(self):
        with Amostra([{"repository": REPOSITORIO, "release_lead_time_hours": 1000.0,
                       "commit_lead_time_hours": 1.0}]) as amostra:
            linha = amostra.classificar().iloc[0]
        self.assertEqual(linha["lead_time_level"], LOW)
        self.assertEqual(linha["lead_time_level_com_fallback"], LOW)
        self.assertFalse(linha["lead_time_apenas_com_b"])
        self.assertEqual(linha["lead_time_variante"], "(a) por release")


class DistribuicaoTests(unittest.TestCase):
    def test_counts_and_shares_of_every_level_including_the_unclassified(self):
        linhas = [{**com_niveis(deployment_frequency=ELITE), "repository": "owner/a"},
                  {**com_niveis(deployment_frequency=LOW), "repository": "owner/b"},
                  {"repository": "owner/c"}]
        with Amostra(linhas) as amostra:
            contagens, percentuais = classificacao_c1.distribuicao(amostra.classificar())
        frequencia = contagens.set_index("metrica").loc["Deployment Frequency"]
        self.assertEqual([frequencia[nivel] for nivel in classificacao_c1.NIVEIS],
                         [1, 0, 0, 1, 1])
        proporcao = percentuais.set_index("metrica").loc["Deployment Frequency"]
        self.assertAlmostEqual(proporcao["Elite"], 1 / 3)
        self.assertAlmostEqual(proporcao[classificacao_c1.SEM_CLASSIFICACAO], 1 / 3)

    def test_has_one_row_per_metric_and_one_for_the_overall_level(self):
        with Amostra([com_niveis(deployment_frequency=HIGH)]) as amostra:
            contagens, _ = classificacao_c1.distribuicao(amostra.classificar())
        self.assertEqual(list(contagens["metrica"]), list(classificacao_c1.ROTULOS.values()))

    def test_coverage_counts_how_many_metrics_each_repository_has(self):
        linhas = [{**com_niveis(deployment_frequency=ELITE, lead_time=ELITE,
                                change_failure_rate=ELITE, recovery_time=ELITE),
                   "repository": "owner/a"},
                  {**com_niveis(deployment_frequency=ELITE), "repository": "owner/b"},
                  {"repository": "owner/c"}]
        with Amostra(linhas) as amostra:
            cobertura = classificacao_c1.cobertura(amostra.classificar())
        contagem = dict(zip(cobertura["metricas_classificadas"], cobertura["repositorios"]))
        self.assertEqual((contagem[4], contagem[1], contagem[0]), (1, 1, 1))
        self.assertAlmostEqual(cobertura.set_index("metricas_classificadas").loc[4, "proporcao"],
                               1 / 3)


class SaidasTests(unittest.TestCase):
    def test_writes_the_csv_tables_figure_and_draft(self):
        linha, releases, episodios, _ = do_pipeline(*amostra_de_referencia())
        with Amostra([linha], releases, episodios) as amostra:
            classificacao_c1.executar(amostra.carregar(), amostra.saida)
            self.assertTrue((amostra.saida / "classificacao_c1.csv").is_file())
            tabelas = {caminho.name for caminho in (amostra.saida / "tabelas").iterdir()}
            for nome in ("classificacao_c1_distribuicao", "classificacao_c1_distribuicao_percentual",
                         "classificacao_c1_cobertura", "classificacao_c1_divergencias"):
                self.assertIn(f"{nome}.csv", tabelas)
                self.assertIn(f"{nome}.tex", tabelas)
            self.assertTrue((amostra.saida / "figuras"
                             / "classificacao_c1_distribuicao.pdf").is_file())
            texto = (amostra.saida / "texto"
                     / "notas_classificacao_c1.md").read_text(encoding="utf-8")
        self.assertIn("1 de 1 repositórios batem", texto)
        self.assertIn("**Decisão registrada: opção (2)**", texto)
        self.assertIn("mediana das notas das métricas disponíveis", texto)

    def test_empty_sample_still_produces_the_tables(self):
        with Amostra() as amostra:
            resultado = classificacao_c1.executar(amostra.carregar(), amostra.saida)
            self.assertTrue((amostra.saida / "classificacao_c1.csv").is_file())
            contagens = resultado["distribuicao"].set_index("metrica")
        self.assertEqual(resultado["repositorios"], 0)
        self.assertEqual(int(contagens.loc["Classificação geral (C1)", "Elite"]), 0)

    def test_the_command_runs_the_registered_analysis(self):
        linha, releases, episodios, _ = do_pipeline(*amostra_de_referencia())
        with Amostra([linha], releases, episodios) as amostra:
            self.assertEqual(main(["--dados", str(amostra.dados_em), "--saida",
                                   str(amostra.saida), "--analise", "classificacao_c1"]), 0)
            self.assertTrue((amostra.saida / "classificacao_c1.csv").is_file())


if __name__ == "__main__":
    unittest.main()
