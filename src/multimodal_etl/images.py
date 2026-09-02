"""Image download (the "vision" half of the multimodal data).

A multimodal publication is only really usable once the image exists **on disk**, next to
the text: a URL can be dead, gated, or point at something that is not an image. So this
module downloads each image, validates it with Pillow, then returns the **file path** —
and it is that path which gets written into the raw JSON alongside the text.

The module is laid out as four small functions:

1. :func:`url_plausible` — filters out the obviously unusable URLs, for free;
2. :func:`filename_for` — builds a deterministic name (a rerun makes no duplicate);
3. :func:`download_image` — downloads and validates **one** image;
4. :func:`download_images` — walks the publications and fills in ``image_path``.
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

# File extension matching each accepted MIME type.
_EXTENSIONS: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def url_plausible(image_url: str) -> bool:
    """Say whether a URL stands a chance of being a downloadable image.

    All we do here is a free check — an HTTP(S) scheme and a host. The real check is the
    download itself. We deliberately do not filter on the file extension, because many
    CDNs serve images through URLs that have none.
    """
    if not image_url:
        return False
    parsed = urlparse(image_url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def filename_for(image_url: str, mime_type: str) -> str:
    """Build a deterministic file name from the image URL.

    The name depends on the URL alone: replaying the pipeline rewrites the same file
    instead of piling up copies of it.
    """
    # The hash is a file name, not a protection: hence `usedforsecurity=False`.
    fingerprint = hashlib.sha1(image_url.encode(), usedforsecurity=False).hexdigest()[:16]
    extension = _EXTENSIONS.get(mime_type, ".jpg")
    return f"{fingerprint}{extension}"


def download_image(
    image_url: str, config: ImageConfig, directory: Path | None = None
) -> Path | None:
    """Download an image and return its path, or ``None`` when it is unusable.

    Three checks in a row, cheapest first: the announced MIME type, then the file size,
    then a real open by Pillow.
    """
    directory = directory or IMAGES_DIR
    directory.mkdir(parents=True, exist_ok=True)

    if not url_plausible(image_url):
        return None

    try:
        response = requests.get(
            image_url,
            timeout=config.request_timeout,
            headers={"User-Agent": config.user_agent},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Image: download failed (%s): %s", image_url[:80], exc)
        return None

    # 1. Does the server actually announce an image of a type we can read?
    mime_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if mime_type not in config.accepted_mime_types:
        logger.warning("Image: type '%s' rejected for %s", mime_type, image_url[:80])
        return None

    # 2. Does the file fit the disk budget we set?
    size_mb = len(response.content) / (1024 * 1024)
    if size_mb > config.max_size_mb:
        logger.warning("Image: %.1f MB over the limit for %s", size_mb, image_url[:80])
        return None

    path = directory / filename_for(image_url, mime_type)
    path.write_bytes(response.content)

    # 3. Is the file a genuinely decodable image? (booby-trapped URL, truncated file)
    try:
        with Image.open(path) as image:
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        logger.warning("Image: unreadable file, deleted (%s): %s", path.name, exc)
        path.unlink(missing_ok=True)
        return None

    return path


def download_images(
    records: list[dict[str, object]], config: ImageConfig | None = None
) -> dict[str, int]:
    """Fill in each publication with the path of its downloaded image.

    Modifies the dictionaries in place, setting ``image_path`` — a path **relative to the
    project root**, so it stays valid locally as well as inside the Airflow container — or
    an empty string when the image could not be fetched. Returns a numeric report, which
    the KPIs pick up.
    """
    config = config or ImageConfig()
    ensure_dirs()

    counts = {"tentees": 0, "reussies": 0, "echouees": 0, "ignorees": 0, "octets": 0}

    for record in records:
        image_url = str(record.get("image_url", ""))

        # Cap reached: we stop trying, but we keep the publication.
        if counts["tentees"] >= config.max_images:
            record["image_path"] = ""
            counts["ignorees"] += 1
            continue

        if not url_plausible(image_url):
            record["image_path"] = ""
            counts["ignorees"] += 1
            continue

        counts["tentees"] += 1
        path = download_image(image_url, config)
        if path is None:
            record["image_path"] = ""
            counts["echouees"] += 1
            continue

        record["image_path"] = relative_path(path)
        counts["reussies"] += 1
        counts["octets"] += path.stat().st_size

    logger.info(
        "Images: %d downloaded, %d failures, %d skipped (%.1f MB on disk)",
        counts["reussies"],
        counts["echouees"],
        counts["ignorees"],
        counts["octets"] / (1024 * 1024),
    )
    return counts
