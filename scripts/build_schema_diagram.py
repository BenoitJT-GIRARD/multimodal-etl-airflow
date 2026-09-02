"""Generate the conceptual data schema.

The diagram is built from :data:`multimodal_etl.schema.FIELDS` (the single source of
truth), so code, documentation and schema always stay aligned. It produces a Mermaid file
``docs/data_schema.mmd`` then, when ``mmdc`` (mermaid-cli, through npx) is available, its
PNG and PDF renderings.

The model is **conceptual** — business entities and relations, not physical storage. It
makes the role of every field explicit and shows the text-image link visually.

Usage:
    uv run python scripts/build_schema_diagram.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from multimodal_etl.schema import ENTITIES, fields_of

DOCS_DIR = ROOT / "docs"

# Which field belongs to which entity comes straight from multimodal_etl.schema: adding a
# field to the schema makes it appear in the diagram without touching anything here.

# Conceptual relations (Mermaid cardinalities).
RELATIONS: tuple[tuple[str, str, str, str], ...] = (
    ("SOURCE", "||--o{", "PUBLICATION", "publie"),
    ("PUBLICATION", "||--||", "CONTENU_TEXTE", "porte"),
    ("PUBLICATION", "||--||", "CONTENU_IMAGE", "associe"),
    ("PUBLICATION", "||--o|", "LABEL", "annote"),
)


def _mermaid_type(dtype: str) -> str:
    """Translate a logical type into one the diagram can display."""
    mapping = {
        "string": "string",
        "integer": "int",
        "boolean": "bool",
        "datetime": "datetime",
    }
    return mapping.get(dtype, dtype)


def _key(entity: str, name: str) -> str:
    """Say whether a field is a primary or a foreign key within its entity."""
    if entity == "PUBLICATION" and name == "id":
        return "PK"
    if entity == "PUBLICATION" and name == "source_id":
        return "FK"
    if entity == "SOURCE" and name == "source_id":
        return "PK"
    # The content entities share the key of the publication they describe.
    if name == "id":
        return "PK"
    return ""


def build_mermaid() -> str:
    """Build the Mermaid text of the conceptual schema."""
    lines = ["erDiagram"]

    # Relations.
    for left, cardinality, right, label in RELATIONS:
        lines.append(f"    {left} {cardinality} {right} : {label}")
    lines.append("")

    # Entities and attributes (type + role + key).
    for entity in ENTITIES:
        lines.append(f"    {entity} {{")
        # The join key is repeated on each content entity.
        if entity in {"CONTENU_TEXTE", "CONTENU_IMAGE", "LABEL"}:
            lines.append('        string id PK "KEY"')
        if entity == "SOURCE":
            lines.append('        string source_id PK "KEY"')
        for spec in fields_of(entity):
            lines.append(
                f"        {_mermaid_type(spec.dtype)} {spec.name} "
                f'{_key(entity, spec.name)} "{spec.role}"'
            )
        lines.append("    }")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render(mmd_path: Path) -> None:
    """Render the .mmd as PNG and PDF through mmdc, when the tool is available."""
    mmdc = shutil.which("mmdc") or shutil.which("mmdc.cmd")
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if mmdc:
        base_command = [mmdc]
    elif npx:
        base_command = [npx, "-y", "@mermaid-js/mermaid-cli"]
    else:
        print("[warn] neither mmdc nor npx available: rendering skipped, the .mmd still stands.")
        return
    for extension in ("png", "pdf"):
        output = mmd_path.with_suffix(f".{extension}")
        try:
            subprocess.run(
                [
                    *base_command,
                    "-i",
                    str(mmd_path),
                    "-o",
                    str(output),
                    "-b",
                    "white",
                    "-t",
                    "neutral",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            print(f"[ok] rendering written: {output.name}")
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            print(f"[warn] {extension} rendering failed ({exc}). The .mmd still stands.")


def main() -> None:
    """Generate the .mmd, then its renderings."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    mmd_path = DOCS_DIR / "data_schema.mmd"
    mmd_path.write_text(build_mermaid(), encoding="utf-8")
    print(f"[ok] Mermaid schema written: {mmd_path}")
    render(mmd_path)


if __name__ == "__main__":
    main()
