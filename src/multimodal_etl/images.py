"""Téléchargement des images (volet « vision » de la donnée multimodale).

Une publication multimodale n'est réellement exploitable que si l'image existe
**sur le disque**, à côté du texte : une URL peut être morte, protégée ou pointer
vers autre chose qu'une image. Ce module télécharge donc chaque image, la valide
avec Pillow, puis renvoie le **chemin du fichier** — c'est ce chemin qui est écrit
dans le JSON brut aux côtés du texte.

Le module est organisé en quatre petites fonctions :

1. :func:`url_plausible` — filtre les URL manifestement inutilisables (gratuit) ;
2. :func:`filename_for` — construit un nom déterministe (relance = pas de doublon) ;
3. :func:`download_image` — télécharge et valide **une** image ;
4. :func:`download_images` — parcourt les publications et complète ``image_path``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, UnidentifiedImageError

from multimodal_etl.config import IMAGES_DIR, ImageConfig, ensure_dirs, relative_path
from multimodal_etl.logging_setup import get_logger

logger = get_logger(__name__)

# Extension de fichier associée à chaque type MIME accepté.
_EXTENSIONS: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def url_plausible(image_url: str) -> bool:
    """Indique si une URL a une chance d'être une image téléchargeable.

    On se contente ici d'un contrôle gratuit (schéma HTTP(S) et hôte présent) :
    le vrai contrôle, c'est le téléchargement. On ne filtre volontairement pas sur
    l'extension du fichier, car beaucoup de CDN servent des images via des URL
    sans extension.
    """
    if not image_url:
        return False
    analyse = urlparse(image_url)
    return analyse.scheme in {"http", "https"} and bool(analyse.netloc)


def filename_for(image_url: str, type_mime: str) -> str:
    """Construit un nom de fichier déterministe à partir de l'URL de l'image.

    Le nom dépend uniquement de l'URL : relancer le pipeline réécrit le même
    fichier au lieu d'en accumuler des copies.
    """
    # Empreinte utilisée comme nom de fichier, pas comme protection : d'où
    # `usedforsecurity=False`.
    empreinte = hashlib.sha1(image_url.encode(), usedforsecurity=False).hexdigest()[:16]
    extension = _EXTENSIONS.get(type_mime, ".jpg")
    return f"{empreinte}{extension}"


def download_image(image_url: str, config: ImageConfig, dossier: Path | None = None) -> Path | None:
    """Télécharge une image et renvoie son chemin, ou ``None`` si elle est inutilisable.

    Trois contrôles successifs, du moins cher au plus cher :
    type MIME annoncé, puis taille du fichier, puis ouverture réelle par Pillow.
    """
    dossier = dossier or IMAGES_DIR
    dossier.mkdir(parents=True, exist_ok=True)

    if not url_plausible(image_url):
        return None

    try:
        reponse = requests.get(
            image_url,
            timeout=config.request_timeout,
            headers={"User-Agent": config.user_agent},
        )
        reponse.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Image : téléchargement impossible (%s) : %s", image_url[:80], exc)
        return None

    # 1. Le serveur annonce-t-il bien une image d'un type que l'on sait lire ?
    type_mime = reponse.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if type_mime not in config.accepted_mime_types:
        logger.warning("Image : type '%s' refusé pour %s", type_mime, image_url[:80])
        return None

    # 2. Le fichier tient-il dans le budget disque fixé ?
    poids_mo = len(reponse.content) / (1024 * 1024)
    if poids_mo > config.max_size_mb:
        logger.warning("Image : %.1f Mo au-dessus de la limite pour %s", poids_mo, image_url[:80])
        return None

    path_for = dossier / filename_for(image_url, type_mime)
    path_for.write_bytes(reponse.content)

    # 3. Le fichier est-il une image réellement décodable ? (URL piégée, fichier tronqué)
    try:
        with Image.open(path_for) as image:
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        logger.warning("Image : fichier illisible, supprimé (%s) : %s", path_for.name, exc)
        path_for.unlink(missing_ok=True)
        return None

    return path_for


def download_images(
    records: list[dict[str, object]], config: ImageConfig | None = None
) -> dict[str, int]:
    """Complète chaque publication avec le chemin de son image téléchargée.

    Modifie les dictionnaires sur place en renseignant ``image_path`` — un chemin
    **relatif à la racine du projet**, pour rester valable en local comme dans le
    conteneur Airflow — ou une chaîne clear si l'image n'a pas pu être récupérée.
    Renvoie un compte rendu chiffré, repris par les KPI.
    """
    config = config or ImageConfig()
    ensure_dirs()

    compteurs = {"tentees": 0, "reussies": 0, "echouees": 0, "ignorees": 0, "octets": 0}

    for record in records:
        image_url = str(record.get("image_url", ""))

        # Plafond atteint : on n'essaie plus, mais on garde la publication.
        if compteurs["tentees"] >= config.max_images:
            record["image_path"] = ""
            compteurs["ignorees"] += 1
            continue

        if not url_plausible(image_url):
            record["image_path"] = ""
            compteurs["ignorees"] += 1
            continue

        compteurs["tentees"] += 1
        path_for = download_image(image_url, config)
        if path_for is None:
            record["image_path"] = ""
            compteurs["echouees"] += 1
            continue

        record["image_path"] = relative_path(path_for)
        compteurs["reussies"] += 1
        compteurs["octets"] += path_for.stat().st_size

    logger.info(
        "Images : %d téléchargées, %d échecs, %d ignorées (%.1f Mo sur disque)",
        compteurs["reussies"],
        compteurs["echouees"],
        compteurs["ignorees"],
        compteurs["octets"] / (1024 * 1024),
    )
    return compteurs
