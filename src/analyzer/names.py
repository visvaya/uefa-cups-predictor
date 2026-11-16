"""Team name normalisation shared by The Analyst and soccer-rating inputs."""

import unicodedata

import pandas as pd

# Analyst or variant spelling -> the key both sources share (after `remove_diacritics` and lowercasing)
NAME_FIX: dict[str, str] = {
    # Diacritics/Variants
    "boda/glimt": "bodo/glimt",
    "kabenhavn": "kobenhavn",
    "atletico madrid": "atletico",
    "atletico de madrid": "atletico",
    "real": "real madrid",
    "nottm forest": "nottingham forest",
    # Europa League: Analyst -> Soccer-rating
    "sturm": "sturm graz",
    "brann": "sk brann bergen",
    "maccabi ta": "maccabi tel aviv",
    "go ahead": "go ahead eagles",
    "crvena zvezda": "crvena zvezda belgrade",
    "fcsb": "steaua bukarest",
    "plzen": "fk viktoria plzen",
    "nice": "ogc nice",
    "ferencvaros": "ferencvaros budapest",
    "young boys": "young boys bern",
    "rangers": "glasgow rangers",
    "feyenoord": "feyenoord rotterdam",
    "paok": "paok saloniki",
    "porto": "fc porto",
    "salzburg": "red bull salzburg",
    "celtic": "celtic glasgow",
    "utrecht": "fc utrecht",
    "basel": "fc basel",
    "midtjylland": "fc midtjylland",
    "celta": "celta de vigo",
    "braga": "sporting braga",
    "genk": "krc genk",
    "malmo": "malmo ff",
    "lille": "osc lille",
    "freiburg": "sc freiburg",
    "bologna": "bologna fc",
    "lyon": "olympique lyon",
    "roma": "as roma",
    "ludogorets": "ludogorets razgrad",
    "betis": "betis sevilla",
    "stuttgart": "vfb stuttgart",
    # Champions League variants (proactive)
    "man city": "manchester city",
    "paris sg": "paris saint-germain",
    "spurs": "tottenham hotspur",
    "ajax": "ajax amsterdam",
    "newcastle": "newcastle united",
    "r. union sg": "royal union saint-gilloise",
    "athletic": "athletic bilbao",
}


def remove_diacritics(s: str) -> str:
    """Removes diacritics and normalizes text to ASCII (includes ø, ł, æ, etc.)."""
    mapping: dict[int | str, int | str | None] = {
        "\u00f8": "o",
        "\u00d8": "O",
        "\u0142": "l",
        "\u0141": "L",
        "\u00e6": "ae",
        "\u00c6": "AE",
        "\u00e5": "a",
        "\u00c5": "A",
    }
    s = s.translate(str.maketrans(mapping))
    normalized = unicodedata.normalize("NFD", s)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def norm_key(s: object) -> str:
    """Creates a normalized key for team names; missing values (None/NaN) map to an empty key."""
    if pd.isna(s) or s is None:
        return ""
    s = remove_diacritics(str(s)).strip().lower()
    return NAME_FIX.get(s, s)
