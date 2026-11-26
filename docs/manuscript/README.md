# Wallet migration manuscript

The numbered Markdown files, [configuration](config.yaml), [preamble](preamble.md),
and [bibliography](references.bib) are the maintained manuscript source. The
[operator walkthrough](../MIGRATION_HOW_TO.md) holds the live migration
instructions.

## Render and check

Use a separate checkout of [docxology/template at commit 87704fe](https://github.com/docxology/template/tree/87704feae0a4490ef7dad9c931d268e8c30273c2)
with Python 3.14 or newer, uv, Pandoc, and XeLaTeX. Use a clean checkout of this
repository named `nockchain-migration` so validation can read its indexed files.
From the template checkout, register this repository and run the two stages.

```sh
nockchain_checkout=/absolute/path/to/nockchain-migration
uv sync --locked --no-dev
mkdir -p projects/working
ln -s "$nockchain_checkout" projects/working/nockchain-migration
uv run --no-sync python scripts/pipeline/stage_03_render.py --project working/nockchain-migration
uv run --no-sync python scripts/pipeline/stage_04_validate.py --project working/nockchain-migration
```

The stages write the PDF at `output/pdf/nockchain-migration_combined.pdf` and HTML
at `output/web/index.html` in this repository. Check the validation and rendered
provenance reports under `output/reports/`.
