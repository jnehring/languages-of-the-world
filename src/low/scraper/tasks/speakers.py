from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .base import ScrapeItem

_INT_RE = re.compile(r"-?\d[\d,_.\s]*")

INSTRUCTIONS = (
    "You are given a web page (in Markdown) as context. "
    "Extract the total number of speakers of the language {language} in {country}. "
    "Combine L1 (native) and L2 (second-language) speakers into a single total — do not distinguish them. "
    "Output ONLY a single integer with no thousands separators, no units, no commentary. "
    "If the page does not contain enough information to determine the number, output exactly: UNKNOWN"
)


def parse_speaker_count(raw: str) -> Optional[int]:
    """Parse an LLM response into an integer count, or None for UNKNOWN/garbage."""
    if raw is None:
        return None
    s = raw.strip()
    if not s or s.upper().startswith("UNKNOWN"):
        return None
    match = _INT_RE.search(s)
    if not match:
        return None
    cleaned = re.sub(r"[,_\s]", "", match.group(0))
    try:
        if "." in cleaned:
            value = int(float(cleaned))
        else:
            value = int(cleaned)
    except ValueError:
        return None
    return value if value >= 0 else None


class SpeakerCountTask:
    """Scrape per-country speaker counts for missing language pairs."""

    name = "speakers"

    def discover_items(self) -> List[ScrapeItem]:
        import low

        db = low.LanguagesOfTheWorld()
        items: List[ScrapeItem] = []
        for country in db.countries:
            known = {sc.language.part3 for sc in country.speaker_counts}
            for lang in country.languages:
                if lang.part3 in known:
                    continue
                items.append(
                    ScrapeItem(
                        fields={
                            "country_code": country.code,
                            "country": country.label,
                            "language_part3": lang.part3,
                            "language": lang.label,
                        }
                    )
                )
        return items

    def item_key(self, item: ScrapeItem) -> Tuple[str, str]:
        return (item.get("country"), item.get("language"))

    def result_columns(self) -> List[str]:
        return ["country", "language"]

    def search_query(self, item: ScrapeItem) -> str:
        return f"{item.get('language')} language number of speakers in {item.get('country')}"

    def build_prompt(self, item: ScrapeItem, markdown: str) -> str:
        country = item.get("country")
        language = item.get("language")
        instructions = INSTRUCTIONS.format(language=language, country=country)
        return (
            f"{instructions}\n\n"
            f"Question: What is the number of {language} speakers in {country}?\n\n"
            f"--- WEB PAGE (Markdown) ---\n{markdown}\n"
        )

    def parse_response(self, raw: str) -> Optional[int]:
        return parse_speaker_count(raw)

    def is_solved(self, value: Any) -> bool:
        return value is not None

    def merge_values(self, existing: Any, new: Any) -> Any:
        if existing is None:
            return new
        if new is None:
            return existing
        return max(existing, new)

    def to_output_record(self, item: ScrapeItem, value: Any, url: str) -> Dict[str, Any]:
        return {
            "country": item.get("country"),
            "language": item.get("language"),
            "number_of_speakers": value,
            "source_url": url,
        }

    def output_filename(self) -> str:
        return "speakers.json"

    def item_for_key(self, key: Tuple[str, ...], fields: Dict[str, str]) -> ScrapeItem:
        country, language = key
        return ScrapeItem(
            fields={
                "country_code": fields.get("country_code", ""),
                "country": country,
                "language_part3": fields.get("language_part3", ""),
                "language": language,
            }
        )
