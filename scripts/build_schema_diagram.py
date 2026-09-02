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

from multimodal_etl.schema import ENTITES, fields_of

DOCS_DIR = ROOT / "docs"

# L'affectation des champs aux entites vient directement de multimodal_etl.schema :
# ajouter un champ au schema le fait apparaitre dans le diagramme sans rien
# modifier ici.

# Relations conceptuelles (cardinalites Mermaid).
RELATIONS: tuple[tuple[str, str, str, str], ...] = (
    ("SOURCE", "||--o{", "PUBLICATION", "publie"),
    ("PUBLICATION", "||--||", "CONTENU_TEXTE", "porte"),
    ("PUBLICATION", "||--||", "CONTENU_IMAGE", "associe"),
    ("PUBLICATION", "||--o|", "LABEL", "annote"),
)


def _mermaid_type(dtype: str) -> str:
    """Traduit un type logique en type lisible pour le diagramme."""
    correspondance = {
        "string": "string",
        "integer": "int",
        "boolean": "bool",
        "datetime": "datetime",
    }
    return correspondance.get(dtype, dtype)


def _key(entite: str, nom: str) -> str:
    """Indique si un champ est cle primaire ou cle etrangere dans son entite."""
    if entite == "PUBLICATION" and nom == "id":
        return "PK"
    if entite == "PUBLICATION" and nom == "source_id":
        return "FK"
    if entite == "SOURCE" and nom == "source_id":
        return "PK"
    # Les entites de contenu partagent la cle de la publication qu'elles decrivent.
    if nom == "id":
        return "PK"
    return ""


def build_mermaid() -> str:
    """Construit le texte Mermaid du schema conceptuel."""
    lignes = ["erDiagram"]

    # Relations.
    for gauche, cardinalite, droite, libelle in RELATIONS:
        lignes.append(f"    {gauche} {cardinalite} {droite} : {libelle}")
    lignes.append("")

    # Entites et attributs (type + role + cle).
    for entite in ENTITES:
        lignes.append(f"    {entite} {{")
        # La cle de jointure est rappelee sur chaque entite de contenu.
        if entite in {"CONTENU_TEXTE", "CONTENU_IMAGE", "LABEL"}:
            lignes.append('        string id PK "KEY"')
        if entite == "SOURCE":
            lignes.append('        string source_id PK "KEY"')
        for spec in fields_of(entite):
            lignes.append(
                f"        {_mermaid_type(spec.dtype)} {spec.name} "
                f'{_key(entite, spec.name)} "{spec.role}"'
            )
        lignes.append("    }")
        lignes.append("")

    return "\n".join(lignes).rstrip() + "\n"


def render_diagram(mmd_path: Path) -> None:
    """Rend le .mmd en PNG et PDF via mmdc si l'outil est disponible."""
    mmdc = shutil.which("mmdc") or shutil.which("mmdc.cmd")
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if mmdc:
        commande_base = [mmdc]
    elif npx:
        commande_base = [npx, "-y", "@mermaid-js/mermaid-cli"]
    else:
        print(
            "[warn] ni mmdc ni npx disponibles : render_diagram ignore, le .mmd reste exploitable."
        )
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
            print(
                f"[warn] rendu {extension} non genere ({exc}). Le .mmd reste exploitable."
            )


def main() -> None:
    """Genere le .mmd puis ses rendus."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    mmd_path = DOCS_DIR / "schema_donnees.mmd"
    mmd_path.write_text(build_mermaid(), encoding="utf-8")
    print(f"[ok] schema Mermaid ecrit : {mmd_path}")
    render_diagram(mmd_path)


if __name__ == "__main__":
    main()
