# low — Languages of the World

[![CI](https://github.com/your-org/low/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/low/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

`low` is a lightweight, read-only Python utility that aggregates and normalises global **language**, **country**, **continent**, **regional**, and **per-country speaker count data** into a connected in-memory object graph.

Instead of wrapping data behind traditional repository classes, `low` exposes everything through idiomatic Python sequences, smart multi-key lookups, and direct dot-notation object navigation.

---

## Installation

```bash
pip install low
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
    print(f"{country.label} — {country.region.label} ({country.continent.label})")
# Rwanda — Eastern Africa (Africa)
# DR Congo — Eastern Africa (Africa)
# Uganda — Eastern Africa (Africa)

# Country → back-reference to languages
rw = db.countries.get("RW")
for l in rw.languages:
    print(l.label)

# Filter by partial name or minimum speakers
popular = db.languages.filter(min_speakers=50_000_000)
romance = db.languages.filter(label_contains="Portug")

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

# Per-country speaker counts — how many people speak a language in each country
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

# Query the full SpeakerCount collection directly
db.speaker_counts.for_country("DE")        # all entries for Germany
db.speaker_counts.for_language("deu")      # all entries for German
db.speaker_counts.by_source("cldr")        # all CLDR-sourced entries
db.speaker_counts.by_source("cia")         # all CIA-sourced entries
```

---

## Entity Model

```
[Continent] <───1:N─── [Region] <───1:N─── [Country] <───M:N─── [Language]
     │                                           │                     │
     └───────────────────1:N────────────────────┘                     └───N:1─── [LanguageFamily]
                                │                                                      │ parent/children
                                └───────────── [SpeakerCount] ─────────────────────────
                                                  (country, language,
                                                   speaker_count, source)
```

### Language

| Property | Type | Source | Description |
|---|---|---|---|
| `part3` | `str` | SIL ISO 639-3 | ISO 639-3 three-letter code — primary key |
| `part1` | `Optional[str]` | SIL ISO 639-3 | ISO 639-1 two-letter code (if assigned) |
| `label` | `str` | SIL ISO 639-3 | Reference name |
| `scope` | `str` | SIL ISO 639-3 | `"I"` Individual · `"M"` Macrolanguage · `"S"` Special |
| `speaker_count` | `int` | LinguaMeta / Wikidata | Estimated total speakers (global), max across sources |
| `countries` | `List[Country]` | LinguaMeta | Countries where the language is spoken |
| `family` | `Optional[LanguageFamily]` | Glottolog | Immediate parent node in the Glottolog tree |
| `glottocode` | `Optional[str]` | Glottolog | Glottolog identifier (e.g. `"kin1248"`) |
| `speaker_counts` | `List[SpeakerCount]` | CLDR / CIA | Per-country speaker counts for this language |

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
| `speaker_counts` | `List[SpeakerCount]` | CLDR / CIA | Per-language speaker counts in this country |

### SpeakerCount

Represents how many speakers of a given language live in a given country,
according to a specific data source. Both `country.speaker_counts` and
`language.speaker_counts` navigate to these objects.

| Property | Type | Source | Description |
|---|---|---|---|
| `country` | `Country` | — | The country |
| `language` | `Language` | — | The language |
| `speaker_count` | `int` | CLDR / CIA | Estimated number of speakers |
| `speaker_fraction` | `float` | CLDR / CIA | Share of country population (0.0–1.0) |
| `source` | `str` | — | `"cldr"` or `"cia"` |

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
classification tree.  Every node — from the deepest sub-branch to a top-level
family like Indo-European — is a `LanguageFamily` instance.

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

---

## Collection Interface

Every entity collection (`db.languages`, `db.countries`, `db.continents`, `db.regions`, `db.families`, `db.speaker_counts`) implements the Python sequence protocol:

```python
len(db.languages)        # int
db.languages[0]          # Language
db.languages[:5]         # List[Language]
for lang in db.languages: ...
```

### `.get(query)` — Polymorphic lookup

| Query pattern | Resolves to |
|---|---|
| 2-char string | ISO 639-1 / ISO 3166-1 alpha-2 |
| 3-char string | ISO 639-3 |
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
db.families.roots()   # List[LanguageFamily] — only top-level families
```

### SpeakerCountCollection (`db.speaker_counts`)

The `SpeakerCount` collection adds three targeted query methods on top of the
standard sequence protocol:

```python
db.speaker_counts.for_country("DE")    # List[SpeakerCount] — all entries for Germany
db.speaker_counts.for_language("deu")  # List[SpeakerCount] — all entries for German
db.speaker_counts.by_source("cldr")    # List[SpeakerCount] — CLDR entries only
db.speaker_counts.by_source("cia")     # List[SpeakerCount] — CIA entries only
```

The same data is also reachable through dot navigation on `Country` and `Language`:

```python
db.countries.get("DE").speaker_counts   # identical to for_country("DE")
db.languages.get("deu").speaker_counts  # identical to for_language("deu")
```

---

## Data Provenance

`low` integrates six open datasets.  The bootstrap pipeline (`python -m low.bootstrap`)
fetches them at build time and bakes the result into `src/low/data/low_db.json`.

### [SIL International — ISO 639-3](https://iso639-3.sil.org/)

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

### [UN M49 — ISO-3166-Countries-with-Regional-Codes](https://github.com/lukes/ISO-3166-Countries-with-Regional-Codes)

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

### [Google Research — LinguaMeta](https://github.com/google-research/url-nlp/tree/main/linguameta)

**URL:** `https://raw.githubusercontent.com/google-research/url-nlp/main/linguameta/linguameta.tsv`  
**Licence:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)  
**Fields provided:**

| Field | Column in source |
|---|---|
| `Language.speaker_count` | `estimated_number_of_speakers` |
| `Language.countries` | `locales` (comma-separated ISO 3166-1 alpha-2) |

LinguaMeta covers ~6 600 languages with speaker-count estimates and the countries
where each language is spoken.  Speaker counts use order-of-magnitude rounding.
Multiple BCP-47 rows mapping to the same ISO 639-3 code are merged (max speakers,
union of country codes).

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

The `classification` value is a slash-separated ancestor chain from the root
family down to the node's immediate parent (e.g.
`"indo1319/clas1257/germ1287/nort3152/west2793/high1289/high1286/midd1349/mode1258/uppe1464/glob1243"`).
The bootstrap extracts the last element as the immediate parent, producing the
full navigable tree.  The production database contains ~4 800 family-level nodes
and 246 root families.

