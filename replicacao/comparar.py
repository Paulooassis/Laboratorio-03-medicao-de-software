"""Compara os CSVs do grupo replicado sem recoletar dados nem reclassificar DORA.

Uso: python -m replicacao.comparar
Diferenças relativas são proporções; zero no original torna a razão indefinida,
inclusive 0/0. Ausências permanecem ausências e continuam no denominador amostral.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from analise import comum, estilo


METRICAS = {
    "deploy_frequency_semana": "DF (semana)",
    "lead_time_release_h": "LT release (h)",
    "lead_time_commit_h": "LT commit (h)",
    "cfr_ci": "CFR CI",
    "cfr_entrega": "CFR entrega",
    "tempo_recuperacao_h": "Recuperação (h)",
    "rework_rate": "Retrabalho",
}
CATEGORIAS = {
    "categoria_dora_frequencia": "DF",
    "categoria_dora_lead_time": "LT C1",
    "categoria_dora_cfr": "CFR C1",
    "categoria_dora_recuperacao": "Recuperação",
    "categoria_dora_geral": "Geral",
}
NIVEIS = ("Low", "Medium", "High", "Elite")
BASE = Path("replicacao")


def ler_csv(caminho, colunas=()):
    """Valida chave, esquema e duplicatas antes da junção (sem perda silenciosa)."""
    dados = pd.read_csv(caminho, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    chave = next((c for c in ("repo", "repository", "full_name") if c in dados), None)
    if chave is None or set(colunas) - set(dados):
        raise ValueError(f"{caminho}: chave ou colunas obrigatórias ausentes")
    dados = dados.rename(columns={chave: "repo"})
    dados["repo"] = dados["repo"].str.strip().str.lower()
    if dados.empty or not dados.repo.str.fullmatch(r"[^/\s]+/[^/\s]+").all():
        raise ValueError(f"{caminho}: lista vazia ou identificador de repositório inválido")
    if dados.repo.duplicated().any():
        raise ValueError(f"{caminho}: repositório duplicado")
    for coluna in METRICAS.keys() & set(colunas):
        valores = pd.to_numeric(dados[coluna].mask(dados[coluna].eq("")), errors="raise")
        if np.isinf(valores).any():
            raise ValueError(f"{caminho}: {coluna} contém infinito")
        dados[coluna] = valores
    for coluna in CATEGORIAS.keys() & set(colunas):
        valores = dados[coluna].str.strip().replace("", None)
        if not valores.dropna().isin(NIVEIS).all():
            raise ValueError(f"{caminho}: categoria desconhecida em {coluna}")
        dados[coluna] = valores
    return dados.set_index("repo")


def diferenca(original, obtido):
    """(diferença absoluta, relativa, estado); nenhum caso indefinido vira zero."""
    if pd.isna(original) or pd.isna(obtido):
        return np.nan, np.nan, "ausente"
    absoluta = obtido - original
    if original == 0:
        return absoluta, np.nan, "ambos_zero" if obtido == 0 else "original_zero"
    return absoluta, absoluta / original, "comparavel"


def kappa_ponderado(original, obtido):
    """Cohen com distância linear |i-j|/3, na ordem Low < Medium < High < Elite.

    Exclui pares incompletos. Retorna NaN se não houver variabilidade esperada
    (ambos sempre na mesma categoria) ou se houver menos de dois pares.
    """
    pares = [(a, b) for a, b in zip(original, obtido) if pd.notna(a) and pd.notna(b)]
    if len(pares) < 2:
        return np.nan
    matriz = np.zeros((4, 4))
    for a, b in pares:
        matriz[NIVEIS.index(a), NIVEIS.index(b)] += 1
    matriz /= len(pares)
    pesos = np.abs(np.arange(4)[:, None] - np.arange(4)[None, :]) / 3
    esperado = np.outer(matriz.sum(axis=1), matriz.sum(axis=0))
    desacordo_esperado = (pesos * esperado).sum()
    return 1 - (pesos * matriz).sum() / desacordo_esperado if desacordo_esperado else np.nan


def comparar(original, obtido, amostra):
    """Preserva a ordem e todos os repositórios da subamostra, mesmo sem par."""
    colunas = [*METRICAS, *CATEGORIAS]
    a, b = ler_csv(original, colunas), ler_csv(obtido, colunas)
    repos = ler_csv(amostra).index
    a, b = a.reindex(repos), b.reindex(repos)
    linhas, classes, resumo, acordo = [], [], [], []
    for coluna, rotulo in METRICAS.items():
        for repo in repos:
            x, y = a.loc[repo, coluna], b.loc[repo, coluna]
            absoluta, relativa, estado = diferenca(x, y)
            linhas.append(dict(repo=repo, metrica=coluna, original=x, obtido=y,
                               diferenca_absoluta=absoluta, diferenca_relativa=relativa,
                               estado=estado))
        quadro = pd.DataFrame(linhas[-len(repos):])
        finitas = quadro.diferenca_relativa.dropna()
        q1, mediana, q3 = finitas.quantile([.25, .5, .75])
        resumo.append(dict(metrica=coluna, rotulo=rotulo, n_total=len(repos),
                           n_relativas=len(finitas), mediana=mediana, q1=q1, q3=q3,
                           iqr=q3-q1, max_abs_relativa=finitas.abs().max(),
                           n_iguais=int((quadro.diferenca_absoluta == 0).sum()),
                           n_ambos_zero=int((quadro.estado == "ambos_zero").sum()),
                           n_original_zero=int((quadro.estado == "original_zero").sum()),
                           n_ausentes=int((quadro.estado == "ausente").sum())))
    for coluna, rotulo in CATEGORIAS.items():
        validos = a[coluna].notna() & b[coluna].notna()
        iguais = validos & a[coluna].eq(b[coluna])
        for repo in repos:
            classes.append(dict(repo=repo, metrica=coluna, original=a.loc[repo, coluna],
                                obtido=b.loc[repo, coluna], par_valido=bool(validos[repo]),
                                mesma_classificacao=bool(iguais[repo])))
        acordo.append(dict(metrica=coluna, rotulo=rotulo, n_total=len(repos),
                           n_pares=int(validos.sum()), n_iguais=int(iguais.sum()),
                           percentual_amostra=100*iguais.sum()/len(repos),
                           percentual_pares=100*iguais.sum()/validos.sum() if validos.any() else np.nan,
                           kappa_linear=kappa_ponderado(a[coluna], b[coluna])))
    return tuple(pd.DataFrame(q) for q in (linhas, resumo, classes, acordo))


def proveniencia(caminho):
    caminho = Path(caminho)
    resultado = {"arquivo": caminho.as_posix(),
                 "sha256": hashlib.sha256(caminho.read_bytes()).hexdigest()}
    manifesto = caminho.with_name("MANIFEST.json")
    if manifesto.exists():
        conteudo = json.loads(manifesto.read_text(encoding="utf-8"))
        resultado.update(data_declarada=conteudo.get("data_coleta"),
                         commit_declarado=conteudo.get("git", {}).get("commit"),
                         sha256_declarado=conteudo.get("dataset", {}).get("sha256"))
        resultado["manifesto_confere"] = resultado["sha256"] == resultado["sha256_declarado"]
    return resultado


def gerar_figura(diferencas, acordo, saida):
    plt = estilo.aplicar()
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(6.3, 3.1), layout="constrained")
    amostras = [100*diferencas.loc[diferencas.metrica == c, "diferenca_relativa"].dropna()
                for c in METRICAS]
    ax.boxplot(amostras, tick_labels=list(METRICAS.values()), orientation="horizontal",
               flierprops={"marker": ".", "markersize": 4})
    ax.set_xscale("symlog", linthresh=1)
    ax.axvline(0, color=estilo.REFERENCIA, linewidth=.7)
    ax.set_xlabel("Diferença relativa (%) · symlog")
    pos = np.arange(len(acordo))
    bx.barh(pos-.17, acordo.percentual_amostra, height=.32, label="Subamostra (30)")
    bx.barh(pos+.17, acordo.percentual_pares, height=.32, label="Pares classificados")
    bx.set(yticks=pos, yticklabels=acordo.rotulo, xlim=(0, 119), xlabel="Mesma classificação (%)")
    for i, row in acordo.iterrows():
        bx.text(row.percentual_amostra+1, i-.17, f"{row.n_iguais}/{row.n_total}", va="center", fontsize=6)
        bx.text(row.percentual_pares+1 if pd.notna(row.percentual_pares) else 1, i+.17,
                f"{row.n_iguais}/{row.n_pares}", va="center", fontsize=6)
    bx.legend(loc="lower left", bbox_to_anchor=(0, 1), fontsize=6)
    pasta = Path(saida)/"figuras"
    pasta.mkdir(parents=True, exist_ok=True)
    fig.savefig(pasta/"replicacao_comparacao.png", dpi=200)
    estilo.salvar(fig, saida, "replicacao_comparacao")


def executar(original, obtido, amostra, saida):
    diferencas, resumo, classes, acordo = comparar(original, obtido, amostra)
    for nome, quadro in (("diferencas", diferencas), ("resumo", resumo),
                         ("classificacoes", classes), ("concordancia", acordo)):
        pasta = Path(saida)/"tabelas"
        pasta.mkdir(parents=True, exist_ok=True)
        quadro.to_csv(pasta/f"replicacao_{nome}.csv", index=False)
    artigo = resumo[["rotulo", "n_relativas", "mediana", "iqr", "max_abs_relativa"]].copy()
    artigo.columns = ["Métrica", "n", "Mediana (%)", "IQR (p.p.)", "Máximo absoluto (%)"]
    artigo.iloc[:, 2:] *= 100
    comum.salvar_tabela(artigo, saida, "replicacao_artigo", casas=3)
    dora = acordo[["rotulo", "n_iguais", "n_pares", "percentual_amostra",
                   "percentual_pares", "kappa_linear"]].copy()
    dora["n_iguais"] = [f"{r.n_iguais}/{r.n_total}" for r in acordo.itertuples()]
    dora.columns = ["Classificação", "Iguais/total", "Pares", "Total (%)",
                    "Pares (%)", "Kappa linear"]
    comum.salvar_tabela(dora, saida, "replicacao_dora_artigo", casas=3)
    gerar_figura(diferencas, acordo, saida)
    metadados = {"original": proveniencia(original), "obtido": proveniencia(obtido),
                 "amostra": proveniencia(amostra), "resumo": resumo, "concordancia": acordo}
    comum.salvar_json(metadados, saida, "replicacao")
    texto = ["# Replicação cruzada — comparação", "",
             "Unidade: repositório. Junção pela chave sem distinção de caixa, restrita à "
             "subamostra, preservando ausências no denominador. Categorias são as publicadas "
             "pelo grupo autor; não são recalculadas com os limites do nosso pipeline.", "",
             "Diferença = (obtido − original)/original. Original zero (inclusive 0/0) e "
             "ausências têm razão indefinida, registrada como célula vazia no CSV. "
             "Mediana e IQR usam somente razões finitas e quantis com interpolação linear. "
             "Valores seguem a precisão publicada; zero não significa dado ausente.", "",
             "## Resultados numéricos", ""]
    for row in resumo.itertuples():
        texto.append(f"- {row.rotulo}: mediana {100*row.mediana:.4f}%; IQR {100*row.iqr:.4f} p.p.; "
                     f"n={row.n_relativas}/{row.n_total}; iguais={row.n_iguais}; "
                     f"ambos zero={row.n_ambos_zero}; original zero={row.n_original_zero}; "
                     f"ausentes={row.n_ausentes}.")
    texto += ["", "## Concordância DORA", "",
              "Kappa de Cohen com pesos lineares, Low < Medium < High < Elite. Pares incompletos "
              "são excluídos do kappa; duas categorias ausentes não contam como acordo. "
              "Kappa fica indefinido com menos de dois pares ou desacordo esperado zero.", ""]
    for row in acordo.itertuples():
        texto.append(f"- {row.rotulo}: {row.n_iguais}/{row.n_total} ({row.percentual_amostra:.2f}%) "
                     f"da subamostra; {row.n_iguais}/{row.n_pares} ({row.percentual_pares:.2f}%) "
                     f"dos pares; κ linear={row.kappa_linear:.4f}.")
    texto += ["", "## Maiores diferenças", ""]
    maiores = diferencas.dropna(subset=["diferenca_relativa"]).copy()
    maiores["ordem"] = maiores.diferenca_relativa.abs()
    for row in maiores.nlargest(10, "ordem").itertuples():
        texto.append(f"- `{row.repo}`, {METRICAS[row.metrica]}: {row.original:g} → "
                     f"{row.obtido:g} ({100*row.diferenca_relativa:.4f}%).")
    texto += ["", "## Proveniência", ""]
    for lado in ("original", "obtido", "amostra"):
        item = metadados[lado]
        texto.append(f"- {lado}: `{item['arquivo']}`, SHA-256 `{item['sha256']}`.")
        if item.get("manifesto_confere") is False:
            texto.append("  **Manifesto inconsistente:** o SHA-256 declarado não corresponde ao CSV. "
                         "Data e commit declarados não comprovam a origem desse arquivo.")
    texto += ["", "## Causas e limitações", "",
              "No Falco, o pipeline usa updated_at como fim da recuperação. Dois sucessos "
              "de setembro/2025 foram atualizados em outubro/2026, embora os jobs tenham "
              "terminado em 2025. No snapshot adicional, usar updated_at reproduz 502,68 h; "
              "trocar somente esses dois fins pelo maior completed_at dos jobs reproduz "
              "48,10 h. Isso evidencia sensibilidade a metadados mutáveis, sem provar "
              "o estado da coleta original ou que houve reexecução.", "",
              "Amplify, Blockscout, LangWatch e Yosys têm menos runs na replicação. "
              "As consultas adicionais também mostram redução no histórico disponível. "
              "Exclusão/retenção e data de coleta são hipóteses; faltam os dois snapshots "
              "históricos para identificar IDs removidos e descartar cache/paginação. "
              "Os intermediários de releases coincidem nos 30 repositórios.", "",
              "O manifesto original tem hashes incompatíveis com os CSVs publicados; "
              "sua data declarada não comprova a origem dos números. Os JSONs das "
              "consultas estão em replicacao/evidencias/.", "",
              "Issues de divergência: publicação pendente. O conector rejeitou a abertura "
              "da primeira Issue (user rejected MCP tool call); nenhuma foi criada.", "",
              "A figura usa symlog (trecho linear entre −1% e +1%); boxplots incluem "
              "outliers. Mediana nula não implica identidade em todos os repositórios."]
    comum.salvar_texto("\n".join(texto), saida, "notas_replicacao")
    return resumo, acordo


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, default=BASE/"resultados_originais/dataset.csv")
    parser.add_argument("--obtido", type=Path, default=BASE/"resultados_obtidos/dataset.csv")
    parser.add_argument("--amostra", type=Path, default=BASE/"subamostra.csv")
    parser.add_argument("--saida", type=Path, default=Path("resultados"))
    args = parser.parse_args(argv)
    try:
        resumo, acordo = executar(args.original, args.obtido, args.amostra, args.saida)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(resumo.to_string(index=False))
    print(acordo.to_string(index=False))


if __name__ == "__main__":
    main()
