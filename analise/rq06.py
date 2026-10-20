"""RQ 06: fatores associados às métricas DORA, com famílias de Holm separadas.

Uma observação por repositório; grupos definidos antes de excluir métricas ausentes.
Não coleta, imputa, classifica projetos automaticamente nem reconstrói consenso.
"""
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from . import comum, estilo, rq05


PRINCIPAIS = ("df", "lt_a", "cfr_a", "recuperacao")
SUPLEMENTARES = ("lt_b", "cfr_b")
FATORES = ("linguagem", "estrelas", "contribuidores", "idade")
NOMES = {"df": "DF", "lt_a": "LT (a)", "cfr_a": "CFR (a)",
         "recuperacao": "Recuperação", "lt_b": "LT (b)", "cfr_b": "CFR (b)",
         "linguagem": "Linguagem", "estrelas": "Estrelas", "contribuidores": "Contribuidores",
         "idade": "Idade", "tipo": "Tipo do projeto"}
TIPOS = ("library/framework", "application/service", "cli")
TIPOS_CURTOS = {"library/framework": "Biblioteca/\nframework",
                "application/service": "Aplicação/\nserviço", "cli": "CLI"}
GRUPOS_COLUNAS = ["fator", "grupo", "n", "limite_inferior", "limite_superior",
                  "inferior_inclusivo", "unidade"]
POSTHOC_COLUNAS = ["familia", "fator", "metrica", "grupo_a", "grupo_b", "n1", "n2",
                   "u", "p", "p_holm", "delta", "interpretacao", "direcao", "rejeita"]


def interpretar_epsilon(valor):
    """Convenção descritiva de Mangiafico: 0,01 / 0,08 / 0,26; não universal."""
    if pd.isna(valor):
        return "indefinido"
    for limite, nome in ((0.01, "desprezível"), (0.08, "pequeno"), (0.26, "médio")):
        if valor < limite:
            return nome
    return "grande"


def base_metricas(dados):
    """C1 estrita para (a); CFR (b) usa os mesmos vereditos e censura da RQ 05."""
    quadro, origem_b = rq05.por_repositorio(dados)
    repos = dados.repositorios
    for destino, coluna in (("lt_a", "release_lead_time_hours"),
                             ("lt_b", "commit_lead_time_hours"),
                             ("recuperacao", "recovery_hours")):
        quadro[destino] = comum.serie_numerica(repos[coluna])
    invalidos = {}
    for coluna in PRINCIPAIS + SUPLEMENTARES:
        valores = quadro[coluna].dropna()
        if not np.isfinite(valores).all():
            raise ValueError(f"RQ 06: {coluna} deve ser finita quando presente.")
        if (valores < 0).any():
            if coluna not in ("lt_a", "lt_b"):
                raise ValueError(f"RQ 06: {coluna} não pode ser negativa.")
            invalidos[coluna] = int((valores < 0).sum())
        if coluna.startswith("cfr") and (valores > 1).any():
            raise ValueError("RQ 06: CFR deve estar entre 0 e 1.")
    quadro.attrs["duracoes_negativas"] = invalidos
    return quadro, origem_b


def quartis(serie, fator, unidade):
    """qcut com cortes duplicados removidos; empates nunca são separados por ranking."""
    valores = comum.serie_numerica(serie)
    presentes = valores.dropna()
    grupos = pd.Series(pd.NA, index=serie.index, dtype="string")
    linhas = []
    if presentes.empty:
        return grupos, linhas
    if not np.isfinite(presentes).all() or (presentes < 0).any():
        raise ValueError(f"RQ 06: metadado {fator} deve ser finito e não negativo.")
    if presentes.nunique() == 1:
        cortes = np.array([presentes.iloc[0], presentes.iloc[0]])
        codigos = pd.Series(0, index=presentes.index)
    else:
        codigos, cortes = pd.qcut(presentes, 4, labels=False, retbins=True, duplicates="drop")
    for indice in range(len(cortes) - 1):
        nome = f"Q{indice + 1}"
        mascara = codigos.eq(indice)
        grupos.loc[codigos.index[mascara]] = nome
        linhas.append({"fator": fator, "grupo": nome, "n": int(mascara.sum()),
                       "limite_inferior": float(cortes[indice]),
                       "limite_superior": float(cortes[indice + 1]),
                       "inferior_inclusivo": indice == 0, "unidade": unidade})
    return grupos, linhas


