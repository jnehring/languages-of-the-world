"""Stratified sampling and high-risk record selection for manual validation."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from low import LanguagesOfTheWorld

from .record_ids import ID_FN_BY_TABLE, add_record_id


ANNOTATION_COLUMNS = [
    "valid",
    "issue_category",
    "notes",
]

SCRAPED_CAP = 200
DISAGREEMENT_RATIO = 0.5
FRACTION_SUM_THRESHOLD = 1.5


def load_raw_db(db_path: Path) -> dict[str, Any]:
    with db_path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_raw_sources(db_path: Path) -> dict[str, list[dict[str, Any]]]:
    sources_dir = db_path.parent / "sources"
    out: dict[str, list[dict[str, Any]]] = {}
    mapping = {
        "raw_cldr_speakers": "cldr_speakers.json",
        "raw_cia_speakers": "cia_speakers.json",
        "raw_linguameta_speakers": "linguameta_speakers.json",
        "raw_linguameta_names": "linguameta_names.json",
        "raw_linguameta_scripts": "linguameta_scripts.json",
        "raw_wikidata_speakers": "wikidata_speakers.json",
        "raw_scraper_speakers": "low_scraper_speakers.json",
    }
    for key, filename in mapping.items():
        path = sources_dir / filename
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                out[key] = json.load(fh)
        else:
            out[key] = []
    return out


def _stratified_sample(
    rows: list[dict[str, Any]],
    n: int,
    group_cols: list[str],
    seed: int,
) -> list[dict[str, Any]]:
    if not rows:
        return []
    if len(rows) <= n:
        return list(rows)

    df = pd.DataFrame(rows)
    for col in group_cols:
        if col not in df.columns:
            df[col] = ""

    groups = list(df.groupby(group_cols, dropna=False))
    if not groups:
        return df.sample(n=n, random_state=seed).to_dict(orient="records")

    per_group = max(1, n // len(groups))
    picked_idx: list[int] = []
    for _, group in groups:
        k = min(len(group), per_group)
        sample = group.sample(n=k, random_state=seed)
        picked_idx.extend(sample.index.tolist())

    picked = df.loc[sorted(set(picked_idx))]
    if len(picked) < n:
        remaining = df.drop(index=picked.index, errors="ignore")
        extra_n = min(n - len(picked), len(remaining))
        if extra_n > 0:
            extra = remaining.sample(n=extra_n, random_state=seed)
            picked = pd.concat([picked, extra])
    return picked.head(n).to_dict(orient="records")


def _merge_samples(
    stratified: list[dict[str, Any]],
    risk: list[tuple[dict[str, Any], str]],
    table: str,
    seed: int,
    n: int,
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    id_fn = ID_FN_BY_TABLE[table]
    manifest: dict[str, list[str]] = defaultdict(list)
    by_id: dict[str, dict[str, Any]] = {}

    for row in stratified:
        rid = id_fn(row)
        by_id[rid] = row
        manifest[rid].append("stratified")

    for row, reason in risk:
        rid = id_fn(row)
        by_id[rid] = row
        if reason not in manifest[rid]:
            manifest[rid].append(reason)

    ordered_ids = sorted(by_id.keys())
    # Stable ordering for reproducibility beyond dict insertion order
    rng = pd.Series(ordered_ids).sample(frac=1, random_state=seed).tolist()
    selected = [by_id[rid] for rid in rng[: max(n, len(rng))]]
    if len(selected) > n and len(risk) == 0:
        selected = selected[:n]
    return selected, dict(manifest)


def _speaker_disagreements(
    rows: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], str]]:
    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (row["country_code"], row["language_code"])
        by_pair[key].append(row)

    risk: list[tuple[dict[str, Any], str]] = []
    for pair_rows in by_pair.values():
        if len(pair_rows) < 2:
            continue
        counts = [r.get("speaker_count") or 0 for r in pair_rows]
        positive = [c for c in counts if c > 0]
        if len(positive) < 2:
            continue
        lo, hi = min(positive), max(positive)
        if hi == 0:
            continue
        if (hi - lo) / hi > DISAGREEMENT_RATIO:
            for row in pair_rows:
                risk.append((row, "risk:disagreement"))
    return risk


def _fraction_risks(
    rows: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], str]]:
    risk: list[tuple[dict[str, Any], str]] = []
    by_country: dict[str, float] = defaultdict(float)
    country_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        frac = float(row.get("speaker_fraction") or 0.0)
        cc = row["country_code"]
        by_country[cc] += frac
        country_rows[cc].append(row)
        if frac > 1.0:
            risk.append((row, "risk:fraction_gt_1"))

    for cc, total in by_country.items():
        if total <= FRACTION_SUM_THRESHOLD:
            continue
        candidates = sorted(
            country_rows[cc],
            key=lambda r: float(r.get("speaker_fraction") or 0.0),
            reverse=True,
        )
        for row in candidates[:2]:
            risk.append((row, "risk:country_fraction_sum"))

    # Deduplicate while preserving first reason
    seen: set[tuple[str, str, str]] = set()
    deduped: list[tuple[dict[str, Any], str]] = []
    for row, reason in risk:
        key = (row["country_code"], row["language_code"], row.get("source", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append((row, reason))
    return deduped


def _scraped_risk(
    rows: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], str]]:
    scraped = [r for r in rows if r.get("source") == "scraped"]
    if len(scraped) > SCRAPED_CAP:
        df = pd.DataFrame(scraped)
        scraped = df.sample(n=SCRAPED_CAP, random_state=42).to_dict(orient="records")
    return [(r, "risk:scraped") for r in scraped]


def _language_risks(
    raw: dict[str, Any],
    speaker_rows: list[dict[str, Any]],
    official_rows: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], str]]:
    speakers_by_lang: dict[str, set[str]] = defaultdict(set)
    for row in speaker_rows:
        speakers_by_lang[row["language_code"]].add(row["country_code"])

    official_by_pair = {
        (r["country_code"], r["language_code"]) for r in official_rows
    }

    risk: list[tuple[dict[str, Any], str]] = []
    for lang in raw.get("languages", []):
        part3 = lang["part3"]
        if lang.get("scope") == "I" and not lang.get("glottocode"):
            risk.append((lang, "risk:missing_glottocode"))
        countries = lang.get("country_codes") or []
        if countries and part3 not in speakers_by_lang:
            risk.append((lang, "risk:no_speaker_data"))
    return risk


def _official_risks(
    official_rows: list[dict[str, Any]],
    speaker_rows: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], str]]:
    speaker_pairs = {
        (r["country_code"], r["language_code"]) for r in speaker_rows
    }
    risk: list[tuple[dict[str, Any], str]] = []
    for row in official_rows:
        key = (row["country_code"], row["language_code"])
        if key not in speaker_pairs:
            risk.append((row, "risk:official_no_speakers"))
    return risk


def _speaker_quartile_bucket(speaker_count: int | None) -> str:
    if speaker_count is None or speaker_count == 0:
        return "zero"
    if speaker_count < 10_000:
        return "lt_10k"
    if speaker_count < 1_000_000:
        return "10k_1m"
    if speaker_count < 50_000_000:
        return "1m_50m"
    return "gte_50m"


def _family_depth_bucket(db: LanguagesOfTheWorld, glottocode: str) -> str:
    fam = db.families.get(glottocode)
    if fam is None:
        return "unknown"
    depth = fam.depth
    if depth == 0:
        return "root"
    if depth == 1:
        return "depth_1"
    if depth <= 3:
        return "mid"
    return "deep"


def _cap_table(
    rows: list[dict[str, Any]],
    reasons: dict[str, list[str]],
    table: str,
    max_samples: int,
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """Randomly cap a table to at most max_samples rows."""
    if len(rows) <= max_samples:
        return rows, reasons
    id_fn = ID_FN_BY_TABLE[table]
    picked = (
        pd.DataFrame(rows)
        .sample(n=max_samples, random_state=seed)
        .to_dict(orient="records")
    )
    kept_ids = {id_fn(row) for row in picked}
    filtered_reasons = {rid: reasons[rid] for rid in kept_ids if rid in reasons}
    return picked, filtered_reasons


def sample_all_tables(
    db: LanguagesOfTheWorld,
    raw: dict[str, Any],
    raw_sources: dict[str, list[dict[str, Any]]],
    *,
    seed: int = 42,
    include_risk: bool = True,
    max_samples: int | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, list[str]]]]:
    """Return sampled rows per export table and manifest reasons per record_id."""
    speaker_rows = raw.get("country_language_speakers", [])
    official_rows = raw.get("country_official_languages", [])
    language_script_rows = raw.get("language_scripts", [])
    language_name_rows = raw.get("language_names", [])

    tables: dict[str, list[dict[str, Any]]] = {}
    manifest: dict[str, dict[str, list[str]]] = {}

    def sample_table(
        table: str,
        rows: list[dict[str, Any]],
        n: int,
        group_cols: list[str],
        risk_fn: Callable[[], list[tuple[dict[str, Any], str]]] | None = None,
        export_all: bool = False,
    ) -> None:
        risk: list[tuple[dict[str, Any], str]] = []
        if include_risk and risk_fn is not None:
            risk = risk_fn()

        if export_all or len(rows) <= n:
            stratified = list(rows)
        else:
            stratified = _stratified_sample(rows, n, group_cols, seed)

        if risk:
            selected, reasons = _merge_samples(stratified, risk, table, seed, n)
        elif export_all or len(rows) <= n:
            selected = stratified
            id_fn = ID_FN_BY_TABLE[table]
            reasons = {id_fn(row): ["all"] for row in selected}
        else:
            selected, reasons = _merge_samples(stratified, [], table, seed, n)

        tables[table] = selected
        manifest[table] = reasons

    sample_table("continents", raw.get("continents", []), 5, ["id"], export_all=True)
    sample_table("regions", raw.get("regions", []), 17, ["continent_id"], export_all=True)
    sample_table("countries", raw.get("countries", []), 247, ["continent_id"], export_all=True)
    sample_table(
        "scripts",
        raw.get("scripts", []),
        106,
        ["code"],
        export_all=len(raw.get("scripts", [])) <= 106,
    )

    family_rows = raw.get("families", [])
    for row in family_rows:
        row["_depth_bucket"] = _family_depth_bucket(db, row["glottocode"])
    sample_table(
        "families",
        family_rows,
        150,
        ["_depth_bucket"],
    )
    for row in tables.get("families", []):
        row.pop("_depth_bucket", None)

    lang_rows = raw.get("languages", [])
    enriched_langs = []
    for row in lang_rows:
        er = dict(row)
        er["_scope"] = row.get("scope") or ""
        er["_endangerment"] = row.get("endangerment") or "none"
        er["_has_glottocode"] = "yes" if row.get("glottocode") else "no"
        er["_speaker_bucket"] = _speaker_quartile_bucket(row.get("speaker_count"))
        enriched_langs.append(er)
    lang_risk = _language_risks(raw, speaker_rows, official_rows) if include_risk else []

    stratified_langs = _stratified_sample(
        enriched_langs,
        200,
        ["_scope", "_endangerment", "_has_glottocode", "_speaker_bucket"],
        seed,
    )
    selected_langs, lang_manifest = _merge_samples(
        stratified_langs, lang_risk, "languages", seed, 200
    )
    for row in selected_langs:
        row.pop("_scope", None)
        row.pop("_endangerment", None)
        row.pop("_has_glottocode", None)
        row.pop("_speaker_bucket", None)
    tables["languages"] = selected_langs
    manifest["languages"] = lang_manifest

    lang_speaker_totals = {
        r["part3"]: r.get("speaker_count") or 0 for r in raw.get("languages", [])
    }
    ls_enriched = []
    for row in language_script_rows:
        er = dict(row)
        er["_speaker_bucket"] = _speaker_quartile_bucket(
            lang_speaker_totals.get(row["language_part3"])
        )
        ls_enriched.append(er)
    sample_table("language_scripts", ls_enriched, 100, ["_speaker_bucket", "is_canonical"])
    for row in tables.get("language_scripts", []):
        row.pop("_speaker_bucket", None)

    def speaker_risk_fn() -> list[tuple[dict[str, Any], str]]:
        risks: list[tuple[dict[str, Any], str]] = []
        risks.extend(_scraped_risk(speaker_rows))
        risks.extend(_speaker_disagreements(speaker_rows))
        risks.extend(_fraction_risks(speaker_rows))
        return risks

    sample_table(
        "country_speakers",
        speaker_rows,
        200,
        ["source"],
        risk_fn=speaker_risk_fn,
    )

    country_continent = {
        c["code"]: c["continent_id"] for c in raw.get("countries", [])
    }
    off_enriched = []
    for row in official_rows:
        er = dict(row)
        er["_continent_id"] = country_continent.get(row["country_code"], "")
        off_enriched.append(er)

    def official_risk_fn() -> list[tuple[dict[str, Any], str]]:
        return _official_risks(official_rows, speaker_rows)

    stratified_off = _stratified_sample(
        off_enriched, 100, ["_continent_id", "status"], seed
    )
    off_risk = official_risk_fn() if include_risk else []
    selected_off, off_manifest = _merge_samples(
        stratified_off, off_risk, "official_languages", seed, 100
    )
    for row in selected_off:
        row.pop("_continent_id", None)
    tables["official_languages"] = selected_off
    manifest["official_languages"] = off_manifest

    # language_names — stratify by source and script
    name_enriched = []
    for row in language_name_rows:
        er = dict(row)
        er["_script_bucket"] = row.get("script") or "none"
        er["_source_bucket"] = row.get("source") or "unknown"
        name_enriched.append(er)
    sample_table(
        "language_names",
        name_enriched,
        200,
        ["_source_bucket", "_script_bucket"],
    )
    for row in tables.get("language_names", []):
        row.pop("_script_bucket", None)
        row.pop("_source_bucket", None)

    # Raw sources — sample matching merged selections where possible
    sampled_speaker_keys = {
        (r["country_code"], r["language_code"], r.get("source"))
        for r in tables["country_speakers"]
    }
    sampled_lang_keys = {r["part3"] for r in tables["languages"]}
    sampled_name_keys = {
        (r["language_part3"], r["name"], r["in_language_bcp47"], r.get("script") or "")
        for r in tables.get("language_names", [])
    }
    sampled_ls_keys = {
        (r["language_part3"], r["script_code"]) for r in tables.get("language_scripts", [])
    }

    cldr_all = raw_sources.get("raw_cldr_speakers", [])
    cldr_matched = [
        r
        for r in cldr_all
        if (r.get("territory"), r.get("iso639_3"), "cldr") in {
            (cc, lc, src) for cc, lc, src in sampled_speaker_keys
        }
    ]
    if not cldr_matched and cldr_all:
        cldr_matched = _stratified_sample(cldr_all, min(200, len(cldr_all)), ["territory"], seed)
    tables["raw_cldr_speakers"] = cldr_matched
    manifest["raw_cldr_speakers"] = {
        ID_FN_BY_TABLE["raw_cldr_speakers"](r): ["matched_or_stratified"] for r in cldr_matched
    }

    cia_all = raw_sources.get("raw_cia_speakers", [])
    tables["raw_cia_speakers"] = cia_all
    manifest["raw_cia_speakers"] = {
        ID_FN_BY_TABLE["raw_cia_speakers"](r): ["all"] for r in cia_all
    }

    lm_spk = raw_sources.get("raw_linguameta_speakers", [])
    lm_spk_matched = [
        r
        for r in lm_spk
        if (r["country_code"], r["iso639_3"], "linguameta") in sampled_speaker_keys
    ]
    if not lm_spk_matched and lm_spk:
        lm_spk_matched = _stratified_sample(
            lm_spk, min(200, len(lm_spk)), ["country_code"], seed
        )
    tables["raw_linguameta_speakers"] = lm_spk_matched
    manifest["raw_linguameta_speakers"] = {
        ID_FN_BY_TABLE["raw_linguameta_speakers"](r): ["matched_or_stratified"]
        for r in lm_spk_matched
    }

    lm_names = raw_sources.get("raw_linguameta_names", [])
    lm_names_matched = [
        r
        for r in lm_names
        if (
            r["language_part3"],
            r["name"],
            r["in_language_bcp47"],
            r.get("script") or "",
        )
        in sampled_name_keys
    ]
    if not lm_names_matched and lm_names:
        enriched = []
        for r in lm_names:
            er = dict(r)
            er["_script_bucket"] = r.get("script") or "none"
            enriched.append(er)
        lm_names_matched = _stratified_sample(
            enriched, min(200, len(enriched)), ["_script_bucket"], seed
        )
        for r in lm_names_matched:
            r.pop("_script_bucket", None)
    tables["raw_linguameta_names"] = lm_names_matched
    manifest["raw_linguameta_names"] = {
        ID_FN_BY_TABLE["raw_linguameta_names"](r): ["matched_or_stratified"]
        for r in lm_names_matched
    }

    lm_scripts = raw_sources.get("raw_linguameta_scripts", [])
    lm_scripts_matched = [
        r
        for r in lm_scripts
        if (r["language_part3"], r["script_code"]) in sampled_ls_keys
    ]
    if not lm_scripts_matched and lm_scripts:
        lm_scripts_matched = _stratified_sample(
            lm_scripts, min(100, len(lm_scripts)), ["script_code"], seed
        )
    tables["raw_linguameta_scripts"] = lm_scripts_matched
    manifest["raw_linguameta_scripts"] = {
        ID_FN_BY_TABLE["raw_linguameta_scripts"](r): ["matched_or_stratified"]
        for r in lm_scripts_matched
    }

    wd_all = raw_sources.get("raw_wikidata_speakers", [])
    wd_matched = [r for r in wd_all if r.get("resolved_part3") in sampled_lang_keys]
    if not wd_matched and wd_all:
        wd_matched = _stratified_sample(wd_all, min(200, len(wd_all)), ["iso639_3"], seed)
    tables["raw_wikidata_speakers"] = wd_matched
    manifest["raw_wikidata_speakers"] = {
        ID_FN_BY_TABLE["raw_wikidata_speakers"](r): ["matched_or_stratified"] for r in wd_matched
    }

    scraper_all = raw_sources.get("raw_scraper_speakers", [])
    scraper_matched = [
        r
        for r in scraper_all
        if (r["country_code"], r["iso639_3"], "scraped") in sampled_speaker_keys
    ]
    if not scraper_matched and scraper_all:
        scraper_matched = scraper_all[:SCRAPED_CAP]
    tables["raw_scraper_speakers"] = scraper_matched
    manifest["raw_scraper_speakers"] = {
        ID_FN_BY_TABLE["raw_scraper_speakers"](r): ["matched_or_stratified"]
        for r in scraper_matched
    }

    if max_samples is not None:
        for table in tables:
            tables[table], manifest[table] = _cap_table(
                tables[table], manifest[table], table, max_samples, seed
            )

    return tables, manifest
