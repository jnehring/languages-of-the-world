"""Stable record identifiers for annotation CSV rows."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def _hash_key(parts: list[str]) -> str:
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def continent_id(row: Mapping[str, Any]) -> str:
    return f"continent:{row['id']}"


def region_id(row: Mapping[str, Any]) -> str:
    return f"region:{row['id']}"


def country_id(row: Mapping[str, Any]) -> str:
    return f"country:{row['code']}"


def family_id(row: Mapping[str, Any]) -> str:
    return f"family:{row['glottocode']}"


def language_id(row: Mapping[str, Any]) -> str:
    return f"language:{row['part3']}"


def script_id(row: Mapping[str, Any]) -> str:
    return f"script:{row['code']}"


def language_script_id(row: Mapping[str, Any]) -> str:
    return f"lang_script:{row['language_part3']}:{row['script_code']}"


def country_speaker_id(row: Mapping[str, Any]) -> str:
    return (
        f"speakers:{row['country_code']}:{row['language_code']}:{row['source']}"
    )


def official_language_id(row: Mapping[str, Any]) -> str:
    return (
        f"official:{row['country_code']}:{row['language_code']}:{row['status']}"
    )


def language_name_id(row: Mapping[str, Any]) -> str:
    script = row.get("script") or ""
    return (
        f"name:{row['language_part3']}:{row['name']}:{row['in_language_bcp47']}:{script}"
    )


def raw_cldr_id(row: Mapping[str, Any]) -> str:
    return f"raw_cldr:{row['territory']}:{row.get('iso639_3', '')}:{row['language_tag']}"


def raw_cia_id(row: Mapping[str, Any]) -> str:
    return f"raw_cia:{row['country_code']}:{row.get('iso639_3', '')}:{row['language_name']}"


def raw_linguameta_speaker_id(row: Mapping[str, Any]) -> str:
    return f"raw_lm_spk:{row['country_code']}:{row['iso639_3']}"


def raw_linguameta_name_id(row: Mapping[str, Any]) -> str:
    script = row.get("script") or ""
    return (
        f"raw_lm_name:{row['language_part3']}:{row['name']}:"
        f"{row['in_language_bcp47']}:{script}"
    )


def raw_linguameta_script_id(row: Mapping[str, Any]) -> str:
    return f"raw_lm_script:{row['language_part3']}:{row['script_code']}"


def raw_wikidata_id(row: Mapping[str, Any]) -> str:
    return f"raw_wd:{row['qid']}"


def raw_scraper_id(row: Mapping[str, Any]) -> str:
    return f"raw_scraper:{row['country_code']}:{row['iso639_3']}"


ID_FN_BY_TABLE = {
    "continents": continent_id,
    "regions": region_id,
    "countries": country_id,
    "families": family_id,
    "languages": language_id,
    "scripts": script_id,
    "language_scripts": language_script_id,
    "country_speakers": country_speaker_id,
    "official_languages": official_language_id,
    "language_names": language_name_id,
    "raw_cldr_speakers": raw_cldr_id,
    "raw_cia_speakers": raw_cia_id,
    "raw_linguameta_speakers": raw_linguameta_speaker_id,
    "raw_linguameta_names": raw_linguameta_name_id,
    "raw_linguameta_scripts": raw_linguameta_script_id,
    "raw_wikidata_speakers": raw_wikidata_id,
    "raw_scraper_speakers": raw_scraper_id,
}


def add_record_id(table: str, row: dict[str, Any]) -> dict[str, Any]:
    fn = ID_FN_BY_TABLE[table]
    out = dict(row)
    out["record_id"] = fn(row)
    return out


def other_sources_json(sources: list[dict[str, Any]]) -> str:
    return json.dumps(sources, ensure_ascii=False, sort_keys=True)
