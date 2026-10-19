"""Padrão visual único das figuras do artigo: tamanho, fonte, paleta e escala log.

Todas as figuras saem em PDF vetorial, no tamanho de uma coluna do template da SBC
(16 cm de texto), com fonte de 8 pt — legível sem redimensionar no LaTeX. As duas
variantes obrigatórias das RQ 02 e 03 usam sempre as mesmas cores (`VARIANTE_A` e
`VARIANTE_B`), para que as figuras possam ser lidas lado a lado.
"""
import matplotlib
from matplotlib.ticker import MaxNLocator

matplotlib.use("Agg")  # Sem display no CI; as figuras nunca vão para a tela.
import matplotlib.pyplot as plt  # noqa: E402  (o backend precisa vir antes do pyplot)


# Largura do texto em uma coluna do template da SBC, em polegadas (16 cm).
LARGURA = 6.3
TAMANHO_SIMPLES = (LARGURA / 2, 2.6)
TAMANHO_DUPLO = (LARGURA, 2.7)
VARIANTE_A, VARIANTE_B = "#1f4e79", "#c1663f"
NEUTRO, REFERENCIA = "#4d4d4d", "#9a9a9a"
# Níveis DORA do melhor para o pior, mais o "sem classificação" em cinza: a escala é
# ordinal, então a cor também caminha em uma direção só.
NIVEIS = {"Elite": "#1f4e79", "High": "#4a7fb5", "Medium": "#e0b062", "Low": "#c1663f",
          "Sem classificação": "#bdbdbd"}


def aplicar():
    """Aplica o padrão visual; chamado por cada análise antes de criar figuras."""
    plt.rcParams.update({
        "figure.dpi": 150, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
        "font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8,
        "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.4,
        "boxplot.flierprops.markersize": 2.5, "lines.linewidth": 1.0,
        "pdf.fonttype": 42, "ps.fonttype": 42})  # Fontes embutidas, exigência comum de submissão
    return plt


def caixa(eixo, amostras, rotulos, cores):
    """Boxplots lado a lado com a mediana em destaque e a mesma paleta das variantes."""
    desenho = eixo.boxplot(amostras, tick_labels=rotulos, patch_artist=True, widths=0.55,
                           medianprops={"color": "black", "linewidth": 1.1})
    for caixa_, cor in zip(desenho["boxes"], cores):
        caixa_.set(facecolor=cor, alpha=0.45, edgecolor=cor, linewidth=0.9)
    return eixo


def contagem_inteira(eixo, das_contagens="y"):
    """Eixo de contagem de repositórios só com inteiros: não existe "1,5 repositório"."""
    escolhido = eixo.yaxis if das_contagens == "y" else eixo.xaxis
    escolhido.set_major_locator(MaxNLocator(integer=True))
    return eixo


def diagonal(eixo, valores_x, valores_y):
    """Reta y = x nas dispersões a × b: acima dela, a variante (a) é maior.

    Devolve se a reta foi desenhada — sem nenhum par de valores não há o que comparar,
    e o eixo fica sem a reta e sem legenda, em vez de uma legenda vazia.
    """
    pontos = [valor for valor in list(valores_x) + list(valores_y) if valor == valor and valor > 0]
    if not pontos:
        return False
    limites = (min(pontos) * 0.8, max(pontos) * 1.25)
    eixo.plot(limites, limites, color=REFERENCIA, linestyle="--", linewidth=0.8, zorder=0,
              label="a = b")
    eixo.set(xlim=limites, ylim=limites, xscale="log", yscale="log")
    return True


def salvar(figura, diretorio, nome):
    """Grava a figura em `resultados/figuras/<nome>.pdf` e devolve o caminho."""
    diretorio = diretorio / "figuras"
    diretorio.mkdir(parents=True, exist_ok=True)
    caminho = diretorio / f"{nome}.pdf"
    figura.savefig(caminho)
    plt.close(figura)
    return caminho
