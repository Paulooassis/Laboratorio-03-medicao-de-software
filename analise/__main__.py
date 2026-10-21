"""Comando único das análises da Sprint 3: `python -m analise`.

Cada análise é registrada em `ANALISES` e recebe os três CSVs já tipados e o diretório
de saída. Rodar sem argumentos executa todas, na ordem das RQs, e reescreve as tabelas
em `resultados/tabelas/`, as figuras em `resultados/figuras/` e os rascunhos de texto em
`resultados/texto/` — a análise inteira é regenerável a partir dos CSVs.
"""
import argparse
import sys
from pathlib import Path

from . import classificacao_c1, comum, fragilidade, rq01_04, rq05, rq06


ANALISES = {"rq01_04": rq01_04.executar, "classificacao_c1": classificacao_c1.executar,
            "rq05": rq05.executar, "rq06": rq06.executar,
            "fragilidade": fragilidade.executar}


def argumentos(argv):
    parser = argparse.ArgumentParser(
        prog="python -m analise", description="Análises estatísticas das RQs a partir dos CSVs.")
    parser.add_argument("--dados", type=Path, default=comum.DIRETORIO_PADRAO,
                        help="diretório com repositorios.csv, releases.csv e episodios_falha.csv")
    parser.add_argument("--saida", type=Path, default=Path("resultados"),
                        help="diretório das tabelas, figuras e textos gerados")
    parser.add_argument("--analise", action="append", metavar="NOME", choices=sorted(ANALISES),
                        help="executa só esta análise; pode repetir (padrão: todas)")
    parser.add_argument("--listar", action="store_true", help="lista as análises registradas")
    return parser.parse_args(argv)


def main(argv=None):
    args = argumentos(argv)
    if args.listar:
        print("\n".join(sorted(ANALISES)))
        return 0
    try:
        dados = comum.carregar(args.dados)
    except (FileNotFoundError, ValueError) as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 2
    print(f"{len(dados.repositorios)} repositórios, {len(dados.releases)} releases e "
          f"{len(dados.episodios)} episódios de falha em {args.dados}.")
    for nome in args.analise or sorted(ANALISES):
        ANALISES[nome](dados, args.saida)
        print(f"{nome}: tabelas, figuras e textos em {args.saida}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
