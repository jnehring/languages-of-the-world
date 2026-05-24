"""
Build-time data pipeline.

Run once before packaging:

    python -m low.bootstrap

Pulls data from:
  - SIL International ISO 639-3 TSV  (languages, ISO codes, scope)
  - UN M49 CSV                        (continents, regions, countries)
  - Google Research LinguaMeta TSV    (speaker counts + country associations)
  - Glottolog CLDF                    (full language family tree)
  - Unicode CLDR supplementalData     (per-country language speaker percentages)
  - CIA World Factbook via factbook.json (per-country language data)
  - Wikidata SPARQL                   (global speaker counts via P1098)

Writes the result to src/low/data/low_db.json.
Raw per-source speaker data is stored in src/low/data/sources/.
"""
from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Remote source URLs
# ---------------------------------------------------------------------------
_SIL_TSV = "https://iso639-3.sil.org/sites/iso639-3/files/downloads/iso-639-3.tab"
_UN_M49_CSV = (
    "https://raw.githubusercontent.com/lukes/ISO-3166-Countries-with-Regional-Codes"
    "/master/all/all.csv"
)
_LINGUAMETA_TSV = (
    "https://raw.githubusercontent.com/google-research/url-nlp"
    "/main/linguameta/linguameta.tsv"
)
# Per-language JSON files in this directory carry per-country speaker counts
# under language_script_locale[].speaker_data.number_of_speakers.
_LINGUAMETA_TREE_API = (
    "https://api.github.com/repos/google-research/url-nlp/git/trees/main?recursive=1"
)
_LINGUAMETA_RAW_BASE = (
    "https://raw.githubusercontent.com/google-research/url-nlp/main/"
)
_GLOTTOLOG_LANGUAGES_CSV = (
    "https://raw.githubusercontent.com/glottolog/glottolog-cldf"
    "/master/cldf/languages.csv"
)
_GLOTTOLOG_VALUES_CSV = (
    "https://raw.githubusercontent.com/glottolog/glottolog-cldf"
    "/master/cldf/values.csv"
)
_CLDR_SUPPLEMENTAL = (
    "https://raw.githubusercontent.com/unicode-org/cldr"
    "/main/common/supplemental/supplementalData.xml"
)
# Single API call that returns every file path in the repo tree.
# Subsequent country fetches hit raw.githubusercontent.com (no API rate limit).
_FACTBOOK_TREE_API = (
    "https://api.github.com/repos/factbook/factbook.json/git/trees/master?recursive=1"
)
_FACTBOOK_RAW_BASE = "https://raw.githubusercontent.com/factbook/factbook.json/master/"

# Directories that don't contain individual country data files
_FACTBOOK_SKIP_DIRS = {"_layouts", ".github", "oceans", "polar", "world"}

_WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
# All languages (Q34770 and subclasses) with ISO codes and P1098 speaker counts.
# Languages without a speaker count are excluded to keep the response small.
_WIKIDATA_SPARQL_QUERY = """
SELECT ?language ?languageLabel ?iso639_1 ?iso639_3 ?glottolog ?speakers
WHERE {
  ?language wdt:P31/wdt:P279* wd:Q34770.
  ?language wdt:P1098 ?speakers.
  OPTIONAL { ?language wdt:P218 ?iso639_1. }
  OPTIONAL { ?language wdt:P220 ?iso639_3. }
  OPTIONAL { ?language wdt:P1394 ?glottolog. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": "low-bootstrap/0.1 (+https://github.com/low)"})
    with urlopen(req, timeout=60) as resp:
        raw = resp.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    return raw.decode("utf-8")


def _normalize(s: str) -> str:
    return unicodedata.normalize("NFC", s.strip())


# ---------------------------------------------------------------------------
# Source parsers
# ---------------------------------------------------------------------------

def _parse_sil_languages(tsv_text: str) -> Dict[str, Dict[str, Any]]:
    """Return {part3: {part1, label, scope}} from the SIL ISO 639-3 TSV."""
    reader = csv.DictReader(io.StringIO(tsv_text), delimiter="\t")
    langs: Dict[str, Dict[str, Any]] = {}
    for row in reader:
        p3 = _normalize(row.get("Id", ""))
        if not p3:
            continue
        langs[p3] = {
            "part3": p3,
            "part1": _normalize(row.get("Part1", "")) or None,
            "label": _normalize(row.get("Ref_Name", "") or row.get("Print_Name", "")),
            "scope": _normalize(row.get("Scope", "I")),
        }
    return langs


def _parse_linguameta(tsv_text: str) -> Dict[str, Dict[str, Any]]:
    """
    Parse LinguaMeta TSV and return {iso_639_3: {speaker_count, country_codes}}.

    Relevant columns:
      iso_639_3_code               — ISO 639-3 primary key
      estimated_number_of_speakers — total speakers (may be empty)
      locales                      — comma-separated ISO 3166-1 alpha-2 codes
    """
    reader = csv.DictReader(io.StringIO(tsv_text), delimiter="\t")
    result: Dict[str, Dict[str, Any]] = {}

    for row in reader:
        p3 = _normalize(row.get("iso_639_3_code", ""))
        if not p3:
            continue

        raw_count = _normalize(row.get("estimated_number_of_speakers", ""))
        try:
            speaker_count = int(raw_count) if raw_count else 0
        except ValueError:
            speaker_count = 0

        raw_locales = _normalize(row.get("locales", ""))
        country_codes: List[str] = []
        if raw_locales:
            for token in raw_locales.split(","):
                code = token.strip().upper()
                if len(code) == 2 and code.isalpha():
                    country_codes.append(code)

        if p3 in result:
            existing = result[p3]
            existing["speaker_count"] = max(existing["speaker_count"], speaker_count)
            existing["country_codes"] = list(
                dict.fromkeys(existing["country_codes"] + country_codes)
            )
        else:
            result[p3] = {
                "speaker_count": speaker_count,
                "country_codes": country_codes,
            }

    return result


def _parse_glottolog(languages_text: str, values_text: str):
    """
    Parse Glottolog CLDF data and return:

    families : {glottocode: {"glottocode", "label", "parent_glottocode"}}
        All family-level nodes from languages.csv.

    iso_to_glottocode : {iso_639_3: glottocode}
        Language-level nodes that carry an ISO 639-3 code.

    lang_to_parent : {glottocode: immediate_parent_glottocode}
        For language (and dialect) nodes, derived from the classification path.
        The classification value is a slash-separated ancestor chain where
        the last element is the immediate parent.

    glottocode_to_aes : {glottocode: aes_label}
        Glottolog Agglomerated Endangerment Status per language node, e.g.
        "not_endangered", "threatened", "shifting", "moribund",
        "nearly_extinct", "extinct".
    """
    # ---- languages.csv ------------------------------------------------
    lang_reader = csv.DictReader(io.StringIO(languages_text))
    families: Dict[str, Dict[str, Any]] = {}
    iso_to_glottocode: Dict[str, str] = {}

    for row in lang_reader:
        glottocode = _normalize(row.get("ID", ""))
        level = _normalize(row.get("Level", ""))
        name = _normalize(row.get("Name", ""))
        if not glottocode or not level:
            continue

        if level == "family":
            families[glottocode] = {
                "glottocode": glottocode,
                "label": name,
                "parent_glottocode": None,
            }
        elif level == "language":
            iso = _normalize(row.get("ISO639P3code", ""))
            if iso:
                iso_to_glottocode[iso] = glottocode

    # ---- values.csv — classification parameter ------------------------
    # The classification value is a slash-separated path from root down to
    # the node's PARENT (the node itself is not included in the path).
    # Example: "indo1319/clas1257/germ1287/.../glob1243"  → parent = glob1243
    val_reader = csv.DictReader(io.StringIO(values_text))
    lang_to_parent: Dict[str, str] = {}
    glottocode_to_aes: Dict[str, str] = {}

    for row in val_reader:
        param = _normalize(row.get("Parameter_ID", ""))
        glottocode = _normalize(row.get("Language_ID", ""))
        if not glottocode:
            continue

        if param == "classification":
            path = _normalize(row.get("Value", ""))
            if not path:
                continue
            parent_gc = path.split("/")[-1]
            if glottocode in families:
                families[glottocode]["parent_glottocode"] = parent_gc
            else:
                lang_to_parent[glottocode] = parent_gc
        elif param == "aes":
            # Code_ID has the form "aes-not_endangered"; strip the prefix.
            code_id = _normalize(row.get("Code_ID", ""))
            if code_id.startswith("aes-"):
                glottocode_to_aes[glottocode] = code_id[len("aes-"):]

    return families, iso_to_glottocode, lang_to_parent, glottocode_to_aes


def _parse_un_m49(csv_text: str):
    """
    Return (continents, regions, countries) dicts from UN M49 CSV.

    Columns (lukes/ISO-3166-Countries-with-Regional-Codes):
      name, alpha-2, region, sub-region, region-code, sub-region-code
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    continents: Dict[str, Dict[str, str]] = {}
    regions: Dict[str, Dict[str, str]] = {}
    countries: Dict[str, Dict[str, str]] = {}

    for row in reader:
        alpha2 = _normalize(row.get("alpha-2", ""))
        if not alpha2 or len(alpha2) != 2:
            continue

        cont_id = _normalize(row.get("region-code", "")).zfill(3)
        cont_label = _normalize(row.get("region", ""))

        reg_id = _normalize(row.get("sub-region-code", "")).zfill(3)
        reg_label = _normalize(row.get("sub-region", ""))
        if not reg_id or reg_id == "000":
            reg_id = _normalize(row.get("intermediate-region-code", "")).zfill(3)
            reg_label = _normalize(row.get("intermediate-region", ""))

        country_label = _normalize(row.get("name", ""))

        if not cont_id or cont_id == "000" or not cont_label:
            continue
        if not reg_id or reg_id == "000" or not reg_label:
            reg_id = cont_id
            reg_label = cont_label

        if cont_id not in continents:
            continents[cont_id] = {"id": cont_id, "label": cont_label}
        if reg_id not in regions:
            regions[reg_id] = {
                "id": reg_id,
                "label": reg_label,
                "continent_id": cont_id,
            }
        countries[alpha2] = {
            "code": alpha2,
            "label": country_label,
            "continent_id": cont_id,
            "region_id": reg_id,
        }

    return continents, regions, countries


