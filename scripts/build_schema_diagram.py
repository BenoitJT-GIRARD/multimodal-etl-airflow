"""Genere le schema conceptuel des donnees.

Le diagramme est construit a partir de :data:`multimodal_etl.schema.FIELDS` (source
unique de verite) : code, documentation et schema restent ainsi toujours alignes.
On produit un fichier Mermaid ``docs/schema_donnees.mmd`` puis, si l'outil
``mmdc`` (mermaid-cli, via npx) est disponible, ses rendus PNG et PDF.

Le modele est **conceptuel** (entites / relations metier), pas physique : il
explicite le role de chaque champ et garantit visuellement le lien texte-image.

Usage :
    uv run python scripts/build_schema_diagram.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from multimodal_etl.schema import FIELDS

DOCS_DIR = ROOT / "docs"

# Affectation de chaque champ a une entite conceptuelle (regroupement metier).
ENTITES: dict[str, list[str]] = {
    "PUBLICATION": ["id", "language", "published_at", "ingested_at", "has_image", "text_length"],
    "SOURCE": ["source", "source_type", "domain", "url"],
    "CONTENU_TEXTE": ["title", "text"],
    "CONTENU_IMAGE": ["image_url"],
    "LABEL": ["label", "label_source"],
}

# Relations conceptuelles (cardinalites Mermaid).
RELATIONS: tuple[tuple[str, str, str, str], ...] = (
    ("SOURCE", "||--o{", "PUBLICATION", "publie"),
    ("PUBLICATION", "||--||", "CONTENU_TEXTE", "porte"),
    ("PUBLICATION", "||--||", "CONTENU_IMAGE", "associe"),
    ("PUBLICATION", "||--o|", "LABEL", "annote"),
)


def _type_mermaid(dtype: str) -> str:
    """Traduit un type logique en type lisible pour le diagramme."""
    correspondance = {
        "string": "string",
        "integer": "int",
        "boolean": "bool",
        "datetime": "datetime",
    }
    return correspondance.get(dtype, dtype)


def construit_mermaid() -> str:
    """Construit le texte Mermaid du schema conceptuel."""
    par_nom = {spec.name: spec for spec in FIELDS}
    lignes = ["erDiagram"]

    # Relations.
    for gauche, cardinalite, droite, libelle in RELATIONS:
        lignes.append(f"    {gauche} {cardinalite} {droite} : {libelle}")
    lignes.append("")

    # Entites et attributs (type + role + cle).
    for entite, champs in ENTITES.items():
        lignes.append(f"    {entite} {{")
        for nom in champs:
            spec = par_nom[nom]
            cle = "PK" if spec.role == "KEY" else ""
            commentaire = spec.role
            lignes.append(f'        {_type_mermaid(spec.dtype)} {nom} {cle} "{commentaire}"')
        lignes.append("    }")
        lignes.append("")

    return "\n".join(lignes).rstrip() + "\n"


def rendu(mmd_path: Path) -> None:
    """Rend le .mmd en PNG et PDF via mmdc si l'outil est disponible."""
    mmdc = shutil.which("mmdc") or shutil.which("mmdc.cmd")
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if mmdc:
        commande_base = [mmdc]
    elif npx:
        commande_base = [npx, "-y", "@mermaid-js/mermaid-cli"]
    else:
        print("[warn] ni mmdc ni npx disponibles : rendu ignore, le .mmd reste exploitable.")
        return
    for extension in ("png", "pdf"):
        sortie = mmd_path.with_suffix(f".{extension}")
        try:
            subprocess.run(
                [
                    *commande_base,
                    "-i",
                    str(mmd_path),
                    "-o",
                    str(sortie),
                    "-b",
                    "white",
                    "-t",
                    "neutral",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            print(f"[ok] rendu genere : {sortie.name}")
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            print(f"[warn] rendu {extension} non genere ({exc}). Le .mmd reste exploitable.")


def main() -> None:
    """Genere le .mmd puis ses rendus."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    mmd_path = DOCS_DIR / "schema_donnees.mmd"
    mmd_path.write_text(construit_mermaid(), encoding="utf-8")
    print(f"[ok] schema Mermaid ecrit : {mmd_path}")
    rendu(mmd_path)


if __name__ == "__main__":
    main()