def linguagens(serie, minimo=15):
    """Até seis linguagens frequentes; raras em Outras, ausente continua ausente."""
    valores = serie.astype("string").str.strip().replace("", pd.NA)
    contagens = valores.value_counts()
    ordem = sorted(contagens.index, key=lambda nome: (-contagens[nome], nome))
    mantidas = [nome for nome in ordem[:6] if contagens[nome] >= minimo]
    outras = int(contagens.sum() - contagens.reindex(mantidas).sum())
    while mantidas and 0 < outras < minimo:
        outras += int(contagens[mantidas.pop()])
    grupos = valores.where(valores.isin(mantidas), "Outras").where(valores.notna())
    nomes = mantidas + (["Outras"] if outras else [])
    linhas = [{"fator": "linguagem", "grupo": nome, "n": int(grupos.eq(nome).sum()),
               "limite_inferior": np.nan, "limite_superior": np.nan,
               "inferior_inclusivo": pd.NA, "unidade": "repositórios"} for nome in nomes]
    return grupos, linhas


def definir_grupos(repos):
    """Idade em dias no fim da janela de cada repositório, nunca na data da execução."""
    grupos, linhas = {}, []
    grupos["linguagem"], registros = linguagens(repos["language"])
    linhas.extend(registros)
    idade = (repos["window_end"] - repos["created_at"]).dt.total_seconds() / 86400
    for fator, valores, unidade in (("estrelas", repos["stars"], "estrelas"),
                                    ("contribuidores", repos["contributors"], "pessoas"),
                                    ("idade", idade, "dias")):
        grupos[fator], registros = quartis(valores, fator, unidade)
        linhas.extend(registros)
    return grupos, pd.DataFrame(linhas, columns=GRUPOS_COLUNAS)


def tipos_projeto(repos, caminho=None):
    """Prefere consenso; rótulo coletivo é identificado como provisório, sem pseudo-réplicas."""
    raiz = Path(__file__).resolve().parents[1]
    candidatos = [Path(caminho)] if caminho is not None else [
        raiz / "validacao/resultados/tipo_projeto.csv",
        raiz / "validacao/rotulos/rotulos_grupo.csv"]
    fonte = next((arquivo for arquivo in candidatos if arquivo.is_file()), None)
    grupos = pd.Series(pd.NA, index=repos.index, dtype="string")
    if fonte is None:
        return grupos, "Rótulos de tipo ausentes; análise exploratória não estimável."
    rotulos = pd.read_csv(fonte, dtype="string")
    if not {"repository", "project_type"}.issubset(rotulos.columns):
        raise ValueError(f"RQ 06: {fonte} precisa de repository e project_type.")
    rotulos = rotulos[["repository", "project_type"]].copy()
    for coluna in rotulos:
        rotulos[coluna] = rotulos[coluna].str.strip().str.lower().replace("", pd.NA)
    rotulos = rotulos.dropna()
    if not rotulos["project_type"].isin((*TIPOS, "other")).all():
        raise ValueError("RQ 06: tipo do projeto fora das categorias do protocolo.")
    if (rotulos.groupby("repository")["project_type"].nunique() > 1).any():
        raise ValueError("RQ 06: rótulos de tipo conflitantes; resolva o consenso antes de analisar.")
    mapa = rotulos.drop_duplicates("repository").set_index("repository")["project_type"]
    grupos = repos["repository"].str.lower().map(mapa).astype("string")
    excluidos = int(grupos.eq("other").sum())
    grupos = grupos.where(grupos.isin(TIPOS))
    estado = "coletivos, provisórios (não são consenso independente)" if fonte.name == "rotulos_grupo.csv" else "consensuais"
    fonte_exibida = fonte.relative_to(raiz).as_posix() if fonte.is_relative_to(raiz) else fonte.name
    origem = (f"Rótulos {estado}: {fonte_exibida}; {grupos.notna().sum()} repositórios "
              f"com métricas e tipo elegível; {excluidos} do tipo other excluídos.")
    return grupos, origem


