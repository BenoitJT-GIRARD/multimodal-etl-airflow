"""Construit l'échantillon de démonstration du jeu Fakeddit.

Le jeu Fakeddit complet se télécharge depuis Kaggle avec un compte utilisateur ; il
n'est donc pas versionné dans le dépôt. Pour que le pipeline reste exécutable
immédiatement par n'importe qui, on versionne à la place un petit fichier au
**format exact du jeu réel** (mêmes colonnes, même codage des labels).

Les titres sont fabriqués et neutres ; les images, elles, sont de **vraies images
libres de droits** hébergées par Wikimedia Commons, afin que l'étape de
téléchargement et de validation des images travaille sur du contenu réel.

Dès qu'un fichier ``.tsv`` est déposé dans ``data/raw/kaggle/``, le connecteur
l'utilise à la place de cet échantillon.

Usage :
    uv run python scripts/outillage/build_sample_fakeddit.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from multimodal_etl.config import SAMPLES_DIR, ensure_dirs

BASE_COMMONS = "https://upload.wikimedia.org/wikipedia/commons"

# (label 2 classes, sous-reddit, titre, chemin de l'image sur Wikimedia Commons)
_LIGNES: tuple[tuple[str, str, str, str], ...] = (
    (
        "0",
        "fakenews",
        "Front page announces free electricity for every household next month",
        "thumb/d/d5/10-04-2010_in_Warsaw.jpg/960px-10-04-2010_in_Warsaw.jpg",
    ),
    (
        "1",
        "news",
        "Newspapers on display at a Tehran newsstand",
        "d/d0/2011_newspapers_Tehran_6030393078.jpg",
    ),
    (
        "0",
        "fakenews",
        "Viral photo claims a new law bans all private cars downtown",
        "thumb/e/e2/A_Daily_Newspaper_Seller.jpg/960px-A_Daily_Newspaper_Seller.jpg",
    ),
    (
        "1",
        "news",
        "Newspaper vending machine on a street in Mississippi",
        "thumb/3/32/A_newspaper_vending_machine_in_Mississippi%2C_USA.jpg/"
        "960px-A_newspaper_vending_machine_in_Mississippi%2C_USA.jpg",
    ),
    (
        "0",
        "fakenews",
        "Headline claims a common kitchen spice was approved as a vaccine",
        "c/c8/Death_to_fascism_%28newspaper%29.jpg",
    ),
    (
        "1",
        "news",
        "Historic front page reporting the first landing on the Moon",
        "thumb/9/9a/Land_on_the_Moon_7_21_1969-repair.jpg/960px-Land_on_the_Moon_7_21_1969-repair.jpg",
    ),
    (
        "0",
        "fakenews",
        "Famous mistaken headline reused to claim an election was overturned",
        "thumb/0/09/Dewey_Defeats_Truman.jpg/960px-Dewey_Defeats_Truman.jpg",
    ),
    (
        "1",
        "news",
        "Front page of a regional newspaper published in 1865",
        "thumb/4/4d/Front_Page_of_the_Fayetteville_Observer_newspaper_from_March_9%2C_1865.jpg/"
        "960px-Front_Page_of_the_Fayetteville_Observer_newspaper_from_March_9%2C_1865.jpg",
    ),
    (
        "0",
        "fakenews",
        "Doctored press photo circulated as proof of a cancelled summit",
        "thumb/c/c2/Rus_newspaper_1905.jpg/960px-Rus_newspaper_1905.jpg",
    ),
    (
        "1",
        "news",
        "Reader at a cafe terrace in Athens in 1979",
        "thumb/a/ad/Man_reading_a_newspaper_at_a_caf%C3%A9_terrace_in_Athens%2C_Greece_-_1979.jpg/"
        "960px-Man_reading_a_newspaper_at_a_caf%C3%A9_terrace_in_Athens%2C_Greece_-_1979.jpg",
    ),
    (
        "0",
        "fakenews",
        "Old advertisement presented as a recent government announcement",
        "thumb/a/a9/Old_newspaper_ad.png/960px-Old_newspaper_ad.png",
    ),
    (
        "1",
        "news",
        "Group of newspaper vending machines on a city sidewalk",
        "thumb/0/01/Group_of_Newspaper_Vending_Machines.jpg/960px-Group_of_Newspaper_Vending_Machines.jpg",
    ),
    (
        "0",
        "fakenews",
        "Archive front page recycled to claim a bank closure",
        "thumb/b/b9/The_front_page_of_The_Toccoa_Record_newspaper_on_March_8%2C_1901.png/"
        "960px-The_front_page_of_The_Toccoa_Record_newspaper_on_March_8%2C_1901.png",
    ),
    (
        "1",
        "news",
        "Newspaper delivery round early in the morning",
        "thumb/5/53/Newspaper_delivery.jpg/960px-Newspaper_delivery.jpg",
    ),
    (
        "0",
        "fakenews",
        "Post claims the moon will stay invisible for a full week",
        "thumb/c/c1/Piercing_newspaper_with_a_Slingshot.jpg/960px-Piercing_newspaper_with_a_Slingshot.jpg",
    ),
    (
        "1",
        "news",
        "Headquarters of a local newspaper in North Carolina",
        "thumb/1/17/The_Cherokee_Scout_newspaper_headquarters_in_Murphy%2C_North_Carolina.jpg/"
        "960px-The_Cherokee_Scout_newspaper_headquarters_in_Murphy%2C_North_Carolina.jpg",
    ),
    (
        "0",
        "fakenews",
        "Fabricated quote attributed to a central bank governor",
        "thumb/a/a8/USSR_newspaper._Za_Rubezhom._1991_year._img_16.jpg/"
        "960px-USSR_newspaper._Za_Rubezhom._1991_year._img_16.jpg",
    ),
    (
        "1",
        "news",
        "USA Today vending machine photographed in a street",
        "thumb/d/d9/USA_Today_Newspaper_Vending_Machine.jpg/960px-USA_Today_Newspaper_Vending_Machine.jpg",
    ),
    (
        "0",
        "fakenews",
        "Unrelated archive photo used to illustrate a fake evacuation order",
        "thumb/0/05/Remains_of_an_Arabic_newspaper_in_Al_Kharrara.jpg/"
        "960px-Remains_of_an_Arabic_newspaper_in_Al_Kharrara.jpg",
    ),
    (
        "1",
        "news",
        "Man reading the morning paper in Basantapur",
        "thumb/a/a0/Old_man_reading_newspaper_early_in_the_morning_at_Basantapur-IMG_6800.jpg/"
        "960px-Old_man_reading_newspaper_early_in_the_morning_at_Basantapur-IMG_6800.jpg",
    ),
    (
        "0",
        "fakenews",
        "Screenshot claims a national holiday was added to the calendar",
        "thumb/1/14/The_Franklin_Press_newspaper_in_Franklin%2C_North_Carolina.jpg/"
        "960px-The_Franklin_Press_newspaper_in_Franklin%2C_North_Carolina.jpg",
    ),
    (
        "1",
        "news",
        "Stack of newspapers ready for distribution",
        "thumb/8/8a/Vecteezy_stack-of-newspaper_1961329.jpg/960px-Vecteezy_stack-of-newspaper_1961329.jpg",
    ),
    (
        "0",
        "fakenews",
        "Edited headline claims a stadium was demolished overnight",
        "5/52/Newspaper_bag.jpg",
    ),
    (
        "1",
        "news",
        "First issue of the newspaper Erkin-Too",
        "1/1a/The_first_newspaper_%22Erkin-Too%22.jpg",
    ),
)

# Colonnes du jeu Fakeddit réel que le connecteur exploite.
COLONNES = (
    "id",
    "clean_title",
    "title",
    "image_url",
    "hasImage",
    "created_utc",
    "domain",
    "subreddit",
    "2_way_label",
)

# Horodatage de départ (1er janvier 2026), incrémenté d'une heure par ligne.
_DEBUT_UTC = 1767225600


def main() -> None:
    """Écrit l'échantillon de démonstration au format Fakeddit."""
    ensure_dirs()
    destination = SAMPLES_DIR / "fakeddit_sample.tsv"

    with destination.open("w", encoding="utf-8", newline="") as fichier:
        redacteur = csv.writer(fichier, delimiter="\t", lineterminator="\n")
        redacteur.writerow(COLONNES)
        for index, (label, subreddit, titre, image) in enumerate(_LIGNES):
            redacteur.writerow(
                (
                    f"demo{index:03d}",
                    titre,
                    titre,
                    f"{BASE_COMMONS}/{image}",
                    "True",
                    _DEBUT_UTC + index * 3600,
                    "commons.wikimedia.org",
                    subreddit,
                    label,
                )
            )

    print(f"[ok] échantillon écrit : {destination} ({len(_LIGNES)} lignes)")


if __name__ == "__main__":
    main()
