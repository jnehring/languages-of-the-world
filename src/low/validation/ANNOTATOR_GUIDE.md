# LOW Manual Validation — Annotator Instructions

You are reviewing a sample of records from the Languages of the World (LOW) database. Your job is to judge whether each record looks correct and flag anything suspicious.

## What you receive

A single Excel workbook (`low_validation.xlsx`) with one tab per dataset. Each tab has:

- **Context columns** (left, white/blue header) — the data to review. Do not edit these.
- **Annotation columns** (right, light-gray background) — your judgments. Fill in all cells with a light-gray background.

Read the **Instructions** tab when you open the workbook. The **issue_categories** tab shows a color key for issue types.

## Your task, step by step

### 1. Open the workbook

Open `annotation/exports/low_validation.xlsx` in Excel, LibreOffice Calc, or Google Sheets.

If using Google Sheets: File → Import → Upload, then choose "Replace spreadsheet."

### 2. Pick a tab and work row by row

Start with **countries**, then **country_speakers**. After that, work through the remaining tabs in any order.

For each row:

1. Read the context columns and check whether the record is plausible.
2. Fill in the light-gray cells on the right (see below).
3. Skip rows you have not reviewed — leave light-gray cells blank.

You do not need to review every row. Focus on rows where you can make a confident judgment. Rows with a `sample_reason` starting with `risk:` were flagged automatically as potentially problematic — prioritize those.

### 3. Fill in the light-gray cells

| Column | What to enter |
| --- | --- |
| **valid** | `yes` if the record looks correct, `no` if you found a problem, `unsure` if you cannot tell |
| **issue_category** | Required when `valid` is `no`. Pick from the color-coded dropdown. |
| **notes** | Free text. Add evidence: expected value, reference URL, source name, or brief explanation |

The dropdowns are pre-configured. When you select a value, the cell changes color to reflect your choice.

### 4. What to check on each tab

#### continents, regions, countries

- Does the geographic hierarchy make sense? (region → continent, country → region)
- Does the country label match its ISO code?
- Is the population plausible?

#### languages

- Does the ISO 639-3 code (`part3`) match the English label?
- Is the scope (`I` = individual, `M` = macrolanguage) correct?
- Is the global `speaker_count` plausible?
- Should this language have a `glottocode` but does not?
- Do `country_codes` list countries where the language is actually spoken?

#### families

- Does `parent_glottocode` point to a real parent? (empty only for root families)
- Does the label match Glottolog?
- Are there orphan nodes (parent references a missing glottocode)?

#### scripts, language_scripts

- Is the ISO 15924 script code valid?
- Is `is_canonical` reasonable? (e.g. Devanagari for Hindi)

#### country_speakers

- Is this language actually spoken in this country?
- Is `speaker_count` plausible given `country_population`?
- Does `fraction_pct` match speaker_count ÷ population?
- Is the `source` correct?
- If `other_sources_json` shows other counts, do large disagreements make sense?

#### official_languages

- Is the status (`official`, `official_regional`, `de_facto_official`) correct?
- Is the language correctly linked to the country?

#### language_names

- Is the spelling and script plausible?
- Does the endonym/exonym pairing make sense?
- Does the name belong to the language indicated?

#### raw_* tabs

These are upstream source snapshots. Check whether LOW merged them correctly:

- Does the merged LOW data faithfully reflect this upstream row?
- Are ISO code mappings correct (especially CLDR territory → country code)?
- Is anything obviously lost or corrupted during bootstrap?

### 5. Save and return

Save the workbook and return it to the project lead. Place the completed file in `annotation/completed/low_validation.xlsx`.

Do not rename tabs or delete columns.

## Issue category quick reference

| Category | When to use |
| --- | --- |
| `wrong_count` | Speaker count is wrong |
| `wrong_country` | Country assignment is wrong |
| `wrong_language` | Language assignment is wrong |
| `fraction_mismatch` | Fraction does not match count ÷ population |
| `source_error` | Source attribution is wrong |
| `wrong_label` | Display label is wrong |
| `wrong_code` | ISO or other code is wrong |
| `missing_glottocode` | Expected Glottolog code is absent |
| `implausible_speakers` | Speaker count is implausible |
| `wrong_script` | Script code or assignment is wrong |
| `not_a_name` | Value is not a valid language name |
| `canonical_error` | Canonical name/script assignment is wrong |
| `wrong_parent` | Family parent link is wrong |
| `orphan_node` | Family node has no valid parent |
| `wrong_hierarchy` | Geographic hierarchy is wrong |
| `implausible_population` | Population figure is implausible |
| `wrong_status` | Official-language status is wrong |
| `wrong_canonical` | Canonical script flag is wrong |
| `merge_mismatch` | LOW merge does not match upstream |
| `wrong_mapping` | Code mapping during merge is wrong |
| `upstream_error` | Error originates in the upstream source |

See the **issue_categories** tab in the workbook for the full color key.

## Tips

- When in doubt, use `unsure` and explain why in **notes**.
- Rows with `risk:` in `sample_reason` were auto-selected because they look suspicious — start there.
- You are not fixing the database. You are flagging problems so the team can fix them later.
- If you spot a pattern (same error across many rows), note it once in **notes** and mention the pattern.

## Questions?

Ask the project lead before changing your approach or skipping entire tabs.
