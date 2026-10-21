"""Subamostra da replicação cruzada: sorteio reproduzível e auditável.

O sorteio tem de dar sempre a mesma lista para o mesmo CSV e a mesma semente — é o que
permite ao grupo autor refazer a subamostra ao responder as Issues. Por isso os testes
cobrem, além do tamanho, duas propriedades: a ordem das linhas no CSV de origem não muda
o resultado, e os metadados identificam o arquivo exato de onde a lista saiu.
"""
import csv
import json
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from replicacao import subamostra as sub


def escrever_csv(caminho, linhas, campos=("full_name", "stars"), delimitador=","):
    with Path(caminho).open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(campos), delimiter=delimitador)
        escritor.writeheader()
        escritor.writerows(linhas)
    return Path(caminho)


def repositorios(quantidade, coluna="full_name"):
    return [{coluna: f"owner{i}/repo{i}", "stars": 1000 + i} for i in range(1, quantidade + 1)]


class Ambiente:
    """Um diretório temporário com o CSV do outro grupo."""

    def __init__(self, linhas=None, campos=("full_name", "stars"), delimitador=","):
        self.temporario = TemporaryDirectory()
        self.raiz = Path(self.temporario.name)
        self.csv = escrever_csv(self.raiz / "repositorios.csv",
                                repositorios(100) if linhas is None else linhas,
                                campos, delimitador)

    def __enter__(self):
        return self

    def __exit__(self, *erro):
        self.temporario.cleanup()


class SorteioTests(unittest.TestCase):
    def test_draws_exactly_thirty_repositories(self):
        sorteados = sub.sortear([f"owner{i}/repo{i}" for i in range(1, 101)])
        self.assertEqual(len(sorteados), sub.TAMANHO)
        self.assertEqual(len(set(sorteados)), sub.TAMANHO)

    def test_the_same_seed_always_gives_the_same_list(self):
        universo = [f"owner{i}/repo{i}" for i in range(1, 101)]
        self.assertEqual(sub.sortear(universo), sub.sortear(universo))

    def test_the_order_of_the_rows_does_not_change_the_draw(self):
        universo = [f"owner{i}/repo{i}" for i in range(1, 101)]
        self.assertEqual(sub.sortear(universo), sub.sortear(list(reversed(universo))))

    def test_a_different_seed_gives_a_different_list(self):
        universo = [f"owner{i}/repo{i}" for i in range(1, 101)]
        self.assertNotEqual(sub.sortear(universo), sub.sortear(universo, semente=7))

    def test_a_universe_smaller_than_the_sample_is_taken_whole(self):
        universo = [f"owner{i}/repo{i}" for i in range(1, 6)]
        self.assertEqual(sub.sortear(universo), sorted(universo))

    def test_every_drawn_repository_comes_from_the_universe(self):
        universo = [f"owner{i}/repo{i}" for i in range(1, 101)]
        self.assertTrue(set(sub.sortear(universo)) <= set(universo))


class UniversoTests(unittest.TestCase):
    def test_repeated_and_blank_repositories_are_dropped(self):
        linhas = [{"full_name": "owner/a"}, {"full_name": "owner/a"}, {"full_name": " "},
                  {"full_name": None}, {"full_name": "owner/b"}]
        self.assertEqual(sub.universo(linhas, "full_name"), ["owner/a", "owner/b"])

    def test_surrounding_spaces_do_not_create_two_repositories(self):
        linhas = [{"full_name": " owner/a "}, {"full_name": "owner/a"}]
        self.assertEqual(sub.universo(linhas, "full_name"), ["owner/a"])


class ColunaTests(unittest.TestCase):
    def test_detects_each_known_spelling_of_the_repository_column(self):
        for nome in ("full_name", "repository", "nameWithOwner", "repo"):
            self.assertEqual(sub.escolher_coluna([{nome: "owner/a"}]), nome, nome)

    def test_the_requested_column_wins_over_detection(self):
        linhas = [{"full_name": "owner/a", "repo": "outro/b"}]
        self.assertEqual(sub.escolher_coluna(linhas, "repo"), "repo")

    def test_an_unknown_column_layout_asks_for_the_option(self):
        with self.assertRaises(ValueError) as erro:
            sub.escolher_coluna([{"projeto": "owner/a", "estrelas": "10"}])
        self.assertIn("--coluna", str(erro.exception))
        self.assertIn("projeto", str(erro.exception))

    def test_a_requested_column_that_does_not_exist_is_rejected(self):
        with self.assertRaises(ValueError) as erro:
            sub.escolher_coluna([{"full_name": "owner/a"}], "repositorio")
        self.assertIn("repositorio", str(erro.exception))


