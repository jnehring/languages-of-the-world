from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Protocol, Tuple, runtime_checkable


@dataclass(frozen=True)
class ScrapeItem:
    """One unit to scrape. ``fields`` holds task-specific string columns."""

    fields: Dict[str, str]

    def get(self, key: str) -> str:
        return self.fields.get(key, "")


@runtime_checkable
class ScrapeTask(Protocol):
    """Hook points shared by all scrape targets."""

    name: str

    def discover_items(self) -> List[ScrapeItem]:
        """Return all items that may need scraping."""

    def item_key(self, item: ScrapeItem) -> Tuple[str, ...]:
        """Hashable identity for aggregation and deduplication."""

    def result_columns(self) -> List[str]:
        """CSV identity columns (besides url, prompt, llm_response)."""

    def search_query(self, item: ScrapeItem) -> str:
        """Serper search query for this item."""

    def build_prompt(self, item: ScrapeItem, markdown: str) -> str:
        """LLM prompt including page context."""

    def parse_response(self, raw: str) -> Any:
        """Parse LLM output; None means unresolved."""

    def is_solved(self, value: Any) -> bool:
        """Whether a parsed value counts as resolved."""

    def merge_values(self, existing: Any, new: Any) -> Any:
        """Combine two parsed values for the same item key."""

    def to_output_record(self, item: ScrapeItem, value: Any, url: str) -> Dict[str, Any]:
        """One record in the final aggregated JSON output."""

    def output_filename(self) -> str:
        """Filename written under the data directory."""

    def item_for_key(self, key: Tuple[str, ...], fields: Dict[str, str]) -> ScrapeItem:
        """Reconstruct a ScrapeItem from a result row (for resume/aggregate)."""