# ---------------------------------------------------------------------------
# Speaker data sources
# ---------------------------------------------------------------------------

def _parse_cldr_speakers(
    xml_text: str,
    iso1_to_part3: Dict[str, str],
    known_country_codes: set,
    known_part3: set,
):
    """
    Parse CLDR supplementalData.xml.

    Returns (records, territory_populations) where:
      records               List[dict] — per-territory language population entries
      territory_populations Dict[str, int] — {ISO alpha-2: population}

    Each record:
        territory          ISO 3166-1 alpha-2 country code
        language_tag       BCP 47 tag as given in CLDR (e.g. "de", "zh-Hans")
        iso639_3           resolved ISO 639-3 code (or null)
        population_percent float  percentage of territory speakers
        territory_population  int
        speaker_count      int  = population * percent / 100
    """
    root = ET.fromstring(xml_text)
    territory_info = root.find(".//territoryInfo")
    if territory_info is None:
        return []

    records: List[Dict[str, Any]] = []
    territory_populations: Dict[str, int] = {}

    for territory in territory_info.findall("territory"):
        country_code = territory.get("type", "")
        if len(country_code) != 2 or country_code not in known_country_codes:
            continue

        try:
            population = int(float(territory.get("population", "0")))
        except (ValueError, TypeError):
            population = 0

        territory_populations[country_code] = population

        for lang_pop in territory.findall("languagePopulation"):
            lang_tag = lang_pop.get("type", "")
            try:
                pct = float(lang_pop.get("populationPercent", "0"))
            except (ValueError, TypeError):
                pct = 0.0

            # Resolve BCP 47 tag → ISO 639-3
            base = lang_tag.split("-")[0].split("_")[0].lower()
            if len(base) == 2:
                part3 = iso1_to_part3.get(base)
            elif len(base) == 3 and base in known_part3:
                part3 = base
            else:
                part3 = None

            records.append(
                {
                    "territory": country_code,
                    "language_tag": lang_tag,
                    "iso639_3": part3,
                    "official_status": lang_pop.get("officialStatus"),
                    "population_percent": round(pct, 4),
                    "territory_population": population,
                    "speaker_count": int(population * pct / 100) if population else 0,
                }
            )

    return records, territory_populations


def _fetch_factbook_country(path: str) -> Optional[Dict[str, Any]]:
    """Fetch one factbook.json country file and return parsed JSON or None."""
    try:
        text = _fetch_text(_FACTBOOK_RAW_BASE + path)
        return json.loads(text)
    except Exception:
        return None


