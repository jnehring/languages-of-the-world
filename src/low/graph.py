from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .collections import (
    ContinentCollection,
    CountryCollection,
    FamilyCollection,
    LanguageCollection,
    RegionCollection,
    SpeakerCountCollection,
)
from .models import Continent, Country, Language, LanguageFamily, Region, SpeakerCount

_DEFAULT_DB = Path(__file__).parent / "data" / "low_db.json"


class LanguagesOfTheWorld:
    """
    Primary client. Loads the baked JSON database and assembles the
    bidirectional in-memory object graph.

    Usage::

        import low
        db = low.LanguagesOfTheWorld()
        lang = db.languages.get("kin")
        for country in lang.countries:
            print(country.region.label, country.continent.label)

        # Walk the Glottolog family tree
        lang = db.languages.get("deu")
        node = lang.family
        while node:
            print(node.depth * "  ", node.label)
            node = node.parent
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        path = Path(db_path) if db_path else _DEFAULT_DB
        raw = self._load(path)
        (
            self.continents,
            self.regions,
            self.countries,
            self.families,
            self.languages,
            self.speaker_counts,
        ) = self._assemble(raw)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load(path: Path) -> Dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(
                f"Database not found at {path}. "
                "Run `python -m low.bootstrap` to generate it."
            )
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)

    @staticmethod
    def _assemble(raw: Dict[str, Any]):
        # --- Continents ------------------------------------------------
        continents: Dict[str, Continent] = {}
        for row in raw.get("continents", []):
            obj = Continent(id=row["id"], label=row["label"])
            continents[row["id"]] = obj

        # --- Regions ---------------------------------------------------
        regions: Dict[str, Region] = {}
        for row in raw.get("regions", []):
            continent = continents[row["continent_id"]]
            obj = Region(id=row["id"], label=row["label"], continent=continent)
            regions[row["id"]] = obj

        # --- Countries -------------------------------------------------
        countries: Dict[str, Country] = {}
        for row in raw.get("countries", []):
            continent = continents[row["continent_id"]]
            region = regions[row["region_id"]]
            obj = Country(
                code=row["code"],
                label=row["label"],
                continent=continent,
                region=region,
                population=row.get("population", 0),
            )
            countries[row["code"]] = obj
            continent.countries.append(obj)
            region.countries.append(obj)

        # --- Family tree -----------------------------------------------
        # Pass 1: create all LanguageFamily nodes (no parent wiring yet)
        families: Dict[str, LanguageFamily] = {}
        for row in raw.get("families", []):
            obj = LanguageFamily(glottocode=row["glottocode"], label=row["label"])
            families[row["glottocode"]] = obj

        # Pass 2: wire parent / children relationships
        for row in raw.get("families", []):
            parent_gc = row.get("parent_glottocode")
            if parent_gc and parent_gc in families:
                child = families[row["glottocode"]]
                parent = families[parent_gc]
                child.parent = parent
                parent.children.append(child)

        # --- Languages -------------------------------------------------
        languages_list: list[Language] = []
        for row in raw.get("languages", []):
            family_gc = row.get("family_glottocode")
            family = families.get(family_gc) if family_gc else None
            lang_countries = [
                countries[c] for c in row.get("country_codes", []) if c in countries
            ]
            obj = Language(
                part3=row["part3"],
                label=row["label"],
                scope=row["scope"],
                countries=lang_countries,
                family=family,
                part1=row.get("part1"),
                speaker_count=row.get("speaker_count", 0),
                glottocode=row.get("glottocode"),
            )
            # Back-wire countries -> languages
            for country in lang_countries:
                country._language_ref.append(obj)
            # Back-wire family node -> languages
            if family is not None:
                family.languages.append(obj)
            languages_list.append(obj)

        languages_map: dict[str, Language] = {l.part3: l for l in languages_list}

        # --- Official language status (CLDR) ------------------------------
        _STATUS_ATTR = {
            "official":          "_official_languages_ref",
            "official_regional": "_official_regional_languages_ref",
            "de_facto_official": "_de_facto_official_languages_ref",
        }
        for row in raw.get("country_official_languages", []):
            country = countries.get(row["country_code"])
            lang = languages_map.get(row["language_code"])
            attr = _STATUS_ATTR.get(row.get("status", ""))
            if country is None or lang is None or attr is None:
                continue
            getattr(country, attr).append(lang)

        # --- SpeakerCounts ------------------------------------------------
        speaker_counts_list: list[SpeakerCount] = []
        for row in raw.get("country_language_speakers", []):
            country = countries.get(row["country_code"])
            lang = languages_map.get(row["language_code"])
            if country is None or lang is None:
                continue
            sc = SpeakerCount(
                country=country,
                language=lang,
                speaker_count=row.get("speaker_count", 0),
                speaker_fraction=row.get("speaker_fraction", 0.0),
                source=row.get("source", ""),
            )
            country._speaker_count_ref.append(sc)
            lang._speaker_count_ref.append(sc)
            speaker_counts_list.append(sc)

        return (
            ContinentCollection(list(continents.values())),
            RegionCollection(list(regions.values())),
            CountryCollection(list(countries.values())),
            FamilyCollection(list(families.values())),
            LanguageCollection(languages_list),
            SpeakerCountCollection(speaker_counts_list),
        )

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"LanguagesOfTheWorld("
            f"languages={len(self.languages)}, "
            f"countries={len(self.countries)}, "
            f"continents={len(self.continents)}, "
            f"speaker_counts={len(self.speaker_counts)})"
        )
