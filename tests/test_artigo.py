"""Figuras e tabela de correlação da seção de Resultados.

As métricas DORA são assimétricas, então o estudo reporta Spearman; Pearson entra como
contraste. A amostra deste teste tem uma relação **monótona e não linear** construída de
propósito (y = x³), em que Spearman é exatamente 1 e Pearson fica abaixo — é esse
contraste que a figura do artigo precisa mostrar.
"""
import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from analise import artigo, comum


COLUNAS = ("repository", "deployment_frequency_per_week", "lead_time_a_hours",
           "lead_time_b_hours", "cfr_a", "cfr_b", "recovery_hours")


def monotona_nao_linear(quantidade=12):
    """DF crescente e lead time em x³: ordem idêntica, escala muito diferente."""
    return [{"repository": f"owner/r{i}", "deployment_frequency_per_week": float(i),
             "lead_time_a_hours": float(i) ** 3, "lead_time_b_hours": float(i) ** 3,
             "cfr_a": i / quantidade, "cfr_b": i / quantidade,
             "recovery_hours": float(i)} for i in range(1, quantidade + 1)]


class Amostra:
    def __init__(self, linhas):
        self.temporario = TemporaryDirectory()
        self.raiz = Path(self.temporario.name)
        self.dados_em, self.saida = self.raiz / "dados", self.raiz / "resultados"
        self.dados_em.mkdir()
        with (self.dados_em / "repositorios.csv").open("w", encoding="utf-8", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=list(COLUNAS), extrasaction="ignore")
            escritor.writeheader()
            escritor.writerows(linhas)
        (self.dados_em / "releases.csv").write_text("repository,published_at\n", encoding="utf-8")
        (self.dados_em / "episodios_falha.csv").write_text("repository\n", encoding="utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *erro):
        self.temporario.cleanup()

    def carregar(self):
        return comum.carregar(self.dados_em)


class CorrelacaoTests(unittest.TestCase):
    def test_spearman_is_one_and_pearson_is_lower_on_a_monotone_curve(self):
        with Amostra(monotona_nao_linear()) as amostra:
            tabela = artigo.tabela_correlacao(amostra.carregar().repositorios)
        linha = tabela.set_index("par").loc["DF × LT (a)"]
        self.assertAlmostEqual(linha["spearman"], 1.0, places=9)
        self.assertLess(linha["pearson"], 0.95)
        self.assertGreater(linha["diferenca"], 0.05)

    def test_every_pair_of_metrics_appears_once(self):
        with Amostra(monotona_nao_linear()) as amostra:
            tabela = artigo.tabela_correlacao(amostra.carregar().repositorios)
        # Seis métricas dão 15 pares distintos.
        self.assertEqual(len(tabela), 15)
        self.assertEqual(len(set(tabela["par"])), 15)

    def test_the_matrix_diagonal_is_one_and_symmetric(self):
        with Amostra(monotona_nao_linear()) as amostra:
            matriz, tamanhos = artigo.coeficientes(amostra.carregar().repositorios, "spearman")
        for rotulo in matriz.index:
            self.assertAlmostEqual(matriz.loc[rotulo, rotulo], 1.0, places=9)
        self.assertAlmostEqual(matriz.loc["DF", "CFR (a)"], matriz.loc["CFR (a)", "DF"])
        self.assertEqual(tamanhos.loc["DF", "LT (a)"], 12)

    def test_a_constant_metric_has_no_coefficient_instead_of_zero(self):
        linhas = [{**linha, "cfr_a": 0.5} for linha in monotona_nao_linear()]
        with Amostra(linhas) as amostra:
            matriz, _ = artigo.coeficientes(amostra.carregar().repositorios, "pearson")
        valor = matriz.loc["DF", "CFR (a)"]
        self.assertNotEqual(valor, valor)  # NaN: indefinido, não zero

    def test_a_sample_too_small_for_a_coefficient_is_left_empty(self):
        with Amostra(monotona_nao_linear(2)) as amostra:
            tabela = artigo.tabela_correlacao(amostra.carregar().repositorios)
        self.assertTrue(tabela["spearman"].isna().all())


class FiguraTests(unittest.TestCase):
    def test_writes_the_three_figures_and_the_table(self):
        with Amostra(monotona_nao_linear()) as amostra:
            resultado = artigo.executar(amostra.carregar(), amostra.saida)
            figuras = {caminho.name for caminho in (amostra.saida / "figuras").iterdir()}
            tabelas = {caminho.name for caminho in (amostra.saida / "tabelas").iterdir()}
        self.assertEqual(figuras, {"artigo_violino_metricas.pdf", "artigo_correlacao.pdf",
                                   "artigo_dispersao_df_cfr.pdf"})
        self.assertIn("artigo_correlacao.csv", tabelas)
        self.assertIn("artigo_correlacao.tex", tabelas)
        self.assertEqual(len(resultado["figuras"]), 3)

    def test_the_figures_are_vector_without_embedded_images(self):
        """O artigo sai no template da SBC: figura rasterizada fica ilegível impressa."""
        with Amostra(monotona_nao_linear()) as amostra:
            artigo.executar(amostra.carregar(), amostra.saida)
            for caminho in (amostra.saida / "figuras").iterdir():
                conteudo = caminho.read_bytes()
                self.assertTrue(conteudo.startswith(b"%PDF-"), caminho.name)
                self.assertNotIn(b"/Subtype /Image", conteudo, caminho.name)

    def test_an_empty_sample_still_produces_the_figures(self):
        with Amostra([]) as amostra:
            resultado = artigo.executar(amostra.carregar(), amostra.saida)
            self.assertTrue((amostra.saida / "figuras" / "artigo_correlacao.pdf").is_file())
        # Os 15 pares continuam listados; o que falta é o coeficiente, não a linha.
        self.assertEqual(len(resultado["correlacoes"]), 15)
        self.assertTrue(resultado["correlacoes"]["spearman"].isna().all())


if __name__ == "__main__":
    unittest.main()