def amostras(quadro, grupos, metrica):
    """Mesma partição para todas as métricas; n efetivo após retirar ausentes."""
    nomes = list(dict.fromkeys(grupos.dropna()))
    if nomes and all(str(nome).startswith("Q") and str(nome)[1:].isdigit() for nome in nomes):
        nomes.sort(key=lambda nome: int(nome[1:]))
    else:
        nomes.sort()
    return {nome: quadro.loc[grupos.eq(nome).fillna(False), metrica].dropna() for nome in nomes}


def teste_global(quadro, grupos, metrica, fator, exploratorio=False):
    conjuntos = amostras(quadro, grupos, metrica)
    # A regra dos dois maiores evita inferência assintótica com um tipo muito raro.
    tipo_raro = exploratorio and len(conjuntos) >= 3 and min(map(len, conjuntos.values())) < 5
    conjuntos = {nome: valores for nome, valores in conjuntos.items() if len(valores)}
    restricao = ""
    if tipo_raro:
        maiores = sorted(conjuntos, key=lambda nome: (-len(conjuntos[nome]), nome))[:2]
        conjuntos = {nome: conjuntos[nome] for nome in maiores}
        restricao = "apenas os dois maiores tipos; algum grupo tinha n < 5"
    linha = {"fator": fator, "metrica": metrica, "n": sum(map(len, conjuntos.values())),
             "grupos": "; ".join(f"{nome}: {len(valores)}" for nome, valores in conjuntos.items()),
             "teste": "indefinido", "h": np.nan, "u": np.nan, "p": np.nan,
             "epsilon_quadrado": np.nan, "delta": np.nan, "interpretacao": "indefinido",
             "restricao": restricao, "status": "menos de dois grupos com dados"}
    if len(conjuntos) >= 3 and min(map(len, conjuntos.values())) < 5:
        linha["status"] = "Kruskal-Wallis não estimado: grupo com n < 5"
    elif len(conjuntos) >= 3:
        resultado = comum.kruskal_wallis(*conjuntos.values())
        linha.update(resultado, teste="KW", status="ok",
                     interpretacao=interpretar_epsilon(resultado["epsilon_quadrado"]))
    elif len(conjuntos) == 2:
        resultado = comum.mann_whitney(*conjuntos.values())
        linha.update({chave: resultado[chave] for chave in ("u", "p", "delta", "interpretacao")},
                     teste="MW", status="ok")
    return linha, conjuntos


def familia(quadro, grupos, metricas, nome, exploratorio=False):
    """Holm uma vez sobre TODOS os p válidos da família, sem pré-seleção."""
    linhas, selecoes = [], {}
    for fator, particao in grupos.items():
        for metrica in metricas:
            linha, conjuntos = teste_global(quadro, particao, metrica, fator, exploratorio)
            linhas.append({"familia": nome, **linha})
            selecoes[fator, metrica] = conjuntos
    tabela = pd.DataFrame(linhas)
    ajuste = comum.holm(tabela["p"])
    tabela[["p_holm", "rejeita"]] = ajuste[["p_holm", "rejeita"]]
    return tabela, selecoes


def direcao(delta, metrica):
    if pd.isna(delta):
        return "indefinida"
    if delta == 0:
        return "sem dominância"
    maior = delta > 0
    melhor_a = maior if metrica == "df" else not maior
    return f"A tende a ter valores {'maiores' if maior else 'menores'}; sentido favorável a {'A' if melhor_a else 'B'}"


