# Speaker-count scraper (`low-scraper`)

The optional scraper fills in **missing per-country speaker counts** — country/language
pairs where `low` knows the language is spoken but has no `SpeakerCount` from CLDR,
CIA, or LinguaMeta.

## Data provenance

Unlike the seven upstream datasets integrated at bootstrap time, scraped speaker counts are **not fetched
during bootstrap**. They are produced offline by the optional `low-scraper` CLI
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
Pairs already covered by CLDR, CIA, or LinguaMeta are not overwritten — scraped
data fills **gaps** where no other source reported a per-country count.

## Install

```bash
pip install "languages-of-the-world[scraper]"
cat >> .env <<'EOF'
SERPER_API_KEY=your-serper-key
GEMINI_API_KEY=your-gemini-key
EOF
```

## Workflow

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
workflow runs `python -m low.bootstrap` and merges this file into `low_db.json` —
it does **not** run the scraper or call Serper/Gemini (too expensive for CI).

Each round retries **UNKNOWN** pairs with fresh search results. Serper and Gemini
responses are cached under `scraper-data/.cache` (use `--no-cache` to bypass).

`low-scraper status` shows completed rounds, resolved counts, and cache stats.

Legacy loom CSV workflow (`scrape` / `aggregate`) remains for old `promptsN_results_*.csv`
files. See [`examples/02_scraper_analysis.ipynb`](../examples/02_scraper_analysis.ipynb) for
per-round resolution statistics.

## Refreshing scraped speaker data

Run locally when you want new web-scraped counts:

```bash
pip install "languages-of-the-world[scraper]"
# SERPER_API_KEY and GEMINI_API_KEY in .env

low-scraper run --rounds 3
low-scraper import    # → src/low/data/sources/low_scraper_speakers.json

git add src/low/data/sources/low_scraper_speakers.json
git commit -m "Update scraped speaker counts"
git push
```

Then cut a release as usual. Scraper updates are decoupled from release cadence — only commit the JSON when you re-scrape.

Working files under `scraper-data/` are gitignored and are **not** used by bootstrap or the release workflow.
