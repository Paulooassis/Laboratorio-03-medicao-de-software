"""Subamostra de 30 repositórios do dataset do grupo replicado, com semente fixa.

A replicação cruzada roda o pipeline do outro grupo sobre uma subamostra do dataset
*dele*, não sobre uma lista nossa: é o único jeito de comparar os números obtidos com os
que ele publicou. O sorteio precisa ser reproduzível por qualquer pessoa — inclusive pelo
grupo autor, ao responder as Issues — então três coisas ficam fixas e registradas:

- a **semente** (`SEMENTE`), publicada aqui e repetida no arquivo de metadados;
- a **ordenação do universo antes do sorteio**: a lista é ordenada e deduplicada, de modo
  que o resultado dependa só do *conjunto* de repositórios e da semente, nunca da ordem
  das linhas no CSV do outro grupo;
- o **sha256 do CSV de origem**, que amarra a subamostra ao arquivo exato de onde saiu.

Só a biblioteca padrão, de propósito: a subamostra é sorteada antes de instalar qualquer
coisa do ambiente do outro grupo.
"""
import argparse
import csv
import hashlib
import json
import random
import sys
from pathlib import Path


# Tamanho exigido pelo enunciado da replicação cruzada.
TAMANHO = 30
# Semente do sorteio. O valor em si é arbitrário; o que importa é estar publicado e não
# mudar, para que o mesmo CSV de origem produza sempre a mesma subamostra.
SEMENTE = 42
# Nomes já vistos para a coluna do repositório nos CSVs dos grupos, em ordem de
# preferência. `--coluna` tem prioridade sobre a detecção.
COLUNAS_CONHECIDAS = ("full_name", "repository", "repositorio", "nameWithOwner", "repo",
                      "name_with_owner", "nome", "name", "url")


def sha256(caminho):
    """Impressão digital do CSV de origem, para amarrar a subamostra ao arquivo."""
    resumo = hashlib.sha256()
    with Path(caminho).open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(65536), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def ler_csv(caminho):
    """Linhas do CSV de origem; aceita `,` e `;` como separador, como vem do Excel."""
    caminho = Path(caminho)
    if not caminho.is_file():
        raise FileNotFoundError(f"{caminho} não existe.")
    texto = caminho.read_text(encoding="utf-8-sig")
    cabecalho = texto.split("\n", 1)[0]
    delimitador = ";" if cabecalho.count(";") > cabecalho.count(",") else ","
    linhas = list(csv.DictReader(texto.splitlines(), delimiter=delimitador))
    if not linhas:
        raise ValueError(f"{caminho} não tem nenhuma linha além do cabeçalho.")
    return linhas


def escolher_coluna(linhas, coluna=None):
    """Coluna do repositório: a pedida, ou a primeira conhecida que existir no CSV."""
    disponiveis = [nome for nome in (linhas[0].keys() if linhas else []) if nome]
    if coluna is not None:
        if coluna not in disponiveis:
            raise ValueError(f"A coluna {coluna} não existe no CSV. "
                             f"Colunas: {', '.join(disponiveis)}.")
        return coluna
    for candidata in COLUNAS_CONHECIDAS:
        if candidata in disponiveis:
            return candidata
    raise ValueError("Nenhuma coluna de repositório reconhecida no CSV "
                     f"({', '.join(disponiveis)}); informe --coluna.")


def universo(linhas, coluna):
    """Repositórios distintos do CSV, ordenados: o sorteio não depende da ordem das linhas."""
    valores = {str(linha.get(coluna) or "").strip() for linha in linhas}
    return sorted(valor for valor in valores if valor)


def sortear(repositorios, tamanho=TAMANHO, semente=SEMENTE):
    """Subamostra reproduzível: mesma semente e mesmo conjunto, mesma lista.

    Quando o universo é menor que o tamanho pedido, devolve todo ele — a replicação roda
    com o que existe e a diferença fica registrada nos metadados, em vez de o sorteio
    falhar.
    """
    sorteados = sorted(repositorios)
    if len(sorteados) <= tamanho:
        return sorteados
    return random.Random(semente).sample(sorteados, tamanho)


def subamostra(csv_origem, coluna=None, tamanho=TAMANHO, semente=SEMENTE):
    """A subamostra e os metadados que tornam o sorteio auditável."""
    linhas = ler_csv(csv_origem)
    escolhida = escolher_coluna(linhas, coluna)
    todos = universo(linhas, escolhida)
    sorteados = sortear(todos, tamanho, semente)
    return sorteados, {"csv_origem": str(csv_origem), "sha256_csv_origem": sha256(csv_origem),
                       "coluna": escolhida, "linhas_no_csv": len(linhas),
                       "repositorios_distintos": len(todos), "tamanho_pedido": tamanho,
                       "tamanho_obtido": len(sorteados), "semente": semente,
                       "ordenado_antes_do_sorteio": True}


def gravar(sorteados, metadados, saida):
    """Grava a lista usada e os metadados do sorteio, lado a lado."""
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    lista, dados = saida / "subamostra.csv", saida / "subamostra.json"
    with lista.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(["ordem", "repository"])
        escritor.writerows(enumerate(sorteados, start=1))
    dados.write_text(json.dumps(metadados, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
    return lista, dados


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m replicacao.subamostra",
        description="Sorteia 30 repositórios do CSV do grupo replicado, com semente fixa.")
    parser.add_argument("--csv", required=True, type=Path,
                        help="CSV original do outro grupo, com a lista de repositórios")
    parser.add_argument("--coluna", help="coluna do repositório (padrão: detectada)")
    parser.add_argument("--tamanho", type=int, default=TAMANHO,
                        help=f"tamanho da subamostra (padrão: {TAMANHO})")
    parser.add_argument("--semente", type=int, default=SEMENTE,
                        help=f"semente do sorteio (padrão: {SEMENTE})")
    parser.add_argument("--saida", type=Path, default=Path("replicacao"),
                        help="diretório de subamostra.csv e subamostra.json")
    args = parser.parse_args(argv)
    try:
        sorteados, metadados = subamostra(args.csv, args.coluna, args.tamanho, args.semente)
    except (FileNotFoundError, ValueError) as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 2
    lista, dados = gravar(sorteados, metadados, args.saida)
    print(f"{metadados['tamanho_obtido']} de {metadados['repositorios_distintos']} "
          f"repositórios sorteados com a semente {metadados['semente']} "
          f"(coluna {metadados['coluna']}).")
    print(f"Lista em {lista} e metadados em {dados}.")
    if metadados["tamanho_obtido"] < metadados["tamanho_pedido"]:
        print(f"aviso: o CSV tem menos de {metadados['tamanho_pedido']} repositórios; "
              "a subamostra é o universo inteiro.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