def posthoc(tabela, selecoes):
    """MW após KW significativo; Holm reúne pares das métricas dentro de cada fator."""
    linhas = []
    for _, teste in tabela[tabela["rejeita"].fillna(False) & tabela["teste"].eq("KW")].iterrows():
        conjuntos = selecoes[teste["fator"], teste["metrica"]]
        for a, b in combinations(conjuntos, 2):
            resultado = comum.mann_whitney(conjuntos[a], conjuntos[b])
            linhas.append({"familia": teste["familia"], "fator": teste["fator"],
                           "metrica": teste["metrica"], "grupo_a": a, "grupo_b": b,
                           **resultado, "direcao": direcao(resultado["delta"], teste["metrica"])})
    pares = pd.DataFrame(linhas, columns=POSTHOC_COLUNAS)
    pares["rejeita"] = pd.Series(pd.NA, index=pares.index, dtype="boolean")
    for _, bloco in pares.groupby(["familia", "fator"], sort=False):
        ajuste = comum.holm(bloco["p"])
        pares.loc[bloco.index, "p_holm"] = ajuste["p_holm"]
        pares.loc[bloco.index, "rejeita"] = ajuste["rejeita"]
    return pares


def boxplot(conjuntos, teste, saida):
    plt = estilo.aplicar()
    fig, eixo = plt.subplots(figsize=estilo.TAMANHO_DUPLO)
    rotulos = [f"{TIPOS_CURTOS.get(nome, nome)}\n(n={len(valores)})"
               for nome, valores in conjuntos.items()]
    cores = [estilo.VARIANTE_A, estilo.VARIANTE_B, estilo.NEUTRO, estilo.REFERENCIA] * 2
    estilo.caixa(eixo, list(conjuntos.values()), rotulos, cores)
    metrica = teste["metrica"]
    if metrica.startswith("cfr"):
        eixo.set_ylim(0, 1)
        unidade = "proporção"
    else:
        limiar = 0.1 if metrica == "df" else 1
        eixo.set_yscale("symlog", base=10, linthresh=limiar)
        unidade = "releases/semana" if metrica == "df" else "horas"
        unidade += f"; symlog, limiar {limiar:g}"
    eixo.set_ylabel(f"{NOMES[metrica]} ({unidade})")
    efeito = (f"ε²={teste['epsilon_quadrado']:.3f}" if teste["teste"] == "KW"
              else f"δ={teste['delta']:.3f}")
    eixo.set_title(f"{NOMES[teste['fator']]} × {NOMES[metrica]} — {teste['familia']}\n"
                   f"{teste['teste']}; p Holm={teste['p_holm']:.3g}; {efeito}; n={teste['n']}")
    fig.tight_layout()
    return estilo.salvar(fig, saida, f"rq06_{teste['familia']}_{teste['fator']}_{metrica}")


def salvar_testes(tabela, saida, nome):
    """CSV completo; LaTeX compacto com p em notação científica quando necessário."""
    _, tex = comum.salvar_tabela(tabela, saida, nome, casas=4)
    # MW não tem H nem epsilon: reporta U e delta nas colunas gerais de estatística/efeito.
    artigo = pd.DataFrame({"Fator": tabela["fator"].map(NOMES),
                          "Métrica": tabela["metrica"].map(NOMES), "n": tabela["n"],
                          "Teste": tabela["teste"],
                          "H/U": tabela["h"].where(tabela["teste"].eq("KW"), tabela["u"]),
                          "p": tabela["p"].map(rq05.p_texto),
                          "p Holm": tabela["p_holm"].map(rq05.p_texto),
                          "ε²/δ": tabela["epsilon_quadrado"].where(tabela["teste"].eq("KW"), tabela["delta"]),
                          "Efeito": tabela["interpretacao"]})
    # Cabeçalhos matemáticos evitam caracteres gregos não definidos no pdfLaTeX.
    texto = comum.tabela_latex(artigo, casas=3).replace("ε²/δ", r"$\varepsilon^2/\delta$")
    tex.write_text("{\\footnotesize\n" + texto + "}\n", encoding="utf-8")