def _parse_cia_speakers(
    known_country_labels: Dict[str, str],
    known_part3: set,
    label_to_part3: Dict[str, str],
) -> List[Dict[str, Any]]:
    """
    Fetch CIA World Factbook data via factbook.json and return per-country
    language records.

    known_country_labels : {label_lower: ISO_alpha2}
    label_to_part3       : {language_label_lower: part3}

    Each record:
        country_code       ISO 3166-1 alpha-2
        country_name       human-readable name as in factbook
        language_name      as given in factbook
        iso639_3           resolved ISO 639-3 code (or null)
        percent            float or null
        country_population int
        speaker_count      int (0 when population or percent unavailable)
    """
    print("  Fetching factbook.json file tree…")
    try:
        tree_text = _fetch_text(_FACTBOOK_TREE_API)
        tree_data: Dict[str, Any] = json.loads(tree_text)
    except Exception as exc:
        print(f"  WARNING: Could not fetch factbook tree: {exc}")
        return []

    # Keep only top-level directory/*.json files that represent countries
    paths: List[tuple] = []
    for item in tree_data.get("tree", []):
        p = item.get("path", "")
        if item.get("type") != "blob" or not p.endswith(".json"):
            continue
        parts = p.split("/")
        if len(parts) != 2:
            continue
        region_dir = parts[0]
        if region_dir.startswith("_") or region_dir in _FACTBOOK_SKIP_DIRS:
            continue
        paths.append((parts[1].removesuffix(".json"), p))

    print(f"  Fetching {len(paths)} factbook country files (parallel)…")

    # Parallel fetch
    fetched: List[tuple] = []
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(_fetch_factbook_country, p): (fb, p) for fb, p in paths}
        done = 0
        for fut in as_completed(futures):
            done += 1
            if done % 50 == 0:
                print(f"    {done}/{len(paths)}…")
            fb_code, path = futures[fut]
            data = fut.result()
            if data:
                fetched.append((fb_code, data))

    # Population regex: "84,119,100 (2023 est.)" → int
    _pop_re = re.compile(r"[\d,]+")

    # Percent regex in language text: "German 88.6%" → ("German", 88.6)
    _lang_pct_re = re.compile(r"([A-Za-zÀ-ɏ\s\-']+?)\s+([\d.]+)%")

    records: List[Dict[str, Any]] = []

    for _fb_code, data in fetched:
        # --- Country name → ISO 3166-1 alpha-2 ---
        gov = data.get("Government", {})
        country_name_section = gov.get("Country name", {})
        short_form = country_name_section.get("conventional short form", {})
        country_name = short_form.get("text", "") if isinstance(short_form, dict) else ""
        if not country_name:
            # Some files use string values directly
            for _key in ("conventional short form", "local short form"):
                val = country_name_section.get(_key, "")
                if isinstance(val, str) and val:
                    country_name = val
                    break

        country_code = known_country_labels.get(country_name.strip().lower())
        if not country_code:
            # Try partial match on the first word
            first_word = country_name.strip().lower().split()[0] if country_name.strip() else ""
            for lbl, code in known_country_labels.items():
                if first_word and lbl.startswith(first_word):
                    country_code = code
                    break
        if not country_code:
            continue

        # --- Population ---
        people = data.get("People and Society", {})
        pop_text = ""
        pop_section = people.get("Population", {})
        if isinstance(pop_section, dict):
            pop_text = pop_section.get("total", pop_section.get("text", ""))
            if isinstance(pop_text, int):
                population = pop_text
            else:
                m = _pop_re.search(str(pop_text))
                population = int(m.group().replace(",", "")) if m else 0
        else:
            population = 0

        # --- Languages ---
        lang_section = people.get("Languages", {})
        if not isinstance(lang_section, dict):
            continue

        # Structured: {"language": [{"name": "...", "percent": 88.6}]}
        lang_list = lang_section.get("language", [])
        if lang_list and isinstance(lang_list, list):
            for item in lang_list:
                if not isinstance(item, dict):
                    continue
                lang_name = item.get("name", "").strip()
                pct = item.get("percent")
                try:
                    pct_f = float(pct) if pct is not None else None
                except (ValueError, TypeError):
                    pct_f = None

                part3 = label_to_part3.get(lang_name.lower())
                speaker_count = int(population * pct_f / 100) if population and pct_f else 0

                records.append(
                    {
                        "country_code": country_code,
                        "country_name": country_name,
                        "language_name": lang_name,
                        "iso639_3": part3,
                        "percent": pct_f,
                        "country_population": population,
                        "speaker_count": speaker_count,
                    }
                )
        else:
            # Text-only: "German (official) 88.6%, Turkish 2.3% ..."
            lang_text = lang_section.get("text", "")
            for m in _lang_pct_re.finditer(lang_text):
                lang_name = m.group(1).strip().rstrip("(")
                pct_f = float(m.group(2))
                part3 = label_to_part3.get(lang_name.lower())
                speaker_count = int(population * pct_f / 100) if population else 0
                records.append(
                    {
                        "country_code": country_code,
                        "country_name": country_name,
                        "language_name": lang_name,
                        "iso639_3": part3,
                        "percent": pct_f,
                        "country_population": population,
                        "speaker_count": speaker_count,
                    }
                )

    return records


def _fetch_linguameta_country(path: str) -> Optional[Dict[str, Any]]:
    """Fetch one LinguaMeta per-language JSON file or None on error."""
    try:
        text = _fetch_text(_LINGUAMETA_RAW_BASE + path)
        return json.loads(text)
    except Exception:
        return None


