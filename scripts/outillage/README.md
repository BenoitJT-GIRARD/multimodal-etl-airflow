# Scripts d'outillage

Ces scripts **ne font pas partie du pipeline**. Ils servent uniquement à produire ou
reproduire des artefacts du projet à partir du code, pour que ces artefacts ne se
désynchronisent jamais de ce qu'ils décrivent.

| Script | Produit | Quand le relancer |
|---|---|---|
| `build_notebooks.py` | les quatre notebooks de `notebooks/` | après une modification du pipeline qu'ils illustrent |
| `build_presentation.py` | `reports/presentation.pptx` | avant la session de bilan |
| `build_sample_fakeddit.py` | `data/samples/fakeddit_sample.tsv` | jamais, sauf pour régénérer l'échantillon de démonstration |

Les scripts qui font tourner le pipeline, eux, sont dans `scripts/` :
`run_extraction.py`, `run_transformation.py`, `run_chargement.py`, `run_etl.py` et
`build_schema_diagram.py`.

## Usage

```powershell
uv run python scripts/outillage/build_notebooks.py --execute
uv run python scripts/outillage/build_presentation.py
uv run python scripts/outillage/build_sample_fakeddit.py
```