def discussao(quadro, tabelas, pares, cortes, origem_tipo, origem_b):
    invalidos = quadro.attrs.get("duracoes_negativas", {})
    negativos = "; ".join(f"{NOMES[chave]}: {n}" for chave, n in invalidos.items()) or "nenhuma"
    paragrafos = ["# RQ 06 — Fatores associados ao desempenho DORA", "",
        f"A entrada contém {len(quadro)} repositórios, não uma amostra presumida de 300. "
        "Cada repositório tem o mesmo peso. A análise é univariada, bilateral, com α = 0,05. "
        "As métricas principais são DF, LT (a), CFR (a) e recuperação da C1 estrita; "
        "não há fallback de LT (a) para (b), nem imputação de episódios censurados. "
        f"O CFR (b) suplementar usa {origem_b} e a mesma agregação/censura da RQ 05.", "",
        f"Durações negativas encontradas: {negativos}. Os Lead Times negativos são "
        "preservados, conforme a política do pipeline documentada no README (rebase ou "
        "cherry-pick podem gerar essas diferenças de datas). Não se toma módulo nem "
        "se troca por zero. São uma limitação temporal da proxy; não representam "
        "tempo de entrega fisicamente negativo nem justificam alegar desempenho superior.", "",
        "## Grupos e cortes", "",
        "Os grupos são fixados com os metadados antes de excluir a métrica ausente em cada teste. "
        "Idade é (window_end − created_at) em dias de 24 horas; datas ausentes não são estimadas. "
        "Estrelas, contribuidores e idade usam [pandas.qcut][qcut], com quatro quantis e "
        "duplicates='drop': cortes coincidentes são removidos; empates não são separados "
        "por posição arbitrária. Os grupos restantes são Q1…Qk, em ordem crescente, e podem "
        "ter tamanhos diferentes ou intervalos vazios. Um fator constante não permite teste. "
        "Os intervalos são abertos à esquerda e fechados à direita, exceto o primeiro, "
        "que inclui o mínimo. Todos os limites exatos e n estão em rq06_grupos.csv."]
    for fator in FATORES:
        parte = cortes[cortes["fator"].eq(fator)]
        detalhes = []
        for _, linha in parte.iterrows():
            intervalo = ""
            if pd.notna(linha["limite_inferior"]):
                abre = "[" if linha["inferior_inclusivo"] else "("
                intervalo = (f" {abre}{linha['limite_inferior']:.8g}; "
                             f"{linha['limite_superior']:.8g}] {linha['unidade']}")
            detalhes.append(f"{linha['grupo']}{intervalo}: n={linha['n']}")
        paragrafos += ["", f"- {NOMES[fator]}: " + ("; ".join(detalhes) or "sem metadados válidos") + "."]
    paragrafos += ["", "Entre as seis linguagens mais frequentes, mantêm-se separadas apenas as que "
        "têm pelo menos 15 repositórios. As demais conhecidas formam Outras; se Outras tiver "
        "menos de 15, absorve a menor linguagem mantida até atingir esse mínimo. Linguagem "
        "ausente fica fora desse fator. A quantidade de linguagens separadas depende dos dados: "
        "não se fabricam grupos de 15 para alcançar cinco ou seis linguagens.", "",
        "## Testes e tamanhos de efeito", "",
        "A família principal contém os 16 testes planejados (4 fatores × 4 métricas). "
        "A suplementar contém 8 (os mesmos fatores × LT (b) e CFR (b)). Tipo do projeto "
        "tem 4 testes exploratórios separados. Holm é aplicado a todos os p válidos de cada "
        "família, inclusive os não significativos; testes indefinidos permanecem ausentes. "
        "São usados Kruskal–Wallis com correção de empates para três ou mais grupos, "
        "e Mann–Whitney para dois. KW não é estimado se algum grupo efetivo tem menos de 5 "
        "observações ([recomendação do SciPy][kw]). As tabelas CSV registram n, tamanhos "
        "dos grupos efetivos, restrições e motivo de teste indefinido.", "",
        "Para KW, ε² = H/(n−1); a convenção descritiva de [Mangiafico][efeitos] é: "
        "desprezível <0,01; pequeno [0,01;0,08); médio [0,08;0,26); grande ≥0,26. "
        "Esses limites não são universais nem provam importância prática. Para MW, usa-se "
        "δ = 2U/(n₁n₂)−1 e a convenção da base comum (Romano et al., 2006): "
        "|δ| <0,147 desprezível; <0,33 pequeno; <0,474 médio; demais grande. "
        "As tabelas LaTeX mostram H/ε² nas linhas KW e U/δ nas linhas MW; CSV preserva "
        "colunas distintas. O sinal de δ compara o primeiro grupo listado com o segundo."]
    for nome, tabela in tabelas.items():
        significativos = tabela[tabela["rejeita"].fillna(False)]
        relevantes = significativos[significativos["interpretacao"].isin(["médio", "grande"])]
        paragrafos += ["", f"### Família {'exploratória' if nome == 'exploratoria' else nome}", "",
            f"{len(tabela)} testes planejados; {tabela['p'].notna().sum()} estimáveis; "
            f"{len(significativos)} significativo(s) após Holm; {len(relevantes)} "
            "com efeito ao menos médio na convenção adotada."]
        for _, linha in significativos.iterrows():
            kw = linha["teste"] == "KW"
            efeito = linha["epsilon_quadrado"] if kw else linha["delta"]
            paragrafos += ["", f"- {NOMES[linha['fator']]} × {NOMES[linha['metrica']]}: "
                f"n={linha['n']}, p Holm={rq05.p_texto(linha['p_holm'])}, "
                f"{'ε²' if kw else 'δ'}={comum.numero(efeito, 4)} ({linha['interpretacao']})."]
        if not len(significativos):
            paragrafos += ["", "Não houve associação significativa após Holm nesta família; "
                            "isso não comprova ausência de associação."]
        sem_associacao = [NOMES[metrica] for metrica in dict.fromkeys(tabela["metrica"])
                         if not significativos["metrica"].eq(metrica).any()]
        if sem_associacao:
            paragrafos += ["", "Nenhum fator teve associação significativa após Holm com "
                            + ", ".join(sem_associacao) + " nesta família."]
        inconclusivos = tabela[~tabela["rejeita"].fillna(False)
                              & tabela["interpretacao"].isin(["médio", "grande"])]
        if not inconclusivos.empty:
            exemplos = "; ".join(f"{NOMES[linha['fator']]} × {NOMES[linha['metrica']]} "
                                  f"(p Holm={rq05.p_texto(linha['p_holm'])})"
                                  for _, linha in inconclusivos.iterrows())
            paragrafos += ["", "Efeitos ao menos médios sem significância após Holm: "
                            + exemplos + ". Permanecem inconclusivos apesar da magnitude estimada."]
    paragrafos += ["", "## Post-hoc e direção", "",
        "Somente KW significativo após Holm abre comparações MW bilaterais par a par. "
        "Holm reúne todos os pares das métricas selecionadas dentro de cada fator e "
        "família (não só por métrica). A tabela rq06_posthoc registra todos esses pares, "
        "Cliff's delta e direção; MW global com dois grupos já é a comparação direta. "
        "DF maior indica sentido favorável; LT, CFR e recuperação menores indicam sentido "
        "favorável. Dominância de postos não exige diferença entre medianas."]
    for _, linha in pares[pares["rejeita"].fillna(False).astype(bool)].iterrows():
        paragrafos += ["", f"- {linha['familia']}, {NOMES[linha['fator']]} × {NOMES[linha['metrica']]}: "
            f"A={linha['grupo_a']}, B={linha['grupo_b']}; p Holm={rq05.p_texto(linha['p_holm'])}; "
            f"δ={comum.numero(linha['delta'], 4)} ({linha['interpretacao']}); {linha['direcao']}."]
    if not pares["rejeita"].fillna(False).any():
        paragrafos += ["", "Nenhum par foi significativo após a correção do post-hoc."]
    paragrafos += ["", "## Tipo de projeto e limites da interpretação", "", origem_tipo, "",
        "Os tipos elegíveis são biblioteca/framework, aplicação/serviço e CLI. Não se "
        "estendem rótulos aos projetos não rotulados. Se algum tipo efetivo tiver n<5, "
        "comparam-se apenas os dois maiores por MW; a restrição e os grupos ficam na "
        "tabela. Não se mistura esta amostra com a família principal.", "",
        "Significância após Holm indica evidência de distribuições diferentes, não que "
        "uma característica cause desempenho melhor. Efeito pequeno pode ser significativo; "
        "efeito médio/grande sem significância continua inconclusivo. As associações são "
        "univariadas e podem refletir confundimento entre popularidade, idade, linguagem "
        "e contribuidores. Cobertura e ausências podem selecionar os projetos observados. "
        "O CFR (a) mede falha de pipeline, não incidente de produção; métricas baseadas "
        "em releases e recuperação de CI são proxies do DORA. No suplemento, CFR (b) "
        "também carrega o artefato da janela de sete dias discutido na RQ 05.", "",
        "Somente combinações significativas após Holm geram boxplots. Durações usam "
        "symlog base 10 com trecho linear até 1 hora; DF até 0,1 release/semana. Zeros "
        "permanecem sem pseudocontagem. CFR tem eixo linear de 0 a 1. As figuras "
        "mostram mediana, quartis, bigodes de 1,5 IQR e observações além dos bigodes.", "",
        "[qcut]: https://pandas.pydata.org/pandas-docs/version/2.2/reference/api/pandas.qcut.html",
        "[kw]: https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.stats.kruskal.html",
        "[efeitos]: https://rcompanion.org/handbook/F_08.html"]
    return "\n".join(paragrafos)


