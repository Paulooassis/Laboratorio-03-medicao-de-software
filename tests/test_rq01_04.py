"""RQ 01 a 04: mediana, IQR, as duas variantes obrigatórias e a contabilidade da censura.

A amostra tem quatro repositórios com valores escolhidos para que cada estatística
saia à mão:

- releases por semana: 1, 2, 3 e 0, logo mediana 1,5, Q1 0,75, Q3 2,25 e IQR 1,5;
- Lead Time (a): 24 h, 48 h e 120 h, mediana 48 h e IQR 48 h; (b): 12 h, 24 h e 12 h,
  mediana 12 h e IQR 6 h; as razões (a)/(b) são 2, 2 e 10, logo mediana 2 e IQR 4;
- CFR (a): 0,5, 0,25 e 0,75, mediana 0,5 e IQR 0,25; CFR (b) calculado das releases:
  1/2, 0/2 e 1/1, mediana 0,5 e IQR 0,5;
- recuperação: medianas 4 h, 10 h e 30 h, logo mediana 10 h e IQR 13 h; tratando os
  censurados como recuperados no fim da janela, 6 h, 30 h e 30 h, mediana 30 h.

`owner/tres` tem o commit antigo "esquecido": a release `v3.0` cobre 120 h, dez vezes
a mediana dos seus próprios commits.
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from analise import comum, rq01_04
from analise.__main__ import main


REPOSITORIOS = """repository,releases,releases_per_week,release_lead_time_hours,commit_lead_time_hours,releases_no_previous,releases_compare_not_found,releases_compare_error,releases_no_new_commits,releases_no_commit_dates,considered_runs,ignored_runs,change_failure_rate,delivery_change_failure_rate,recovery_hours
owner/um,4,1.0,24,12,1,1,0,0,0,10,2,0.5,0.9,4
owner/dois,8,2.0,48,24,0,0,1,0,0,8,1,0.25,0.9,10
owner/tres,12,3.0,120,12,0,0,0,2,1,4,0,0.75,0.9,30
owner/quatro,0,0.0,,,0,0,0,0,0,0,0,,,
"""
RELEASES = """repository,release_id,tag_name,published_at,status,comparison_status,commits,measured_commits,first_commit_author_date,last_commit_author_date,lead_time_hours,median_commit_lead_time_hours,corrective,censored,failed,fixed_by_tag_name
owner/um,1,v1.0,2025-03-01T00:00:00Z,measured,completed,3,3,2025-02-28T00:00:00Z,2025-02-28T12:00:00Z,24,24,False,False,True,v1.0.1
owner/um,2,v1.0.1,2025-03-03T00:00:00Z,measured,completed,1,1,2025-03-02T00:00:00Z,2025-03-02T00:00:00Z,24,24,True,False,False,
owner/um,3,v1.1,2025-12-30T00:00:00Z,measured,completed,2,2,2025-12-29T00:00:00Z,2025-12-29T12:00:00Z,24,18,False,True,False,
owner/dois,4,v2.0,2025-04-01T00:00:00Z,measured,completed,4,4,2025-03-30T00:00:00Z,2025-03-31T00:00:00Z,48,24,False,False,False,
owner/dois,5,v2.1,2025-05-01T00:00:00Z,measured,completed,4,4,2025-04-29T00:00:00Z,2025-04-30T00:00:00Z,48,24,False,False,False,
owner/tres,6,v3.0,2025-06-05T00:00:00Z,measured,completed,5,5,2025-05-31T05:00:00Z,2025-06-04T17:00:00Z,120,12,False,False,True,v3.0.1
owner/tres,7,v3.0.1,2025-12-28T00:00:00Z,measured,completed,1,1,2025-12-27T12:00:00Z,2025-12-27T12:00:00Z,12,12,True,True,False,
"""
EPISODIOS = """repository,workflow_id,failure_run_id,failures,started_at,recovered_at,recovery_hours,observed_hours,recovered,censored,inconsistent
owner/um,7,101,1,2025-02-01T00:00:00Z,2025-02-01T02:00:00Z,2,,True,False,False
owner/um,7,102,2,2025-03-01T00:00:00Z,2025-03-01T06:00:00Z,6,,True,False,False
owner/um,8,103,1,2025-12-27T00:00:00Z,,,100,False,True,False
owner/dois,9,104,1,2025-04-01T00:00:00Z,2025-04-01T10:00:00Z,10,,True,False,False
owner/dois,9,105,1,2025-12-29T00:00:00Z,,,50,False,True,False
owner/tres,10,106,1,2025-06-01T00:00:00Z,2025-06-01T20:00:00Z,20,,True,False,False
owner/tres,10,107,3,2025-07-01T00:00:00Z,2025-07-02T16:00:00Z,40,,True,False,False
owner/tres,11,108,1,2025-08-01T00:00:00Z,2025-07-31T19:00:00Z,-5,,True,False,True
"""
VAZIOS = {"repositorios": "repository\n", "releases": "repository,published_at\n",
          "episodios": "repository\n"}


class Amostra:
    """Os três CSVs da amostra em disco, com o diretório de saída ao lado."""

    def __init__(self, repositorios=REPOSITORIOS, releases=RELEASES, episodios=EPISODIOS):
        self.temporario = TemporaryDirectory()
        self.raiz = Path(self.temporario.name)
        self.dados_em, self.saida = self.raiz / "dados", self.raiz / "resultados"
        self.dados_em.mkdir()
        for nome, conteudo in (("repositorios.csv", repositorios), ("releases.csv", releases),
                               ("episodios_falha.csv", episodios)):
            (self.dados_em / nome).write_text(conteudo, encoding="utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *erro):
        self.temporario.cleanup()

    def carregar(self):
        return comum.carregar(self.dados_em)

    def executar(self):
        return rq01_04.executar(self.carregar(), self.saida)


def sem_colunas(csv, colunas):
    """O mesmo CSV sem as colunas indicadas, para exercitar os dados incompletos."""
    linhas = [linha.split(",") for linha in csv.strip().split("\n")]
    manter = [indice for indice, nome in enumerate(linhas[0]) if nome not in colunas]
    return "\n".join(",".join(linha[indice] for indice in manter) for linha in linhas) + "\n"


class RQ01Tests(unittest.TestCase):
    def test_median_and_iqr_of_releases_per_week(self):
        with Amostra() as amostra:
            resultado = rq01_04.rq01(amostra.carregar(), amostra.saida)
        self.assertEqual(resultado["resumo"], {"n": 4, "ausentes": 0, "mediana": 1.5, "q1": 0.75,
                                               "q3": 2.25, "iqr": 1.5})

    def test_repository_without_release_counts_as_zero_and_is_reported(self):
        with Amostra() as amostra:
            resultado = rq01_04.rq01(amostra.carregar(), amostra.saida)
        self.assertEqual(resultado["repositorios_sem_release"], 1)
        self.assertEqual(resultado["resumo"]["n"], 4)

    def test_writes_the_distribution_figure(self):
        with Amostra() as amostra:
            rq01_04.rq01(amostra.carregar(), amostra.saida)
            self.assertTrue((amostra.saida / "figuras" / "rq01_deployment_frequency.pdf").is_file())


class RQ02Tests(unittest.TestCase):
    def test_both_variants_in_hours_and_in_days(self):
        with Amostra() as amostra:
            resultado = rq01_04.rq02(amostra.carregar(), amostra.saida)
        self.assertEqual(resultado["a_release"]["horas"],
                         {"n": 3, "ausentes": 1, "mediana": 48.0, "q1": 36.0, "q3": 84.0,
                          "iqr": 48.0})
        self.assertEqual(resultado["b_commit"]["horas"],
                         {"n": 3, "ausentes": 1, "mediana": 12.0, "q1": 12.0, "q3": 18.0,
                          "iqr": 6.0})
        self.assertEqual(resultado["a_release"]["dias"]["mediana"], 2.0)
        self.assertEqual(resultado["b_commit"]["dias"]["mediana"], 0.5)

    def test_the_ratio_quantifies_the_divergence(self):
        with Amostra() as amostra:
            resultado = rq01_04.rq02(amostra.carregar(), amostra.saida)
        self.assertEqual(resultado["razao_a_b"]["mediana"], 2.0)
        self.assertEqual(resultado["razao_a_b"]["iqr"], 4.0)
        self.assertEqual(resultado["razao_a_b"]["n"], 3)

    def test_the_largest_ratios_point_at_the_forgotten_old_commit(self):
        with Amostra() as amostra:
            resultado = rq01_04.rq02(amostra.carregar(), amostra.saida)
        maiores = resultado["maiores_razoes"]
        primeiro = maiores.iloc[0]
        self.assertEqual(primeiro["repository"], "owner/tres")
        self.assertEqual((primeiro["razao_a_b"], primeiro["tag_name"]), (10.0, "v3.0"))
        # v3.0 cobre 120 h e a mediana dos seus commits é 12 h: um commit muito antigo.
        self.assertEqual(primeiro["razao_release_commits"], 10.0)
        self.assertTrue(primeiro["commit_antigo_esquecido"])
        self.assertEqual(resultado["repositorios_com_commit_antigo_esquecido"], 2)
        self.assertFalse(maiores.set_index("repository").loc["owner/um", "commit_antigo_esquecido"])

    def test_at_most_five_repositories_are_inspected(self):
        with Amostra() as amostra:
            resultado = rq01_04.rq02(amostra.carregar(), amostra.saida)
        self.assertLessEqual(len(resultado["maiores_razoes"]), rq01_04.TOPO_RAZAO)

    def test_ignored_releases_are_counted_by_reason(self):
        with Amostra() as amostra:
            tabela = rq01_04.releases_ignoradas(amostra.carregar())
        contagem = dict(zip(tabela["coluna"], tabela["releases"]))
        self.assertEqual(contagem["releases_no_previous"], 1)
        self.assertEqual(contagem["releases_compare_not_found"], 1)
        self.assertEqual(contagem["releases_compare_error"], 1)
        self.assertEqual(contagem["releases_no_new_commits"], 2)
        self.assertEqual(contagem["releases_no_commit_dates"], 1)
        self.assertEqual(tabela.iloc[-1]["releases"], 6)

    def test_ignored_releases_fall_back_to_the_release_table(self):
        colunas = {"releases_no_previous", "releases_compare_not_found",
                   "releases_compare_error", "releases_no_new_commits",
                   "releases_no_commit_dates"}
        releases = RELEASES.replace("measured,completed", "no_commits,completed", 1)
        with Amostra(sem_colunas(REPOSITORIOS, colunas), releases) as amostra:
            tabela = rq01_04.releases_ignoradas(amostra.carregar())
        linha = tabela.set_index("coluna").loc["releases_no_new_commits"]
        self.assertEqual((linha["releases"], linha["origem"]), (1, "releases.csv"))

    def test_counts_the_compare_with_404_apart_from_other_errors(self):
        releases = RELEASES.replace("measured,completed", "no_comparison,not_found", 1)
        with Amostra(sem_colunas(REPOSITORIOS, {"releases_compare_not_found",
                                                "releases_compare_error"}), releases) as amostra:
            tabela = rq01_04.releases_ignoradas(amostra.carregar()).set_index("coluna")
        self.assertEqual(tabela.loc["releases_compare_not_found", "releases"], 1)
        self.assertEqual(tabela.loc["releases_compare_error", "releases"], 0)


class RQ03Tests(unittest.TestCase):
    def test_both_variants_have_median_and_iqr(self):
        with Amostra() as amostra:
            resultado = rq01_04.rq03(amostra.carregar(), amostra.saida)
        self.assertEqual(resultado["a_ci"]["resumo"]["mediana"], 0.5)
        self.assertEqual(resultado["a_ci"]["resumo"]["iqr"], 0.25)
        self.assertEqual(resultado["b_entrega"]["resumo"]["mediana"], 0.5)
        self.assertEqual(resultado["b_entrega"]["resumo"]["iqr"], 0.5)
        self.assertEqual(resultado["b_entrega"]["resumo"]["n"], 3)

    def test_reports_what_entered_and_what_was_left_out(self):
        with Amostra() as amostra:
            resultado = rq01_04.rq03(amostra.carregar(), amostra.saida)
        self.assertEqual(resultado["a_ci"]["runs_considerados"], 22)
        self.assertEqual(resultado["a_ci"]["runs_ignorados"], 3)
        self.assertEqual(resultado["a_ci"]["repositorios_sem_run_considerado"], 1)
        self.assertEqual(resultado["b_entrega"]["releases_avaliadas"], 5)
        self.assertEqual(resultado["b_entrega"]["releases_que_falharam"], 2)
        self.assertEqual(resultado["b_entrega"]["releases_censuradas"], 2)

    def test_delivery_rate_comes_from_the_releases_not_from_the_summary(self):
        with Amostra() as amostra:
            resultado = rq01_04.rq03(amostra.carregar(), amostra.saida)
        self.assertEqual(resultado["b_entrega"]["origem"], "releases.csv")
        por_repositorio = resultado["por_repositorio"].set_index("repository")
        self.assertEqual(por_repositorio.loc["owner/um", "cfr_entrega"], 0.5)
        self.assertEqual(por_repositorio.loc["owner/tres", "avaliadas"], 1)

    def test_without_a_verdict_in_the_releases_it_uses_the_summary_column(self):
        with Amostra(releases=sem_colunas(RELEASES, {"censored", "failed"})) as amostra:
            resultado = rq01_04.rq03(amostra.carregar(), amostra.saida)
        self.assertEqual(resultado["b_entrega"]["origem"], "repositorios.csv")
        self.assertEqual(resultado["b_entrega"]["resumo"]["mediana"], 0.9)

    def test_release_without_publication_date_is_not_evaluable(self):
        releases = RELEASES.replace("v1.1,2025-12-30T00:00:00Z", "v1.1,")
        with Amostra(releases=releases) as amostra:
            resultado = rq01_04.rq03(amostra.carregar(), amostra.saida)
        self.assertEqual(resultado["b_entrega"]["releases_censuradas"], 1)
        self.assertEqual(resultado["b_entrega"]["releases_avaliadas"], 5)


class RQ04Tests(unittest.TestCase):
    def test_median_and_iqr_use_only_recovered_episodes(self):
        with Amostra() as amostra:
            resultado = rq01_04.rq04(amostra.carregar(), amostra.saida)
        self.assertEqual(resultado["recuperados"]["horas"]["mediana"], 10.0)
        self.assertEqual(resultado["recuperados"]["horas"]["iqr"], 13.0)
        self.assertEqual(resultado["recuperados"]["origem"], "episodios_falha.csv")

    def test_counts_every_outcome_of_the_episodes(self):
        with Amostra() as amostra:
            resultado = rq01_04.rq04(amostra.carregar(), amostra.saida)
        self.assertEqual(resultado["episodios"],
                         {"total": 8, "recuperados": 6, "censurados": 2, "inconsistentes": 1})

    def test_censored_share_per_repository(self):
        with Amostra() as amostra:
            resultado = rq01_04.rq04(amostra.carregar(), amostra.saida)
        por_repositorio = resultado["por_repositorio"].set_index("repository")
        self.assertAlmostEqual(por_repositorio.loc["owner/um", "proporcao_censurada"], 1 / 3)
        self.assertEqual(por_repositorio.loc["owner/dois", "proporcao_censurada"], 0.5)
        self.assertEqual(por_repositorio.loc["owner/tres", "proporcao_censurada"], 0.0)
        self.assertAlmostEqual(resultado["proporcao_censurada"]["mediana"], 1 / 3)

    def test_lower_bound_quantifies_the_censoring_bias(self):
        with Amostra() as amostra:
            resultado = rq01_04.rq04(amostra.carregar(), amostra.saida)
        # owner/um: 2 h, 6 h e um censurado observado por 100 h, mediana 6 h, antes 4 h.
        self.assertEqual(resultado["limite_inferior"]["horas"]["mediana"], 30.0)
        self.assertEqual(resultado["vies_da_censura_horas"], 20.0)
        self.assertGreater(resultado["limite_inferior"]["horas"]["mediana"],
                           resultado["recuperados"]["horas"]["mediana"])

    def test_inconsistent_episode_stays_out_of_both_medians(self):
        with Amostra() as amostra:
            por_repositorio = rq01_04.recuperacao_por_repositorio(amostra.carregar().episodios)
        linha = por_repositorio.set_index("repository").loc["owner/tres"]
        # 20 h e 40 h entram; o episódio com datas contraditórias (-5 h) fica de fora.
        self.assertEqual((linha["mediana_horas"], linha["mediana_limite_horas"]), (30.0, 30.0))
        self.assertEqual(linha["inconsistentes"], 1)

    def test_without_episodes_it_uses_the_summary_column(self):
        with Amostra(episodios=VAZIOS["episodios"]) as amostra:
            resultado = rq01_04.rq04(amostra.carregar(), amostra.saida)
        self.assertEqual(resultado["recuperados"]["origem"], "repositorios.csv")
        self.assertEqual(resultado["recuperados"]["horas"]["mediana"], 10.0)
        self.assertEqual(resultado["episodios"]["total"], 0)


class SinteseTests(unittest.TestCase):
    def test_one_row_per_metric_variant_and_unit(self):
        with Amostra() as amostra:
            resultados = amostra.executar()
        tabela = resultados["sintese"]
        self.assertEqual(list(tabela.columns),
                         ["metrica", "variante", "unidade", "n", "ausentes", "mediana", "q1",
                          "q3", "iqr"])
        lead_time = tabela[tabela["variante"] == "(a) por release"].set_index("unidade")
        self.assertEqual(lead_time.loc["horas", "mediana"], 48.0)
        self.assertEqual(lead_time.loc["dias", "mediana"], 2.0)
        self.assertEqual(set(tabela["variante"]) >= {"(a) por release", "(b) por commit",
                                                     "(a) proxy de CI", "(b) proxy de entrega"},
                         True)

    def test_writes_every_table_figure_and_draft(self):
        with Amostra() as amostra:
            amostra.executar()
            tabelas = {caminho.name for caminho in (amostra.saida / "tabelas").iterdir()}
            figuras = {caminho.name for caminho in (amostra.saida / "figuras").iterdir()}
            self.assertEqual(figuras, {"rq01_deployment_frequency.pdf",
                                       "rq02_lead_time_variantes.pdf", "rq03_cfr_variantes.pdf",
                                       "rq04_tempo_de_recuperacao.pdf"})
            for nome in ("sintese_rq01_04", "rq02_releases_ignoradas", "rq02_razao_lead_time",
                         "rq03_cobertura", "rq04_censura"):
                self.assertIn(f"{nome}.csv", tabelas)
                self.assertIn(f"{nome}.tex", tabelas)
            self.assertTrue((amostra.saida / "texto" / "notas_rq01_04.md").is_file())
            self.assertTrue((amostra.saida / "rq01_04.json").is_file())

    def test_the_draft_carries_the_computed_numbers(self):
        with Amostra() as amostra:
            amostra.executar()
            texto = (amostra.saida / "texto" / "notas_rq01_04.md").read_text(encoding="utf-8")
        self.assertIn("Mediana de 1,50 releases por semana", texto)
        self.assertIn("falha de pipeline não é falha em produção", texto)
        self.assertIn("6 de 7 observadas", texto)
        self.assertIn("uma diferença de 20,00 h", texto)
        self.assertIn("owner/tres", texto)

    def test_census_numbers_are_written_for_the_article(self):
        with Amostra() as amostra:
            amostra.executar()
            censura = (amostra.saida / "tabelas" / "rq04_censura.csv").read_text(encoding="utf-8")
            cobertura = (amostra.saida / "tabelas" / "rq03_cobertura.csv").read_text(encoding="utf-8")
        self.assertIn("Episódios censurados,2", censura)
        self.assertIn("(b) releases censuradas nos últimos 7 dias,2", cobertura)


class DadosIncompletosTests(unittest.TestCase):
    def test_sample_without_any_row_produces_empty_statistics(self):
        with Amostra(**VAZIOS) as amostra:
            resultados = amostra.executar()
            self.assertTrue((amostra.saida / "tabelas" / "sintese_rq01_04.csv").is_file())
        self.assertEqual(resultados["rq01"]["resumo"]["n"], 0)
        self.assertEqual(resultados["rq04"]["episodios"]["total"], 0)
        self.assertTrue(resultados["rq02"]["maiores_razoes"].empty)


class ComandoTests(unittest.TestCase):
    def test_runs_every_registered_analysis(self):
        with Amostra() as amostra:
            self.assertEqual(main(["--dados", str(amostra.dados_em),
                                   "--saida", str(amostra.saida)]), 0)
            self.assertTrue((amostra.saida / "tabelas" / "sintese_rq01_04.csv").is_file())

    def test_runs_only_the_requested_analysis(self):
        with Amostra() as amostra:
            self.assertEqual(main(["--dados", str(amostra.dados_em), "--saida",
                                   str(amostra.saida), "--analise", "rq01_04"]), 0)

    def test_lists_the_registered_analyses(self):
        self.assertEqual(main(["--listar"]), 0)

    def test_missing_csv_ends_with_an_input_error(self):
        with TemporaryDirectory() as vazio:
            self.assertEqual(main(["--dados", vazio]), 2)


if __name__ == "__main__":
    unittest.main()
