# Artigo

Fonte LaTeX do artigo, no template da SBC.

## Para abrir no Overleaf

Há dois arquivos gerados, conforme o que você precisa colar:

| Arquivo | Quando usar |
| --- | --- |
| [`artigo-overleaf.tex`](artigo-overleaf.tex) | Documento inteiro, com preâmbulo e bibliografia embutida — substitui o `.tex` principal |
| [`secoes-overleaf.tex`](secoes-overleaf.tex) | Só as seções, para colar no corpo de um documento que já existe |

Os dois referenciam as figuras como `figuras/<arquivo>.pdf` e **já trazem a
bibliografia**, que vive no fim de [`secoes/07-conclusao.tex`](secoes/07-conclusao.tex) em
um bloco `thebibliography` — não há `.bib` nem `bibtex` no projeto, de propósito: uma
fonte só, e o documento compila em duas passadas simples.

1. Abra o [template SBC no Overleaf](https://www.overleaf.com/latex/templates/sbc-conferences-template/blbxwjwzdngr)
   com *Open as Template* — ele já traz `sbc-template.sty`.
2. Crie uma pasta `figuras/` no projeto e envie os **seis PDFs** de
   `../resultados/figuras/artigo_*.pdf`.
3. Cole o arquivo escolhido acima.

Ao colar apenas as seções, confira que o preâmbulo tem `graphicx`, `amsmath`, `booktabs`,
`multirow` e `url`. Se o documento de destino já tiver um `thebibliography`, remova um dos
dois para a lista não sair duplicada.

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