def executar(dados, saida):
    quadro, origem_b = base_metricas(dados)
    grupos, cortes = definir_grupos(dados.repositorios)
    tipos, origem_tipo = tipos_projeto(dados.repositorios)
    tipos_linhas = [{"fator": "tipo", "grupo": tipo, "n": int(tipos.eq(tipo).sum()),
                     "limite_inferior": np.nan, "limite_superior": np.nan,
                     "inferior_inclusivo": pd.NA, "unidade": "repositórios"} for tipo in TIPOS]
    cortes = pd.concat([cortes, pd.DataFrame(tipos_linhas)], ignore_index=True)
    tabelas, todos_pares = {}, []
    for nome, particoes, metricas in (("principal", grupos, PRINCIPAIS),
                                      ("suplementar", grupos, SUPLEMENTARES),
                                      ("exploratoria", {"tipo": tipos}, PRINCIPAIS)):
        tabela, selecao = familia(quadro, particoes, metricas, nome, nome == "exploratoria")
        tabelas[nome] = tabela
        todos_pares.append(posthoc(tabela, selecao))
        salvar_testes(tabela, saida, f"rq06_testes_{nome}")
        # Remove somente figuras desta combinação que perderam significância na reexecução.
        for _, teste in tabela[~tabela["rejeita"].fillna(False)].iterrows():
            anterior = Path(saida) / "figuras" / f"rq06_{nome}_{teste['fator']}_{teste['metrica']}.pdf"
            anterior.unlink(missing_ok=True)
        for _, teste in tabela[tabela["rejeita"].fillna(False)].iterrows():
            boxplot(selecao[teste["fator"], teste["metrica"]], teste, saida)
    preenchidos = [parte for parte in todos_pares if not parte.empty]
    pares = pd.concat(preenchidos, ignore_index=True) if preenchidos else todos_pares[0]
    _, tex = comum.salvar_tabela(pares, saida, "rq06_posthoc", casas=4)
    # A tabela detalhada é larga: \\input dentro de table* ou resizebox no artigo.
    artigo = pares[["familia", "fator", "metrica", "grupo_a", "grupo_b", "n1", "n2",
                     "p_holm", "delta", "interpretacao"]].copy()
    artigo["p_holm"] = artigo["p_holm"].map(rq05.p_texto)
    tex.write_text(comum.tabela_latex(artigo, casas=3), encoding="utf-8")
    comum.salvar_tabela(cortes, saida, "rq06_grupos", casas=6)
    comum.salvar_texto(discussao(quadro, tabelas, pares, cortes, origem_tipo, origem_b),
                       saida, "notas_rq06")
    return {"testes": tabelas, "posthoc": pares, "grupos": cortes}
