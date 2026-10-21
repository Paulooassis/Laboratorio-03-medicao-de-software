# Artigo

Fonte LaTeX do artigo, no template da SBC.

## Para abrir no Overleaf (caminho recomendado)

Use **[`artigo-overleaf.tex`](artigo-overleaf.tex)**: é o artigo inteiro em um arquivo só,
com a bibliografia embutida em `thebibliography`, então compila em uma passada, sem
`bibtex` e sem `.bib` separado.

1. Abra o [template SBC no Overleaf](https://www.overleaf.com/latex/templates/sbc-conferences-template/blbxwjwzdngr)
   e clique em *Open as Template* — ele já traz `sbc-template.sty`.
2. Substitua o conteúdo do `.tex` principal pelo de `artigo-overleaf.tex`.
3. Envie os três PDFs de `../resultados/figuras/` (`artigo_violino_metricas.pdf`,
   `artigo_dispersao_df_cfr.pdf`, `artigo_correlacao.pdf`) para uma pasta `figuras/` do
   projeto.

Sem as figuras o documento **ainda compila**: cada uma vira uma moldura dizendo qual
arquivo falta, em vez de quebrar a compilação.

## Fonte modular

O artigo é mantido em [`main.tex`](main.tex) mais [`secoes/`](secoes/), para que cada seção
entre por um PR próprio, e [`referencias.bib`](referencias.bib). O arquivo do Overleaf é
**gerado** a partir dessas fontes:

```bash
python artigo/montar_overleaf.py
```

Edite as seções, nunca o `artigo-overleaf.tex` — ele é sobrescrito.

## Contagem de páginas

O limite é de 10 páginas. Na última medição, com um substituto local do `sbc-template.sty`
que aproxima a caixa de texto oficial (A4, Times 12 pt, margens de 3 cm), o artigo ficou em
**14 páginas**. O template real pode diferir em uma página ou outra, mas não fecha a
diferença: **o texto precisa ser cortado antes da entrega**.

Para medir localmente sem instalar uma distribuição TeX completa:

```bash
brew install tectonic
tectonic -X compile artigo-overleaf.tex --keep-logs
grep -o "Output written on.*pages" artigo-overleaf.log
```

## Figuras

Vêm de `../resultados/figuras/`, geradas por `python -m analise` — nenhuma é editada à mão.
Todas são PDF vetorial, sem imagem rasterizada embutida, o que é verificado por
`tests/test_artigo.py`.

## Conferência dos números

Todo número citado no texto vem de um arquivo em `../resultados/`. Para regerar:

```bash
python -m analise --dados data/processed --saida resultados
```
