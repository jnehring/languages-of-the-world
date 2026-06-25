# low - Languages of the World

[![CI](https://github.com/your-org/low/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/low/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

`low` is a lightweight, read-only Python utility that aggregates and normalises seven open linguistic datasets — SIL ISO 639-3, UN M49, LinguaMeta, Glottolog, Unicode CLDR, the CIA World Factbook, and Wikidata — into a connected in-memory object graph. Instead of wrapping data behind traditional repository classes, `low` exposes everything through idiomatic Python sequences, smart multi-key lookups, and direct dot-notation object navigation. `low` contains

- **~7,900 languages** - ISO 639-3 codes, labels, scope (individual / macrolanguage), and optional ISO 639-1 codes
- **Country assignments** - languages linked to the countries where they are spoken
- **247 countries** - ISO 3166-1 alpha-2 codes, population, and back-references to spoken languages
- **5 continents & 17 UN M49 regions** - geographic hierarchy from country up to continent
- **~4,800 Glottolog family nodes** - navigable parent/child tree with 246 root families
- **Endangerment status** - Glottolog Agglomerated Endangerment Scale (AES) per language
- **106 writing systems** - ISO 15924 scripts with primary-script assignment per language
- **Cross-lingual names** - canonical endonyms and exonyms across languages
- **Per-country speaker counts** - from CLDR, CIA World Factbook, LinguaMeta, and optional web-scraped data
- **Global speaker totals** - merged across LinguaMeta and Wikidata
- **Official language status** - nationally official, regionally official, and de facto official languages per country
- **Queryable collections** - polymorphic `.get()`, `.filter()`, and indexed access on every entity type

**Table of contents**

- [low - Languages of the World](#low---languages-of-the-world)
  - [Installation](#installation)
  - [Quick Start](#quick-start)
  - [Examples](#examples)
  - [Entity Model](#entity-model)
    - [Language](#language)
    - [Script](#script)
    - [LanguageName](#languagename)
    - [Country](#country)
    - [SpeakerCount](#speakercount)
    - [Region](#region)
    - [Continent](#continent)
    - [LanguageFamily](#languagefamily)
  - [Collection Interface](#collection-interface)
    - [`.get(query)` - Polymorphic lookup](#getquery---polymorphic-lookup)
    - [`.filter()` (LanguageCollection only)](#filter-languagecollection-only)
    - [`.roots()` (FamilyCollection only)](#roots-familycollection-only)
    - [SpeakerCountCollection (`db.speaker_counts`)](#speakercountcollection-dbspeaker_counts)
    - [ScriptCollection (`db.scripts`)](#scriptcollection-dbscripts)
    - [LanguageNameCollection (`db.language_names`)](#languagenamecollection-dblanguage_names)
  - [Data Provenance](#data-provenance)
    - [SIL International - ISO 639-3](#sil-international---iso-639-3)
    - [UN M49 - ISO-3166-Countries-with-Regional-Codes](#un-m49---iso-3166-countries-with-regional-codes)
    - [Google Research - LinguaMeta](#google-research---linguameta)
    - [Glottolog CLDF](#glottolog-cldf)
    - [Unicode CLDR - supplementalData.xml](#unicode-cldr---supplementaldataxml)
    - [CIA World Factbook - factbook.json](#cia-world-factbook---factbookjson)
    - [Wikidata - SPARQL Query Service](#wikidata---sparql-query-service)
    - [Web-scraped speaker counts (`low-scraper`)](#web-scraped-speaker-counts-low-scraper)
  - [Speaker-count scraper (`low-scraper`)](#speaker-count-scraper-low-scraper)
    - [Install](#install)
    - [Workflow](#workflow)
  - [Regenerating the Database](#regenerating-the-database)
  - [Development](#development)
  - [License](#license)


## Installation

```bash
pip install languages-of-the-world
```

---

## Quick Start

```python
import low

# Initialise the graph (~7900 languages, 247 countries, 4800+ family tree nodes)
db = low.LanguagesOfTheWorld()

# Slice like a list
first_ten = db.languages[:10]
total     = len(db.languages)

# Polymorphic single-key lookup
db.languages.get("rw")          # ISO 639-1 (2-char)  → Kinyarwanda
db.languages.get("kin")         # ISO 639-3 (3-char)  → Kinyarwanda
db.languages.get("Kinyarwanda") # Label (case-insensitive) → Kinyarwanda

# Navigate the object graph with dot notation
lang = db.languages.get("kin")
for country in lang.countries:
    print(f"{country.label} - {country.region.label} ({country.continent.label})")
# Rwanda - Eastern Africa (Africa)
# DR Congo - Eastern Africa (Africa)
# Uganda - Eastern Africa (Africa)

# Country → back-reference to languages
rw = db.countries.get("RW")
for l in rw.languages:
    print(l.label)

# Filter by partial name or minimum speakers
popular = db.languages.filter(min_speakers=50_000_000)
romance = db.languages.filter(label_contains="Portug")

# Glottolog endangerment status
print(db.languages.get("kin").endangerment)   # 'not_endangered'
print(db.languages.get("dlg").endangerment)   # 'moribund'  (Dolgan)
at_risk = [l for l in db.languages
           if l.endangerment in {"nearly_extinct", "moribund"}]

# Walk the Glottolog language family tree
deu = db.languages.get("deu")
node = deu.family
while node:
    print("  " * node.depth + node.label)
    node = node.parent
# Standard German's Glottolog lineage, leaf → root

# All top-level root families
for fam in db.families.roots():
    print(fam.label, f"({len(fam.children)} subgroups)")

# Official language status per country (from CLDR)
ch = db.countries.get("CH")
print([l.label for l in ch.official_languages])
# ['French', 'German', 'Italian', 'Romansh']
print([l.label for l in ch.official_regional_languages])
# e.g. regionally recognised languages
print([l.label for l in ch.de_facto_official_languages])
# e.g. de facto official languages with no formal legal status

# Per-country speaker counts - how many people speak a language in each country
rw = db.countries.get("RW")
print(f"Rwanda population: {rw.population:,}")
for sc in rw.speaker_counts:
    print(f"{sc.language.label}: {sc.speaker_count:,} ({sc.speaker_fraction:.1%}) [{sc.source}]")
# Rwanda population: 13,776,698
# Kinyarwanda: 10,200,000 (74.0%) [cldr]
# French: 300,000 (2.2%) [cldr]
# Kinyarwanda: 9,900,000 (71.8%) [cia]

# Same from the language side
kin = db.languages.get("kin")
for sc in kin.speaker_counts:
    print(f"{sc.country.label}: {sc.speaker_count:,} ({sc.source})")

# Canonical names for a language across other languages
deu = db.languages.get("deu")
print(deu.endonym.name)                       # "Deutsch"
print([n.name for n in deu.names if n.in_language_bcp47 == "fr"])
# ['allemand']

# All known English names for every language
for n in db.language_names.in_language("en")[:5]:
    print(f"{n.language.part3} → {n.name}")

# Query the full SpeakerCount collection directly
db.speaker_counts.for_country("DE")        # all entries for Germany
db.speaker_counts.for_language("deu")      # all entries for German
db.speaker_counts.by_source("cldr")        # all CLDR-sourced entries
db.speaker_counts.by_source("cia")         # all CIA-sourced entries
db.speaker_counts.by_source("linguameta")  # all LinguaMeta-sourced entries
```

---

## Examples

Jupyter notebooks in [`examples/`](examples/) walk through the
full `low` API - from geography and speaker counts to families, scripts, and
names. Install notebook dependencies with:

```bash
pip install "languages-of-the-world[examples]"
```

- **[`01_languages_per_country.ipynb`](examples/01_languages_per_country.ipynb)** - Count languages spoken in each country and map global linguistic diversity as a choropleth and bar chart.
- **[`02_scraper_analysis.ipynb`](examples/02_scraper_analysis.ipynb)** - Track how many `(country, language)` pairs the optional `low-scraper` resolves per scrape round.
- **[`03_endangered_languages_by_continent.ipynb`](examples/03_endangered_languages_by_continent.ipynb)** - Map Glottolog endangerment tiers by continent and highlight countries with the most at-risk languages.
- **[`04_language_families.ipynb`](examples/04_language_families.ipynb)** - Explore the Glottolog family tree: root-family sizes, descendant counts, and a lineage walk for German.
- **[`05_speaker_source_disagreement.ipynb`](examples/05_speaker_source_disagreement.ipynb)** - Compare CLDR, CIA, and LinguaMeta speaker estimates for the same country–language pairs.
- **[`06_official_vs_spoken.ipynb`](examples/06_official_vs_spoken.ipynb)** - Find countries where the most-spoken language is not the legally official one.
- **[`07_endonyms_and_exonyms.ipynb`](examples/07_endonyms_and_exonyms.ipynb)** - Report endonym coverage and build cross-lingual name lookup tables.
- **[`08_scripts_of_the_world.ipynb`](examples/08_scripts_of_the_world.ipynb)** - Chart how ISO 15924 writing systems are distributed across languages and speaker totals.
- **[`09_languages_without_borders.ipynb`](examples/09_languages_without_borders.ipynb)** - Rank languages by how many countries they span and map their geographic spread.
- **[`10_top_languages_by_speakers.ipynb`](examples/10_top_languages_by_speakers.ipynb)** - Rank global speaker totals, explore macrolanguages, and demo `get()` / `filter()`.

---

## Entity Model

```
[Continent] <───1:N─── [Region] <───1:N─── [Country] <───M:N─── [Language] ───1:N─── [LanguageName]
     │                                           │                     │                    │
     └───────────────────1:N────────────────────┘                     └───N:1─── [LanguageFamily]
                                │                                                      │ parent/children
                                └───────────── [SpeakerCount] ─────────────────────────
                                                  (country, language,
                                                   speaker_count, source)
```

### Language

| Property | Type | Source | Description |
|---|---|---|---|
| `part3` | `str` | SIL ISO 639-3 | ISO 639-3 three-letter code - primary key |
| `part1` | `Optional[str]` | SIL ISO 639-3 | ISO 639-1 two-letter code (if assigned) |
| `label` | `str` | SIL ISO 639-3 | Reference name |
| `scope` | `str` | SIL ISO 639-3 | `"I"` Individual · `"M"` Macrolanguage · `"S"` Special |
| `speaker_count` | `int` | LinguaMeta / Wikidata | Estimated total speakers (global), max across sources |
| `countries` | `List[Country]` | LinguaMeta | Countries where the language is spoken |
| `family` | `Optional[LanguageFamily]` | Glottolog | Immediate parent node in the Glottolog tree |
| `glottocode` | `Optional[str]` | Glottolog | Glottolog identifier (e.g. `"kin1248"`) |
| `endangerment` | `Optional[str]` | Glottolog | Agglomerated Endangerment Status (AES). One of `"not_endangered"`, `"threatened"`, `"shifting"`, `"moribund"`, `"nearly_extinct"`, `"extinct"`; `None` if Glottolog has no assessment |
| `speaker_counts` | `List[SpeakerCount]` | CLDR / CIA / LinguaMeta / scraped | Per-country speaker counts for this language |
| `names` | `List[LanguageName]` | LinguaMeta | Canonical names for this language in other languages |
| `scripts` | `List[Script]` | LinguaMeta | Writing systems used for this language (canonical first) |
| `primary_script` | `Optional[Script]` *(property)* | derived | First canonical script, or first script alphabetically |
| `endonym` | `Optional[LanguageName]` *(property)* | LinguaMeta | The name expressed in the language itself, if available |

### Script

A writing system identified by [ISO 15924](https://unicode.org/iso15924/). Sourced from LinguaMeta's `language_script_locale` entries (all distinct script codes per language).

| Property | Type | Source | Description |
|---|---|---|---|
| `code` | `str` | LinguaMeta | ISO 15924 four-letter code (lowercase, e.g. `"deva"`) |
| `label` | `str` | Unicode CLDR | English display name (e.g. `"Devanagari"`) |
| `languages` | `List[Language]` | derived | Languages that use this script |

### LanguageName

A single canonical name for a language, expressed in some (possibly different) language. Sourced from LinguaMeta's `name_data`, filtered to `is_canonical=True`.

| Property | Type | Source | Description |
|---|---|---|---|
| `language` | `Language` | - | The language being named |
| `name` | `str` | LinguaMeta | The name string (e.g. `"Deutsch"`, `"German"`, `"Allemand"`) |
| `in_language_bcp47` | `str` | LinguaMeta | BCP 47 code of the language the name is expressed in |
| `in_language` | `Optional[Language]` | derived | Resolved `Language`, when the BCP 47 base maps to a known ISO 639-3 |
| `script` | `Optional[str]` | LinguaMeta | ISO 15924 script code, when supplied |
| `source` | `Optional[str]` | LinguaMeta | Upstream provenance string (e.g. `"CLDR"`, `"GOOGLE_RESEARCH"`) |
| `is_endonym` | `bool` *(property)* | derived | True when `in_language` is the same as `language` |

### Country

| Property | Type | Source | Description |
|---|---|---|---|
| `code` | `str` | UN M49 | ISO 3166-1 alpha-2 |
| `label` | `str` | UN M49 | Common name |
| `continent` | `Continent` | UN M49 | |
| `region` | `Region` | UN M49 | UN M49 sub-region |
| `population` | `int` | CLDR | Total population (0 if not available) |
| `languages` | `List[Language]` | LinguaMeta | All languages spoken in this country |
| `official_languages` | `List[Language]` | CLDR | Nationally official languages (`officialStatus="official"`) |
| `official_regional_languages` | `List[Language]` | CLDR | Regionally official languages (`officialStatus="official_regional"`) |
| `de_facto_official_languages` | `List[Language]` | CLDR | De facto official languages (`officialStatus="de_facto_official"`) |
| `speaker_counts` | `List[SpeakerCount]` | CLDR / CIA / LinguaMeta / scraped | Per-language speaker counts in this country |

### SpeakerCount

Represents how many speakers of a given language live in a given country,
according to a specific data source. Both `country.speaker_counts` and
`language.speaker_counts` navigate to these objects.

| Property | Type | Source | Description |
|---|---|---|---|
| `country` | `Country` | - | The country |
| `language` | `Language` | - | The language |
| `speaker_count` | `int` | CLDR / CIA / LinguaMeta / scraped | Estimated number of speakers |
| `speaker_fraction` | `float` | CLDR / CIA / LinguaMeta / scraped | Share of country population (0.0–1.0; derived from `Country.population` for LinguaMeta and scraped) |
| `source` | `str` | - | `"cldr"`, `"cia"`, `"linguameta"`, or `"scraped"` |

### Region

| Property | Type | Source | Description |
|---|---|---|---|
| `id` | `str` | UN M49 | UN M49 numeric code |
| `label` | `str` | UN M49 | Sub-region name |
| `continent` | `Continent` | UN M49 | |
| `countries` | `List[Country]` | UN M49 | Back-reference |

### Continent

| Property | Type | Source | Description |
|---|---|---|---|
| `id` | `str` | UN M49 | UN M49 numeric code |
| `label` | `str` | UN M49 | Continent name |
| `countries` | `List[Country]` | UN M49 | Back-reference |

### LanguageFamily

Represents a node in the [Glottolog](https://glottolog.org/) genealogical
classification tree.  Every node - from the deepest sub-branch to a top-level
family like Indo-European - is a `LanguageFamily` instance.

| Property | Type | Source | Description |
|---|---|---|---|
| `glottocode` | `str` | Glottolog | Glottolog identifier (e.g. `"indo1319"`) |
| `label` | `str` | Glottolog | Node name |
| `parent` | `Optional[LanguageFamily]` | Glottolog | Parent node; `None` for root families |
| `children` | `List[LanguageFamily]` | Glottolog | Direct child sub-families |
| `languages` | `List[Language]` | Glottolog | Languages whose immediate Glottolog parent is this node |
| `root` | `LanguageFamily` *(property)* | derived | Walk up to the top-level family |
| `ancestors` | `List[LanguageFamily]` *(property)* | derived | Ordered list parent → root |
| `depth` | `int` *(property)* | derived | Depth in tree (0 = root family) |

## Collection Interface

Every entity collection (`db.languages`, `db.countries`, `db.continents`, `db.regions`, `db.families`, `db.scripts`, `db.speaker_counts`, `db.language_names`) implements the Python sequence protocol:

```python
len(db.languages)        # int
db.languages[0]          # Language
db.languages[:5]         # List[Language]
for lang in db.languages: ...
```

### `.get(query)` - Polymorphic lookup

| Query pattern | Resolves to |
|---|---|
| 2-char string | ISO 639-1 / ISO 3166-1 alpha-2 |
| 3-char string | ISO 639-3 |
| 4-char string (scripts) | ISO 15924 |
| 8-char string (families) | Glottolog code |
| Longer string | Case-insensitive label |

### `.filter()` (LanguageCollection only)

```python
db.languages.filter(label_contains="arabic")
db.languages.filter(min_speakers=1_000_000)
db.languages.filter(label_contains="creole", min_speakers=100_000)
```

### `.roots()` (FamilyCollection only)

```python
db.families.roots()   # List[LanguageFamily] - only top-level families
```

### SpeakerCountCollection (`db.speaker_counts`)

The `SpeakerCount` collection adds three targeted query methods on top of the
standard sequence protocol:

```python
db.speaker_counts.for_country("DE")    # List[SpeakerCount] - all entries for Germany
db.speaker_counts.for_language("deu")  # List[SpeakerCount] - all entries for German
db.speaker_counts.by_source("cldr")        # List[SpeakerCount] - CLDR entries only
db.speaker_counts.by_source("cia")         # List[SpeakerCount] - CIA entries only
db.speaker_counts.by_source("linguameta")  # List[SpeakerCount] - LinguaMeta entries only
db.speaker_counts.by_source("scraped")  # List[SpeakerCount] - web-scraped entries only
```

### ScriptCollection (`db.scripts`)

```python
db.scripts.get("deva")           # Script - by ISO 15924 code
db.scripts.for_language("hin")   # List[Script] - all scripts for Hindi
```

### LanguageNameCollection (`db.language_names`)

Holds every canonical name parsed from LinguaMeta's per-language JSON
(`name_data` rows with `is_canonical=True`), one record per
`(language, in_language_bcp47, script)` triple.

```python
db.language_names.for_language("deu")   # every canonical name of German
db.language_names.in_language("en")     # every language's English canonical name
db.language_names.endonyms()            # one entry per language: its name in itself
```

Each entry resolves to a `Language` via `name.in_language` when the BCP 47 base
maps to a known ISO 639-3; otherwise `in_language` is `None` and only
`in_language_bcp47` is meaningful.

The same data is also reachable through dot navigation on `Country` and `Language`:

```python
db.countries.get("DE").speaker_counts   # identical to for_country("DE")
db.languages.get("deu").speaker_counts  # identical to for_language("deu")
```

## Data Provenance

`low` integrates seven open datasets fetched at build time, plus a committed
web-scraped speaker-count snapshot merged in when present.  The bootstrap pipeline
(`python -m low.bootstrap`) pulls the upstream sources and bakes the result into
`src/low/data/low_db.json`.

### [SIL International - ISO 639-3](https://iso639-3.sil.org/)

**URL:** `https://iso639-3.sil.org/sites/iso639-3/files/downloads/iso-639-3.tab`  
**Licence:** [SIL Usage](https://www.sil.org/iso639-3/download.asp)  
**Fields provided:**

| Field | Column in source |
|---|---|
| `Language.part3` | `Id` |
| `Language.part1` | `Part1` |
| `Language.label` | `Ref_Name` |
| `Language.scope` | `Scope` (`I`/`M`/`S`) |

This TSV is the authoritative source of all ISO 639-3 codes.
Every language in `low` originates here; other sources add extra attributes.

---

### [UN M49 - ISO-3166-Countries-with-Regional-Codes](https://github.com/lukes/ISO-3166-Countries-with-Regional-Codes)

**URL:** `https://raw.githubusercontent.com/lukes/ISO-3166-Countries-with-Regional-Codes/master/all/all.csv`  
**Licence:** [MIT](https://github.com/lukes/ISO-3166-Countries-with-Regional-Codes/blob/master/LICENSE.md)  
**Fields provided:**

| Field | Column in source |
|---|---|
| `Country.code` | `alpha-2` |
| `Country.label` | `name` |
| `Region.id`, `Region.label` | `sub-region-code`, `sub-region` |
| `Continent.id`, `Continent.label` | `region-code`, `region` |

Countries, regions, and continents are entirely built from this CSV.

---

### [Google Research - LinguaMeta](https://github.com/google-research/url-nlp/tree/main/linguameta)

**TSV URL:** `https://raw.githubusercontent.com/google-research/url-nlp/main/linguameta/linguameta.tsv`
**Per-language JSON base:** `https://raw.githubusercontent.com/google-research/url-nlp/main/linguameta/data/<bcp47>.json`
**Licence:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
**Raw output:** `src/low/data/sources/linguameta_speakers.json`, `linguameta_names.json`, `linguameta_scripts.json`
**Fields provided:**

| Field | Source path |
|---|---|
| `Language.speaker_count` | TSV `estimated_number_of_speakers` (merged max with Wikidata) |
| `Language.countries` | TSV `locales` (comma-separated ISO 3166-1 alpha-2) |
| `SpeakerCount.country` | per-language JSON `language_script_locale[].locale.iso_3166_code` |
| `SpeakerCount.language` | per-language JSON `iso_639_3_code` |
| `SpeakerCount.speaker_count` | `language_script_locale[].speaker_data.number_of_speakers` |
| `SpeakerCount.speaker_fraction` | derived as `speaker_count / Country.population` (CLDR-sourced population) |
| `LanguageName.name` | per-language JSON `name_data[].name` (filtered to `is_canonical=true`) |
| `LanguageName.in_language_bcp47` | `name_data[].bcp_47_code` |
| `LanguageName.script` | `name_data[].iso_15924_code` (optional) |
| `LanguageName.source` | `name_data[].source` (e.g. `"CLDR"`, `"GOOGLE_RESEARCH"`) |
| `Script.code` | `language_script_locale[].script.iso_15924_code` |
| `Language.scripts` | all distinct scripts per language from `language_script_locale` |

Script **codes** come from LinguaMeta; English **labels** are resolved from
[Unicode CLDR `en.xml`](#unicode-cldr--supplementaldataxml) at bootstrap time (see below).

The TSV is the authoritative table for the global per-language total
(`estimated_number_of_speakers`, order-of-magnitude rounded). Multiple BCP-47
rows mapping to the same ISO 639-3 code are merged (max speakers, union of
country codes).

The per-language JSON files under `linguameta/data/` are fetched in parallel
(~7 000 files, up to 20 threads) in a single pass that produces three record sets:

- **Per-locale speaker counts** from `language_script_locale[].speaker_data.number_of_speakers` → merged into `SpeakerCount` with `source="linguameta"`.
- **Canonical names** from `name_data[]` (rows with `is_canonical=true`) → `LanguageName` collection. Names are deduplicated on `(language, in_language_bcp47, script)`; the first occurrence wins.
- **Language scripts** from `language_script_locale[].script.iso_15924_code` → distinct `(language, script)` pairs deduplicated across locales; `is_canonical` is true if any locale entry marked the script canonical.

The repo file tree is discovered via a single GitHub trees API call; individual
files come from `raw.githubusercontent.com` (no rate-limit).

---

### [Glottolog CLDF](https://github.com/glottolog/glottolog-cldf)

**Languages CSV:** `https://raw.githubusercontent.com/glottolog/glottolog-cldf/master/cldf/languages.csv`  
**Values CSV:** `https://raw.githubusercontent.com/glottolog/glottolog-cldf/master/cldf/values.csv`  
**Licence:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)  
**Fields provided:**

| Field | Source column |
|---|---|
| `LanguageFamily.glottocode` | `ID` (languages.csv, `Level=family`) |
| `LanguageFamily.label` | `Name` (languages.csv) |
| `LanguageFamily.parent` | Last component of the `classification` path (values.csv) |
| `Language.glottocode` | `ID` (languages.csv, `Level=language`) |
| `Language.family` | Resolved from the language's `classification` path |
| `Language.endangerment` | `Code_ID` of the `aes` parameter (values.csv), with the `aes-` prefix stripped |

The `classification` value is a slash-separated ancestor chain from the root
family down to the node's immediate parent (e.g.
`"indo1319/clas1257/germ1287/nort3152/west2793/high1289/high1286/midd1349/mode1258/uppe1464/glob1243"`).
The bootstrap extracts the last element as the immediate parent, producing the
full navigable tree.  The production database contains ~4 800 family-level nodes
and 246 root families.

### [Unicode CLDR - supplementalData.xml](https://github.com/unicode-org/cldr)

**URL:** `https://raw.githubusercontent.com/unicode-org/cldr/main/common/supplemental/supplementalData.xml`  
**Scripts URL:** `https://raw.githubusercontent.com/unicode-org/cldr/main/common/main/en.xml`  
**Licence:** [Unicode License v3](https://www.unicode.org/license.txt)  
**Raw output:** `src/low/data/sources/cldr_speakers.json`  
**Fields provided:**

| Field | Source element |
|---|---|
| `Country.population` | `territory[@population]` |
| `Country.official_languages` | `languagePopulation[@officialStatus="official"]` |
| `Country.official_regional_languages` | `languagePopulation[@officialStatus="official_regional"]` |
| `Country.de_facto_official_languages` | `languagePopulation[@officialStatus="de_facto_official"]` |
| `SpeakerCount.country` | `<territory type="…">` - ISO 3166-1 alpha-2 |
| `SpeakerCount.language` | `<languagePopulation type="…">` - BCP 47 tag, mapped to ISO 639-3 |
| `SpeakerCount.speaker_count` | `territory[@population]` × `languagePopulation[@populationPercent]` / 100 |
| `SpeakerCount.speaker_fraction` | `languagePopulation[@populationPercent]` / 100 |
| `Script.label` | `en.xml` → `<script type="…">` text (English display name) |

Each `<territory>` element carries the total population and a list of
`<languagePopulation>` children with `populationPercent` and optional
`officialStatus` attributes.  The three official-status lists on `Country`
are built from the `officialStatus` attribute; entries with any other value
(e.g. `official_minority`) or no attribute are omitted from those lists.
Territory population is written directly onto `Country.population`.
BCP 47 language tags are normalised to ISO 639-3 codes using the SIL table
(2-char base → ISO 639-1 → ISO 639-3 mapping; 3-char base used directly).

---

### [CIA World Factbook - factbook.json](https://github.com/factbook/factbook.json)

**Index URL:** `https://raw.githubusercontent.com/factbook/factbook.json/master/index.json`  
**Per-country base:** `https://raw.githubusercontent.com/factbook/factbook.json/master/`  
**Licence:** Public domain (U.S. Government work)  
**Raw output:** `src/low/data/sources/cia_speakers.json`  
**Fields provided:**

| Field | Source path in country JSON |
|---|---|
| `SpeakerCount.country` | `Government › Country name › conventional short form` - matched to ISO alpha-2 by label |
| `SpeakerCount.language` | `People and Society › Languages › language[].name` - matched to ISO 639-3 by label |
| `SpeakerCount.speaker_count` | country population × language `percent` / 100 |
| `SpeakerCount.speaker_fraction` | language `percent` / 100 |

Country files are fetched in parallel (up to 20 threads).  Each file's language
section is parsed as a structured list when available or extracted from free text
via a percentage regex as fallback.  Language names are matched to ISO 639-3
codes against the `Language.label` index.

### [Wikidata - SPARQL Query Service](https://query.wikidata.org/)

**Endpoint:** `https://query.wikidata.org/sparql`
**Licence:** [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)
**Raw output:** `src/low/data/sources/wikidata_speakers.json`
**Fields provided:**

| Field | Source property |
|---|---|
| `Language.speaker_count` | `P1098` (number of speakers, writers, or signers), max with LinguaMeta |

Queries all instances of `wd:Q34770` (language) and its subclasses that carry a
`P1098` value, joined with `P218` (ISO 639-1) and `P220` (ISO 639-3) for code
resolution. Rows resolve to ISO 639-3 directly when present, otherwise via the
2-letter code lookup. When multiple Wikidata items map to the same ISO 639-3
(sub-varieties, alternative references) the highest speaker count wins.
Merged into `Language.speaker_count` as `max(linguameta, wikidata)`.

---

### Web-scraped speaker counts (`low-scraper`)

Unlike the seven upstream datasets above, scraped speaker counts are **not fetched
during bootstrap**.  They are produced offline by the optional `low-scraper` CLI
(web search via [serper.dev](https://serper.dev), page fetch, answer extraction
via **Google Gemini**), committed to the repo, and merged when bootstrap runs.

**Raw output:** `src/low/data/sources/low_scraper_speakers.json`  
**Licence:** derived from web pages retrieved at scrape time (no single upstream licence)  
**Fields provided:**

| Field | Source |
|---|---|
| `SpeakerCount.country` | ISO 3166-1 alpha-2 from the scraped task |
| `SpeakerCount.language` | ISO 639-3 from the scraped task |
| `SpeakerCount.speaker_count` | LLM-extracted integer from aggregated scrape rounds |
| `SpeakerCount.speaker_fraction` | `speaker_count / Country.population` (CLDR-sourced population) |
| `SpeakerCount.source` | always `"scraped"` |

Bootstrap loads `low_scraper_speakers.json` when the file is present and merges
records into `country_language_speakers` with `source="scraped"`, deduplicating
on `(country_code, language_code, source)` and keeping the highest speaker count.
Pairs already covered by CLDR, CIA, or LinguaMeta are not overwritten - scraped
data fills **gaps** where no other source reported a per-country count.

For install, CLI workflow, caching, and release notes, see
[Speaker-count scraper (`low-scraper`)](#speaker-count-scraper-low-scraper) below.

## Speaker-count scraper (`low-scraper`)

The optional scraper fills in **missing per-country speaker counts** - country/language
pairs where `low` knows the language is spoken but has no `SpeakerCount` from CLDR,
CIA, or LinguaMeta.  See [Data Provenance](#web-scraped-speaker-counts-low-scraper)
for how scraped records are stored and merged into `low_db.json`.

### Install

```bash
pip install "languages-of-the-world[scraper]"
cat >> .env <<'EOF'
SERPER_API_KEY=your-serper-key
GEMINI_API_KEY=your-gemini-key
EOF
```

### Workflow

Working files live under `scraper-data/` (gitignored). One command runs search,
scraping, LLM extraction, and aggregation for multiple rounds:

```bash
low-scraper run --rounds 3          # → round1_results.csv … speakers.json
low-scraper import                  # → src/low/data/sources/low_scraper_speakers.json
git add src/low/data/sources/low_scraper_speakers.json
git commit -m "Update scraped speaker counts"
python -m low.bootstrap             # optional local preview → low_db.json
```

**PyPI releases:** commit `low_scraper_speakers.json` to the repo. The release
workflow runs `python -m low.bootstrap` and merges this file into `low_db.json` -
it does **not** run the scraper or call Serper/Gemini (too expensive for CI).

Each round retries **UNKNOWN** pairs with fresh search results. Serper and Gemini
responses are cached under `scraper-data/.cache` (use `--no-cache` to bypass).

`low-scraper status` shows completed rounds, resolved counts, and cache stats.

Legacy loom CSV workflow (`scrape` / `aggregate`) remains for old `promptsN_results_*.csv`
files. See [`examples/02_scraper_analysis.ipynb`](examples/02_scraper_analysis.ipynb) for
per-round resolution statistics.

---

## Regenerating the Database

The baked JSON (`src/low/data/low_db.json`) is shipped with the package. To re-pull from upstream sources (requires internet access):

```bash
pip install "low[bootstrap]"
python -m low.bootstrap
```

The bootstrap writes `low_db.json` plus one raw JSON file per upstream source:

| File | Contents |
|---|---|
| `src/low/data/low_db.json` | Merged, deduplicated graph database |
| `src/low/data/sources/cldr_speakers.json` | Raw CLDR per-territory language population records (includes `official_status` field) |
| `src/low/data/sources/cia_speakers.json` | Raw CIA World Factbook per-country language records |
| `src/low/data/sources/linguameta_speakers.json` | Raw LinguaMeta per-locale speaker-count records |
| `src/low/data/sources/linguameta_names.json` | Raw LinguaMeta canonical language-name records |
| `src/low/data/sources/linguameta_scripts.json` | Raw LinguaMeta language–script association records |
| `src/low/data/sources/wikidata_speakers.json` | Raw Wikidata SPARQL global speaker-count records |
| `src/low/data/sources/low_scraper_speakers.json` | Normalized web-scraped per-country speaker counts (committed separately; not re-fetched by bootstrap) |

The source files under `src/low/data/sources/` preserve upstream (or scrape) data
exactly as parsed, before deduplication and ISO-code resolution, so they can be
used independently.

## Development

```bash
git clone https://github.com/your-org/low
cd low
pip install -e ".[dev]"
pytest
```

---

## License

MIT