---

### [Unicode CLDR — supplementalData.xml](https://github.com/unicode-org/cldr)

**URL:** `https://raw.githubusercontent.com/unicode-org/cldr/main/common/supplemental/supplementalData.xml`  
**Licence:** [Unicode License v3](https://www.unicode.org/license.txt)  
**Raw output:** `src/low/data/sources/cldr_speakers.json`  
**Fields provided:**

| Field | Source element |
|---|---|
| `Country.population` | `territory[@population]` |
| `Country.official_languages` | `languagePopulation[@officialStatus="official"]` |
| `Country.official_regional_languages` | `languagePopulation[@officialStatus="official_regional"]` |
| `Country.de_facto_official_languages` | `languagePopulation[@officialStatus="de_facto_official"]` |
| `SpeakerCount.country` | `<territory type="…">` — ISO 3166-1 alpha-2 |
| `SpeakerCount.language` | `<languagePopulation type="…">` — BCP 47 tag, mapped to ISO 639-3 |
| `SpeakerCount.speaker_count` | `territory[@population]` × `languagePopulation[@populationPercent]` / 100 |
| `SpeakerCount.speaker_fraction` | `languagePopulation[@populationPercent]` / 100 |

Each `<territory>` element carries the total population and a list of
`<languagePopulation>` children with `populationPercent` and optional
`officialStatus` attributes.  The three official-status lists on `Country`
are built from the `officialStatus` attribute; entries with any other value
(e.g. `official_minority`) or no attribute are omitted from those lists.
Territory population is written directly onto `Country.population`.
BCP 47 language tags are normalised to ISO 639-3 codes using the SIL table
(2-char base → ISO 639-1 → ISO 639-3 mapping; 3-char base used directly).

---

### [CIA World Factbook — factbook.json](https://github.com/factbook/factbook.json)

**Index URL:** `https://raw.githubusercontent.com/factbook/factbook.json/master/index.json`  
**Per-country base:** `https://raw.githubusercontent.com/factbook/factbook.json/master/`  
**Licence:** Public domain (U.S. Government work)  
**Raw output:** `src/low/data/sources/cia_speakers.json`  
**Fields provided:**

| Field | Source path in country JSON |
|---|---|
| `SpeakerCount.country` | `Government › Country name › conventional short form` — matched to ISO alpha-2 by label |
| `SpeakerCount.language` | `People and Society › Languages › language[].name` — matched to ISO 639-3 by label |
| `SpeakerCount.speaker_count` | country population × language `percent` / 100 |
| `SpeakerCount.speaker_fraction` | language `percent` / 100 |

Country files are fetched in parallel (up to 20 threads).  Each file's language
section is parsed as a structured list when available or extracted from free text
via a percentage regex as fallback.  Language names are matched to ISO 639-3
codes against the `Language.label` index.

---

### [Wikidata — SPARQL Query Service](https://query.wikidata.org/)

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

## Regenerating the Database

The baked JSON (`src/low/data/low_db.json`) is shipped with the package. To re-pull from upstream sources (requires internet access):

```bash
pip install "low[bootstrap]"
python -m low.bootstrap
```

The bootstrap writes three files:

| File | Contents |
|---|---|
| `src/low/data/low_db.json` | Merged, deduplicated graph database (includes `country_official_languages` section) |
| `src/low/data/sources/cldr_speakers.json` | Raw CLDR per-territory language population records (includes `official_status` field) |
| `src/low/data/sources/cia_speakers.json` | Raw CIA World Factbook per-country language records |
| `src/low/data/sources/wikidata_speakers.json` | Raw Wikidata SPARQL global speaker-count records |

The two source files preserve the original data exactly as parsed, before
deduplication and ISO-code resolution, so they can be used independently.

---

## Examples

See the [`examples/`](examples/) directory for Jupyter notebooks:

| Notebook | Description |
|---|---|
| [`01_languages_per_country.ipynb`](examples/01_languages_per_country.ipynb) | World choropleth map — number of languages per country |

---

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
