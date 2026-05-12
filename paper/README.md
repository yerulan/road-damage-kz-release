# Paper Draft

`main.tex` is an MDPI-style manuscript draft for the Applied Sciences target.

The official MDPI ACS LaTeX template was downloaded from MDPI's LaTeX author page and its `Definitions/` directory is available under `paper/`.

Build target:

```bash
cd paper
pdflatex main.tex
pdflatex main.tex
```

Before submission, replace all remaining author placeholders and keep all dataset counts and metrics synchronized with:

```bash
roadkz figures --paper
roadkz project-status --fail-on-blockers
```

The current manuscript should remain framed as an Applied Sciences external-validation/domain-shift article. Do not pivot it to MDPI Data or Data in Brief unless the dataset becomes redistributable at data-journal scale.
