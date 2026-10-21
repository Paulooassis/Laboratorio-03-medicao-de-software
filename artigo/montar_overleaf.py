"""Monta o arquivo único do Overleaf a partir das seções versionadas.

O artigo é mantido em `main.tex` mais `secoes/`, para que cada seção entre por um PR
próprio. O Overleaf é mais prático com um arquivo só, então este script concatena as
mesmas fontes em `artigo-overleaf.tex`, com a bibliografia embutida em
`thebibliography` — assim o documento compila em uma passada, sem bibtex e sem `.bib`.

Rodar da raiz do projeto: `python artigo/montar_overleaf.py`
"""
from pathlib import Path


RAIZ = Path(__file__).resolve().parent
SECOES = ("01-introducao", "02-metodologia", "03-resultados", "04-discussao",
          "05-ameacas", "06-replicacao", "07-conclusao")
# As figuras são enviadas à parte no Overleaf; sem elas o documento ainda compila.
FALLBACK_FIGURA = r"""
% As figuras vêm de resultados/figuras/ e precisam ser enviadas ao projeto do Overleaf.
% Enquanto não estiverem lá, o documento compila com um aviso no lugar de cada uma, em
% vez de falhar. `\detokenize` protege o sublinhado do nome do arquivo.
\newcommand{\figuradora}[1]{%
  \IfFileExists{#1}{\includegraphics[width=0.85\textwidth]{#1}}{%
  \IfFileExists{figuras/#1}{\includegraphics[width=\textwidth]{figuras/#1}}{%
    \fbox{\parbox{0.93\textwidth}{\centering\vspace{1.1cm}
      \texttt{\detokenize{#1}}\\[0.3cm]
      \small Envie este arquivo de \texttt{resultados/figuras/} para o projeto do
      Overleaf.\vspace{1.1cm}}}}}%
}
"""


def corpo(nome):
    texto = (RAIZ / "secoes" / f"{nome}.tex").read_text(encoding="utf-8").rstrip()
    # Troca o include direto pelo comando tolerante a figura ausente.
    return texto.replace("\\includegraphics[width=0.85\\textwidth]{", "\\figuradora{")


def bibliografia():
    """Referências no formato da SBC, embutidas para dispensar o bibtex."""
    return r"""
\begin{thebibliography}{}

\bibitem[DORA 2024]{dora2024}
DORA (2024).
\newblock {\em DORA's software delivery metrics: the four keys}.
\newblock DevOps Research and Assessment. Disponível em:
  \url{https://dora.dev/guides/dora-metrics-four-keys/}. Acesso em: out. 2026.

\bibitem[Forsgren et al. 2018]{forsgren2018}
Forsgren, N., Humble, J., and Kim, G. (2018).
\newblock {\em Accelerate: The Science of Lean Software and DevOps: Building and
  Scaling High Performing Technology Organizations}.
\newblock IT Revolution Press, Portland, OR.

\bibitem[Landis and Koch 1977]{landis1977}
Landis, J.~R. and Koch, G.~G. (1977).
\newblock The measurement of observer agreement for categorical data.
\newblock {\em Biometrics}, 33(1):159--174.

\bibitem[Romano et al. 2006]{romano2006}
Romano, J., Kromrey, J.~D., Coraggio, J., and Skowronek, J. (2006).
\newblock Appropriate statistics for ordinal level data: Should we really be using
  t-test and Cohen's d for evaluating group differences on the NSSE and other surveys?
\newblock In {\em Annual Meeting of the Florida Association for Institutional
  Research}, pages 1--33.

\bibitem[Wohlin et al. 2012]{wohlin2012}
Wohlin, C., Runeson, P., H{\"o}st, M., Ohlsson, M.~C., Regnell, B., and Wessl{\'e}n,
  A. (2012).
\newblock {\em Experimentation in Software Engineering}.
\newblock Springer, Berlin.

\end{thebibliography}
"""


def montar():
    principal = (RAIZ / "main.tex").read_text(encoding="utf-8")
    cabeca, _, resto = principal.partition("\\input{secoes/01-introducao}")
    # Tudo depois dos \input é só a bibliografia e o \end{document}.
    cabeca = cabeca.replace("\\graphicspath{{../resultados/figuras/}}",
                            "\\graphicspath{{figuras/}{../resultados/figuras/}}")
    cabeca = cabeca.replace("\\begin{document}", FALLBACK_FIGURA + "\n\\begin{document}")
    partes = [cabeca.rstrip(), ""]
    partes += [corpo(nome) + "\n" for nome in SECOES]
    partes += [bibliografia(), "\\end{document}", ""]
    destino = RAIZ / "artigo-overleaf.tex"
    destino.write_text("\n".join(partes), encoding="utf-8")
    return destino


if __name__ == "__main__":
    caminho = montar()
    print(f"{caminho.relative_to(Path.cwd())}: "
          f"{len(caminho.read_text(encoding='utf-8').splitlines())} linhas")
