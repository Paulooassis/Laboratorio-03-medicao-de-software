# Artigo

Fonte LaTeX do artigo, no template da SBC. As seções estão separadas em
[`secoes/`](secoes/) e são reunidas por [`main.tex`](main.tex), de modo que cada uma
possa entrar por um PR próprio.

## Compilar

O template oficial da SBC **não é redistribuído aqui**. Baixe-o em
<https://www.sbc.org.br/documentos-da-sbc/summary/169-templates-para-artigos-e-capitulos-de-livros/878-modelosparapublicaodeartigos>
e coloque `sbc-template.sty` e `sbc.bst` nesta pasta. Depois:

```bash
cd artigo
pdflatex main
bibtex main
pdflatex main
pdflatex main
```

No Overleaf, suba esta pasta junto com `resultados/figuras/` e compile `main.tex`.

> O PDF **não está versionado**: ele é gerado a partir desta fonte. Quem tiver LaTeX
> instalado deve gerá-lo e anexá-lo à release de entrega, conforme a Issue #55.

## Figuras

Vêm de `../resultados/figuras/`, resolvidas pelo `\graphicspath` do `main.tex`, e são
geradas por `python -m analise` — nenhuma é editada à mão. Todas são PDF vetorial, sem
imagem rasterizada embutida, o que é verificado por `tests/test_artigo.py`.

## Conferência dos números

Todo número citado no texto vem de um arquivo em `../resultados/`. Para regerar tudo:

```bash
python -m analise --dados data/processed --saida resultados
```
