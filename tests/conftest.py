"""Shared fixtures for the low test suite."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Minimal in-memory database for fast, offline tests
# ---------------------------------------------------------------------------
_MINIMAL_DB = {
    "continents": [
        {"id": "002", "label": "Africa"},
        {"id": "019", "label": "Americas"},
        {"id": "142", "label": "Asia"},
        {"id": "150", "label": "Europe"},
    ],
    "regions": [
        {"id": "014", "label": "Eastern Africa",  "continent_id": "002"},
        {"id": "005", "label": "South America",   "continent_id": "019"},
        {"id": "034", "label": "Southern Asia",   "continent_id": "142"},
        {"id": "155", "label": "Western Europe",  "continent_id": "150"},
    ],
    "countries": [
        {"code": "RW", "label": "Rwanda",   "continent_id": "002", "region_id": "014", "population": 13776698},
        {"code": "CD", "label": "DR Congo", "continent_id": "002", "region_id": "014", "population": 99010212},
        {"code": "UG", "label": "Uganda",   "continent_id": "002", "region_id": "014", "population": 45741000},
        {"code": "BR", "label": "Brazil",   "continent_id": "019", "region_id": "005", "population": 214300000},
        {"code": "IN", "label": "India",    "continent_id": "142", "region_id": "034", "population": 1380004385},
        {"code": "DE", "label": "Germany",  "continent_id": "150", "region_id": "155", "population": 83200000},
    ],
    # Glottolog tree slice used by tests:
    #   indo1319 (Indo-European)
    #     └─ germ1287 (Germanic)
    #          └─ west2793 (West Germanic)
    #   atla1278 (Atlantic-Congo)   [root, no parent]
    "families": [
        {"glottocode": "indo1319", "label": "Indo-European",  "parent_glottocode": None},
        {"glottocode": "germ1287", "label": "Germanic",       "parent_glottocode": "indo1319"},
        {"glottocode": "west2793", "label": "West Germanic",  "parent_glottocode": "germ1287"},
        {"glottocode": "atla1278", "label": "Atlantic-Congo", "parent_glottocode": None},
    ],
    "languages": [
        {
            "part3": "kin", "part1": "rw",
            "label": "Kinyarwanda", "scope": "I",
            "speaker_count": 12000000,
            "glottocode": "kiny1244",
            "family_glottocode": "atla1278",
            "country_codes": ["RW", "CD", "UG"],
        },
        {
            "part3": "fra", "part1": "fr",
            "label": "French", "scope": "I",
            "speaker_count": 76000000,
            "glottocode": "stan1290",
            "family_glottocode": "indo1319",
            "country_codes": ["RW"],
        },
        {
            "part3": "por", "part1": "pt",
            "label": "Portuguese", "scope": "I",
            "speaker_count": 232000000,
            "glottocode": "port1283",
            "family_glottocode": "indo1319",
            "country_codes": ["BR"],
        },
        {
            "part3": "hin", "part1": "hi",
            "label": "Hindi", "scope": "I",
            "speaker_count": 344000000,
            "glottocode": "hind1269",
            "family_glottocode": "indo1319",
            "country_codes": ["IN"],
        },
        {
            "part3": "deu", "part1": "de",
            "label": "German", "scope": "I",
            "speaker_count": 75000000,
            "glottocode": "stan1295",
            "family_glottocode": "west2793",
            "country_codes": ["DE"],
        },
        {
            "part3": "arc", "part1": None,
            "label": "Official Aramaic", "scope": "I",
            "speaker_count": 0,
            "glottocode": None,
            "family_glottocode": None,
            "country_codes": [],
        },
    ],
    "country_language_speakers": [
        {"country_code": "RW", "language_code": "kin", "speaker_count": 10200000,  "speaker_fraction": 0.74,   "source": "cldr"},
        {"country_code": "RW", "language_code": "fra", "speaker_count": 300000,    "speaker_fraction": 0.022,  "source": "cldr"},
        {"country_code": "BR", "language_code": "por", "speaker_count": 211000000, "speaker_fraction": 0.984,  "source": "cldr"},
        {"country_code": "IN", "language_code": "hin", "speaker_count": 528000000, "speaker_fraction": 0.383,  "source": "cldr"},
        {"country_code": "DE", "language_code": "deu", "speaker_count": 72000000,  "speaker_fraction": 0.866,  "source": "cldr"},
        {"country_code": "RW", "language_code": "kin", "speaker_count": 9900000,   "speaker_fraction": 0.718,  "source": "cia"},
        {
            "country_code": "UG",
            "language_code": "kin",
            "speaker_count": 450000,
            "speaker_fraction": 0.009838,
            "source": "low_scraper",
            "source_url": "https://example.org/kinyarwanda-uganda",
        },
        {"country_code": "DE", "language_code": "deu", "speaker_count": 74000000,  "speaker_fraction": 0.886,  "source": "cia"},
    ],
    "country_official_languages": [
        {"country_code": "RW", "language_code": "kin", "status": "official"},
        {"country_code": "RW", "language_code": "fra", "status": "official"},
        {"country_code": "BR", "language_code": "por", "status": "official"},
        {"country_code": "DE", "language_code": "deu", "status": "official"},
        {"country_code": "IN", "language_code": "hin", "status": "de_facto_official"},
    ],
}


@pytest.fixture(scope="session")
def minimal_db_path(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("db") / "low_db.json"
    path.write_text(json.dumps(_MINIMAL_DB), encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def db(minimal_db_path):
    """LanguagesOfTheWorld client wired to the minimal fixture database."""
    from low import LanguagesOfTheWorld
    return LanguagesOfTheWorld(db_path=minimal_db_path)