def _parse_linguameta_per_language(
    known_country_codes: set,
    known_part3: set,
    iso1_to_part3: Dict[str, str],
):
    """
    Fetch every LinguaMeta per-language JSON file once and extract two record sets:

    speaker_records: per-(country, language) speaker counts from
        language_script_locale[].speaker_data.number_of_speakers

    name_records: canonical names for each language in other languages from
        name_data[] (filtered to is_canonical=True). Each record:
            language_part3      ISO 639-3 of the language being named
            name                the name itself
            in_language_bcp47   BCP 47 of the language the name is expressed in
            in_language_part3   resolved ISO 639-3 (or null)
            script              ISO 15924 code (or null)
            source              originating source string (e.g. "CLDR")
    """
    print("  Fetching LinguaMeta file tree…")
    try:
        tree_text = _fetch_text(_LINGUAMETA_TREE_API)
        tree_data: Dict[str, Any] = json.loads(tree_text)
    except Exception as exc:
        print(f"  WARNING: Could not fetch LinguaMeta tree: {exc}")
        return []

    paths: List[str] = []
    for item in tree_data.get("tree", []):
        p = item.get("path", "")
        if item.get("type") != "blob":
            continue
        if not p.startswith("linguameta/data/") or not p.endswith(".json"):
            continue
        paths.append(p)

    print(f"  Fetching {len(paths)} LinguaMeta language files (parallel)…")

    fetched: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(_fetch_linguameta_country, p): p for p in paths}
        done = 0
        for fut in as_completed(futures):
            done += 1
            if done % 500 == 0:
                print(f"    {done}/{len(paths)}…")
            data = fut.result()
            if data:
                fetched.append(data)

    speaker_records: List[Dict[str, Any]] = []
    name_records: List[Dict[str, Any]] = []

    for data in fetched:
        p3 = _normalize(data.get("iso_639_3_code", ""))
        if not p3 or p3 not in known_part3:
            continue

        # --- Per-country speaker counts ---
        for entry in data.get("language_script_locale", []) or []:
            locale = entry.get("locale") or {}
            country_code = _normalize(locale.get("iso_3166_code", "")).upper()
            if len(country_code) != 2 or country_code not in known_country_codes:
                continue

            speaker_data = entry.get("speaker_data") or {}
            raw_count = speaker_data.get("number_of_speakers")
            try:
                speaker_count = int(raw_count) if raw_count is not None else 0
            except (ValueError, TypeError):
                speaker_count = 0
            if speaker_count <= 0:
                continue

            official = entry.get("official_status") or {}
            speaker_records.append({
                "country_code": country_code,
                "iso639_3": p3,
                "speaker_count": speaker_count,
                "has_official_status": official.get("has_official_status"),
            })

        # --- Language names (canonical only) ---
        for entry in data.get("name_data", []) or []:
            if not entry.get("is_canonical"):
                continue
            name = _normalize(entry.get("name", ""))
            if not name:
                continue
            in_bcp47 = _normalize(entry.get("bcp_47_code", "")).lower()
            if not in_bcp47:
                continue

            base = in_bcp47.split("-")[0].split("_")[0]
            in_part3: Optional[str] = None
            if len(base) == 2 and base in iso1_to_part3:
                in_part3 = iso1_to_part3[base]
            elif len(base) == 3 and base in known_part3:
                in_part3 = base

            script = _normalize(entry.get("iso_15924_code", "")) or None
            name_records.append({
                "language_part3": p3,
                "name": name,
                "in_language_bcp47": in_bcp47,
                "in_language_part3": in_part3,
                "script": script,
                "source": _normalize(entry.get("source", "")) or None,
            })

    return speaker_records, name_records