class LeituraTests(unittest.TestCase):
    def test_reads_a_csv_separated_by_semicolons(self):
        with Ambiente(repositorios(40), delimitador=";") as ambiente:
            linhas = sub.ler_csv(ambiente.csv)
        self.assertEqual(len(linhas), 40)
        self.assertEqual(linhas[0]["full_name"], "owner1/repo1")

    def test_a_missing_file_is_reported_with_its_path(self):
        with self.assertRaises(FileNotFoundError) as erro:
            sub.ler_csv(Path("nao") / "existe.csv")
        self.assertIn("existe.csv", str(erro.exception))

    def test_a_csv_with_only_a_header_is_rejected(self):
        with Ambiente([]) as ambiente:
            with self.assertRaises(ValueError) as erro:
                sub.ler_csv(ambiente.csv)
        self.assertIn("nenhuma linha", str(erro.exception))


class MetadadosTests(unittest.TestCase):
    def test_records_the_seed_the_column_and_the_source_fingerprint(self):
        with Ambiente() as ambiente:
            sorteados, metadados = sub.subamostra(ambiente.csv)
            self.assertEqual(metadados["sha256_csv_origem"], sub.sha256(ambiente.csv))
        self.assertEqual(len(sorteados), 30)
        self.assertEqual((metadados["semente"], metadados["coluna"]), (sub.SEMENTE, "full_name"))
        self.assertEqual((metadados["repositorios_distintos"], metadados["tamanho_obtido"]),
                         (100, 30))
        self.assertTrue(metadados["ordenado_antes_do_sorteio"])

    def test_the_fingerprint_changes_when_the_source_csv_changes(self):
        with Ambiente() as ambiente:
            antes = sub.sha256(ambiente.csv)
            escrever_csv(ambiente.csv, repositorios(99))
            self.assertNotEqual(sub.sha256(ambiente.csv), antes)

    def test_a_short_universe_is_recorded_as_such(self):
        with Ambiente(repositorios(12)) as ambiente:
            _, metadados = sub.subamostra(ambiente.csv)
        self.assertEqual((metadados["tamanho_pedido"], metadados["tamanho_obtido"]), (30, 12))


class ComandoTests(unittest.TestCase):
    def test_writes_the_used_list_and_the_metadata(self):
        with Ambiente() as ambiente:
            codigo = sub.main(["--csv", str(ambiente.csv), "--saida", str(ambiente.raiz)])
            lista = (ambiente.raiz / "subamostra.csv").read_text(encoding="utf-8").splitlines()
            dados = json.loads((ambiente.raiz / "subamostra.json").read_text(encoding="utf-8"))
        self.assertEqual(codigo, 0)
        self.assertEqual(lista[0], "ordem,repository")
        self.assertEqual(len(lista), 31)  # cabeçalho mais os 30 sorteados
        self.assertEqual(lista[1].split(",")[0], "1")
        self.assertEqual(dados["semente"], sub.SEMENTE)

    def test_running_twice_produces_the_same_list(self):
        with Ambiente() as ambiente:
            sub.main(["--csv", str(ambiente.csv), "--saida", str(ambiente.raiz)])
            primeira = (ambiente.raiz / "subamostra.csv").read_text(encoding="utf-8")
            sub.main(["--csv", str(ambiente.csv), "--saida", str(ambiente.raiz)])
            segunda = (ambiente.raiz / "subamostra.csv").read_text(encoding="utf-8")
        self.assertEqual(primeira, segunda)

    def test_the_sample_size_and_the_seed_can_be_overridden(self):
        with Ambiente() as ambiente:
            sub.main(["--csv", str(ambiente.csv), "--saida", str(ambiente.raiz),
                      "--tamanho", "5", "--semente", "7"])
            dados = json.loads((ambiente.raiz / "subamostra.json").read_text(encoding="utf-8"))
        self.assertEqual((dados["tamanho_obtido"], dados["semente"]), (5, 7))

    def test_a_short_universe_warns_without_failing(self):
        with Ambiente(repositorios(12)) as ambiente:
            with redirect_stderr(StringIO()) as aviso:
                codigo = sub.main(["--csv", str(ambiente.csv), "--saida", str(ambiente.raiz)])
            lista = (ambiente.raiz / "subamostra.csv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(codigo, 0)
        self.assertIn("menos de 30 repositórios", aviso.getvalue())
        self.assertEqual(len(lista), 13)

    def test_a_csv_that_cannot_be_read_ends_with_an_input_error(self):
        with TemporaryDirectory() as vazio:
            self.assertEqual(sub.main(["--csv", str(Path(vazio) / "nada.csv")]), 2)

    def test_an_unknown_column_layout_ends_with_an_input_error(self):
        with Ambiente([{"projeto": "owner/a"}], campos=("projeto",)) as ambiente:
            self.assertEqual(sub.main(["--csv", str(ambiente.csv), "--saida",
                                       str(ambiente.raiz)]), 2)


if __name__ == "__main__":
    unittest.main()