def _fetch_wikidata_speakers(
    iso1_to_part3: Dict[str, str],
    known_part3: set,
) -> List[Dict[str, Any]]:
    """
    Query Wikidata SPARQL for global speaker counts (P1098).

    Returns a list of raw records, one per Wikidata binding:
        qid              Wikidata entity ID (e.g. "Q150")
        label            English label
        iso639_1         2-letter code (or null)
        iso639_3         3-letter code (or null)
        glottolog        Glottolog code (or null)
        speaker_count    int (P1098)
        resolved_part3   ISO 639-3 we mapped this row to (or null)
    """
    from urllib.parse import urlencode

    url = _WIKIDATA_SPARQL_ENDPOINT + "?" + urlencode(
        {"query": _WIKIDATA_SPARQL_QUERY, "format": "json"}
    )
    req = Request(url, headers={
        "User-Agent": "low-bootstrap/0.1 (+https://github.com/low)",
        "Accept": "application/sparql-results+json",
    })
    with urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    records: List[Dict[str, Any]] = []
    for binding in payload.get("results", {}).get("bindings", []):
        def _val(key: str) -> Optional[str]:
            v = binding.get(key)
            return _normalize(v["value"]) if v and v.get("value") else None

        qid_uri = _val("language") or ""
        qid = qid_uri.rsplit("/", 1)[-1] if qid_uri else None

        raw_speakers = _val("speakers")
        try:
            speaker_count = int(float(raw_speakers)) if raw_speakers else 0
        except ValueError:
            speaker_count = 0

        iso1 = _val("iso639_1")
        iso3 = _val("iso639_3")

        resolved_part3: Optional[str] = None
        if iso3 and iso3 in known_part3:
            resolved_part3 = iso3
        elif iso1 and iso1.lower() in iso1_to_part3:
            resolved_part3 = iso1_to_part3[iso1.lower()]

        records.append({
            "qid": qid,
            "label": _val("languageLabel"),
            "iso639_1": iso1,
            "iso639_3": iso3,
            "glottolog": _val("glottolog"),
            "speaker_count": speaker_count,
            "resolved_part3": resolved_part3,
        })

    return records


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_db(output_path: Optional[Path] = None) -> Path:
    """Pull all sources, merge, and write low_db.json."""
    if output_path is None:
        output_path = Path(__file__).parent / "data" / "low_db.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sources_dir = output_path.parent / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)

    print("Fetching SIL ISO 639-3 table…")
    sil_langs = _parse_sil_languages(_fetch_text(_SIL_TSV))

    print("Fetching UN M49 country/region table…")
    raw_conts, raw_regions, raw_countries = _parse_un_m49(_fetch_text(_UN_M49_CSV))

    print("Fetching LinguaMeta speaker & country data…")
    linguameta = _parse_linguameta(_fetch_text(_LINGUAMETA_TSV))

    print("Fetching Glottolog family tree (languages.csv)…")
    glottolog_langs_text = _fetch_text(_GLOTTOLOG_LANGUAGES_CSV)
    print("Fetching Glottolog family tree (values.csv)…")
    glottolog_vals_text = _fetch_text(_GLOTTOLOG_VALUES_CSV)
    glottolog_families, iso_to_glottocode, lang_to_parent, glottocode_to_aes = _parse_glottolog(
        glottolog_langs_text, glottolog_vals_text
    )

    known_country_codes = set(raw_countries.keys())
    known_family_glottocodes = set(glottolog_families.keys())

    languages: List[Dict[str, Any]] = []
    for p3, lang in sil_langs.items():
        lm = linguameta.get(p3, {})

        # Resolve immediate family parent via Glottolog:
        # 1. Look up this language's glottocode via ISO 639-3
        # 2. Get its direct parent from the classification path
        # 3. Walk up until we land on a node that exists in our families dict
        #    (some language parents are themselves language nodes; we skip those)
        lang_glottocode = iso_to_glottocode.get(p3)
        family_glottocode: Optional[str] = None
        if lang_glottocode:
            parent_gc = lang_to_parent.get(lang_glottocode)
            seen: set = set()
            while parent_gc and parent_gc not in known_family_glottocodes:
                if parent_gc in seen:
                    break
                seen.add(parent_gc)
                parent_gc = lang_to_parent.get(parent_gc)
            if parent_gc and parent_gc in known_family_glottocodes:
                family_glottocode = parent_gc

        country_codes = [
            c for c in lm.get("country_codes", []) if c in known_country_codes
        ]

        languages.append(
            {
                "part3": lang["part3"],
                "part1": lang["part1"],
                "label": lang["label"],
                "scope": lang["scope"],
                "speaker_count": lm.get("speaker_count", 0),
                "glottocode": lang_glottocode,
                "family_glottocode": family_glottocode,
                "endangerment": glottocode_to_aes.get(lang_glottocode) if lang_glottocode else None,
                "country_codes": country_codes,
            }
        )

    families_list = sorted(glottolog_families.values(), key=lambda x: x["glottocode"])

    # --- Build lookup tables needed by speaker-count parsers --------------
    iso1_to_part3 = {
        lang["part1"]: lang["part3"]
        for lang in languages
        if lang["part1"]
    }
    known_part3 = {lang["part3"] for lang in languages}
    label_to_part3 = {lang["label"].lower(): lang["part3"] for lang in languages}
    known_country_labels = {
        row["label"].lower(): row["code"] for row in raw_countries.values()
    }

    # --- CLDR speaker data ------------------------------------------------
    print("Fetching Unicode CLDR supplementalData.xml…")
    try:
        cldr_raw, cldr_populations = _parse_cldr_speakers(
            _fetch_text(_CLDR_SUPPLEMENTAL),
            iso1_to_part3,
            known_country_codes,
            known_part3,
        )
    except Exception as exc:
        print(f"  WARNING: CLDR fetch failed: {exc}")
        cldr_raw, cldr_populations = [], {}

    # Stamp territory population onto country records
    for code, pop in cldr_populations.items():
        if code in raw_countries:
            raw_countries[code]["population"] = pop

    cldr_path = sources_dir / "cldr_speakers.json"
    cldr_path.write_text(
        json.dumps(cldr_raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  Stored {len(cldr_raw)} CLDR records → {cldr_path}")

    # --- CIA World Factbook speaker data ----------------------------------
    print("Fetching CIA World Factbook (via factbook.json)…")
    try:
        cia_raw = _parse_cia_speakers(
            known_country_labels,
            known_part3,
            label_to_part3,
        )
    except Exception as exc:
        print(f"  WARNING: CIA fetch failed: {exc}")
        cia_raw = []

    cia_path = sources_dir / "cia_speakers.json"
    cia_path.write_text(
        json.dumps(cia_raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  Stored {len(cia_raw)} CIA records → {cia_path}")

    # --- LinguaMeta per-country speaker counts + canonical names ----------
    print("Fetching LinguaMeta per-language JSON files…")
    try:
        linguameta_country_raw, linguameta_names_raw = _parse_linguameta_per_language(
            known_country_codes, known_part3, iso1_to_part3
        )
    except Exception as exc:
        print(f"  WARNING: LinguaMeta per-language fetch failed: {exc}")
        linguameta_country_raw, linguameta_names_raw = [], []

    linguameta_country_path = sources_dir / "linguameta_speakers.json"
    linguameta_country_path.write_text(
        json.dumps(linguameta_country_raw, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"  Stored {len(linguameta_country_raw)} LinguaMeta per-country records "
        f"→ {linguameta_country_path}"
    )

    linguameta_names_path = sources_dir / "linguameta_names.json"
    linguameta_names_path.write_text(
        json.dumps(linguameta_names_raw, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"  Stored {len(linguameta_names_raw)} LinguaMeta canonical-name records "
        f"→ {linguameta_names_path}"
    )

    # --- Wikidata global speaker counts -----------------------------------
    print("Fetching Wikidata SPARQL speaker counts (P1098)…")
    try:
        wikidata_raw = _fetch_wikidata_speakers(iso1_to_part3, known_part3)
    except Exception as exc:
        print(f"  WARNING: Wikidata fetch failed: {exc}")
        wikidata_raw = []

    wikidata_path = sources_dir / "wikidata_speakers.json"
    wikidata_path.write_text(
        json.dumps(wikidata_raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  Stored {len(wikidata_raw)} Wikidata records → {wikidata_path}")

    # Merge into Language.speaker_count: max across LinguaMeta + Wikidata.
    # Multiple Wikidata rows may map to the same ISO 639-3 (multiple references
    # or sub-varieties); take the highest count per part3.
    wikidata_by_part3: Dict[str, int] = {}
    for rec in wikidata_raw:
        p3 = rec.get("resolved_part3")
        count = rec.get("speaker_count", 0)
        if p3 and count > wikidata_by_part3.get(p3, 0):
            wikidata_by_part3[p3] = count

    wikidata_applied = 0
    for lang in languages:
        wd_count = wikidata_by_part3.get(lang["part3"], 0)
        if wd_count > lang["speaker_count"]:
            lang["speaker_count"] = wd_count
            wikidata_applied += 1
    print(f"  Wikidata raised speaker_count on {wikidata_applied} languages")

    # --- Merge speaker counts into DB entity ------------------------------
    # Deduplicate: one record per (country_code, language_code, source).
    # Use the highest speaker_count when duplicates exist.
    seen_keys: Dict[tuple, Dict[str, Any]] = {}

    for rec in cldr_raw:
        if not rec.get("iso639_3") or not rec.get("territory"):
            continue
        key = (rec["territory"], rec["iso639_3"], "cldr")
        existing = seen_keys.get(key)
        if existing is None or rec["speaker_count"] > existing["speaker_count"]:
            seen_keys[key] = {
                "country_code": rec["territory"],
                "language_code": rec["iso639_3"],
                "speaker_count": rec["speaker_count"],
                "speaker_fraction": round(rec["population_percent"] / 100, 6),
                "source": "cldr",
            }

    for rec in cia_raw:
        if not rec.get("iso639_3") or not rec.get("country_code"):
            continue
        key = (rec["country_code"], rec["iso639_3"], "cia")
        existing = seen_keys.get(key)
        if existing is None or rec["speaker_count"] > existing["speaker_count"]:
            pct = rec.get("percent")
            seen_keys[key] = {
                "country_code": rec["country_code"],
                "language_code": rec["iso639_3"],
                "speaker_count": rec["speaker_count"],
                "speaker_fraction": round(pct / 100, 6) if pct is not None else 0.0,
                "source": "cia",
            }

    # LinguaMeta per-country: derive speaker_fraction from country population
    # when available (population is stamped onto raw_countries from CLDR).
    for rec in linguameta_country_raw:
        cc = rec.get("country_code")
        p3 = rec.get("iso639_3")
        if not cc or not p3:
            continue
        key = (cc, p3, "linguameta")
        existing = seen_keys.get(key)
        if existing is None or rec["speaker_count"] > existing["speaker_count"]:
            pop = raw_countries.get(cc, {}).get("population", 0)
            fraction = round(rec["speaker_count"] / pop, 6) if pop else 0.0
            seen_keys[key] = {
                "country_code": cc,
                "language_code": p3,
                "speaker_count": rec["speaker_count"],
                "speaker_fraction": fraction,
                "source": "linguameta",
            }

    country_language_speakers = sorted(
        seen_keys.values(),
        key=lambda x: (x["country_code"], x["source"], x["language_code"]),
    )

    # --- Official language status (CLDR) ----------------------------------
    _TRACKED_STATUSES = {"official", "official_regional", "de_facto_official"}
    seen_official: set = set()
    country_official_languages: List[Dict[str, Any]] = []
    for rec in cldr_raw:
        status = rec.get("official_status")
        if status not in _TRACKED_STATUSES:
            continue
        if not rec.get("iso639_3") or not rec.get("territory"):
            continue
        key = (rec["territory"], rec["iso639_3"], status)
        if key not in seen_official:
            seen_official.add(key)
            country_official_languages.append(
                {
                    "country_code": rec["territory"],
                    "language_code": rec["iso639_3"],
                    "status": status,
                }
            )
    country_official_languages.sort(
        key=lambda x: (x["country_code"], x["status"], x["language_code"])
    )

    # --- Language names (LinguaMeta) --------------------------------------
    # Dedupe on (language_part3, in_language_bcp47, script). First entry wins.
    seen_names: set = set()
    language_names: List[Dict[str, Any]] = []
    for rec in linguameta_names_raw:
        key = (rec["language_part3"], rec["in_language_bcp47"], rec.get("script"))
        if key in seen_names:
            continue
        seen_names.add(key)
        language_names.append(rec)
    language_names.sort(
        key=lambda x: (x["language_part3"], x["in_language_bcp47"], x.get("script") or "")
    )

    # --- Assemble final DB ------------------------------------------------
    db = {
        "continents": sorted(raw_conts.values(), key=lambda x: x["id"]),
        "regions":    sorted(raw_regions.values(), key=lambda x: x["id"]),
        "countries":  sorted(raw_countries.values(), key=lambda x: x["code"]),
        "families":   families_list,
        "languages":  sorted(languages, key=lambda x: x["label"]),
        "country_language_speakers": country_language_speakers,
        "country_official_languages": country_official_languages,
        "language_names": language_names,
    }

    langs_with_speakers  = sum(1 for l in db["languages"] if l["speaker_count"] > 0)
    langs_with_countries = sum(1 for l in db["languages"] if l["country_codes"])
    langs_with_family    = sum(1 for l in db["languages"] if l["family_glottocode"])
    root_families        = sum(1 for f in db["families"] if not f["parent_glottocode"])
    cldr_entries         = sum(1 for r in country_language_speakers if r["source"] == "cldr")
    cia_entries          = sum(1 for r in country_language_speakers if r["source"] == "cia")
    linguameta_entries   = sum(1 for r in country_language_speakers if r["source"] == "linguameta")
    official_counts      = {s: sum(1 for r in country_official_languages if r["status"] == s)
                            for s in _TRACKED_STATUSES}

    output_path.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Wrote {output_path}\n"
        f"  {len(db['languages'])} languages "
        f"({langs_with_speakers} with speaker counts, "
        f"{langs_with_countries} with country links, "
        f"{langs_with_family} with Glottolog family)\n"
        f"  {len(db['countries'])} countries, "
        f"{len(db['regions'])} regions, "
        f"{len(db['continents'])} continents\n"
        f"  {len(db['families'])} family tree nodes ({root_families} root families)\n"
        f"  {len(country_language_speakers)} country-language speaker records "
        f"({cldr_entries} CLDR, {cia_entries} CIA, {linguameta_entries} LinguaMeta)\n"
        f"  {len(language_names)} canonical language names (LinguaMeta)\n"
        f"  {len(country_official_languages)} official-language entries "
        f"(official: {official_counts['official']}, "
        f"regional: {official_counts['official_regional']}, "
        f"de_facto: {official_counts['de_facto_official']})"
    )
    return output_path


if __name__ == "__main__":
    build_db()
