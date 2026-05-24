from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    pass


@dataclass
class SpeakerCount:
    """Number of speakers of one language in one country, from a specific source."""

    country: "Country"
    language: "Language"
    speaker_count: int
    speaker_fraction: float   # share of country population, 0.0–1.0
    source: str  # "cldr", "cia", or "linguameta"

    def __repr__(self) -> str:
        return (
            f"SpeakerCount(country={self.country.code!r}, "
            f"language={self.language.part3!r}, "
            f"speaker_count={self.speaker_count}, "
            f"speaker_fraction={self.speaker_fraction:.4f}, source={self.source!r})"
        )

    def __hash__(self) -> int:
        return hash((self.country.code, self.language.part3, self.source))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SpeakerCount):
            return (
                self.country.code == other.country.code
                and self.language.part3 == other.language.part3
                and self.source == other.source
            )
        return NotImplemented


@dataclass
class Continent:
    id: str
    label: str
    countries: List["Country"] = field(default_factory=list, repr=False)

    def __repr__(self) -> str:
        return f"Continent(id={self.id!r}, label={self.label!r})"


@dataclass
class Region:
    id: str
    label: str
    continent: Continent
    countries: List["Country"] = field(default_factory=list, repr=False)

    def __repr__(self) -> str:
        return f"Region(id={self.id!r}, label={self.label!r})"


@dataclass
class Country:
    code: str  # ISO 3166-1 alpha-2
    label: str
    continent: Continent
    region: Region
    population: int = 0
    _language_ref: List["Language"] = field(default_factory=list, repr=False, compare=False)
    _speaker_count_ref: List["SpeakerCount"] = field(default_factory=list, repr=False, compare=False)
    _official_languages_ref: List["Language"] = field(default_factory=list, repr=False, compare=False)
    _official_regional_languages_ref: List["Language"] = field(default_factory=list, repr=False, compare=False)
    _de_facto_official_languages_ref: List["Language"] = field(default_factory=list, repr=False, compare=False)

    @property
    def languages(self) -> List["Language"]:
        return self._language_ref

    @property
    def speaker_counts(self) -> List["SpeakerCount"]:
        return self._speaker_count_ref

    @property
    def official_languages(self) -> List["Language"]:
        return self._official_languages_ref

    @property
    def official_regional_languages(self) -> List["Language"]:
        return self._official_regional_languages_ref

    @property
    def de_facto_official_languages(self) -> List["Language"]:
        return self._de_facto_official_languages_ref

    def __repr__(self) -> str:
        return f"Country(code={self.code!r}, label={self.label!r})"

    def __hash__(self) -> int:
        return hash(self.code)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Country):
            return self.code == other.code
        return NotImplemented


@dataclass
class LanguageFamily:
    """
    A node in the Glottolog language family tree.

    Both internal nodes (subfamilies) and root families are represented
    as LanguageFamily instances.  The full lineage is navigable via
    ``parent`` / ``children``; ``languages`` holds only those languages
    whose immediate Glottolog parent is *this* node.
    """

    glottocode: str      # Glottolog identifier, e.g. "indo1319"
    label: str
    parent: Optional["LanguageFamily"] = field(default=None, repr=False, compare=False)
    children: List["LanguageFamily"] = field(default_factory=list, repr=False, compare=False)
    languages: List["Language"] = field(default_factory=list, repr=False, compare=False)

    @property
    def root(self) -> "LanguageFamily":
        """Walk up to the top-level family (no parent)."""
        node: LanguageFamily = self
        while node.parent is not None:
            node = node.parent
        return node

    @property
    def ancestors(self) -> List["LanguageFamily"]:
        """Ordered list from direct parent up to root (exclusive of self)."""
        result: List[LanguageFamily] = []
        node = self.parent
        while node is not None:
            result.append(node)
            node = node.parent
        return result

    @property
    def depth(self) -> int:
        """Depth in tree: 0 for root families."""
        return len(self.ancestors)

    def __repr__(self) -> str:
        return f"LanguageFamily(glottocode={self.glottocode!r}, label={self.label!r})"

    def __hash__(self) -> int:
        return hash(self.glottocode)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LanguageFamily):
            return self.glottocode == other.glottocode
        return NotImplemented


@dataclass
class Language:
    part3: str           # ISO 639-3 — primary key
    label: str
    scope: str           # "I" Individual, "M" Macrolanguage
    countries: List[Country]
    family: Optional[LanguageFamily]   # immediate parent node in Glottolog tree
    part1: Optional[str] = None        # ISO 639-1 (optional)
    speaker_count: int = 0
    glottocode: Optional[str] = None   # Glottolog identifier
    _speaker_count_ref: List["SpeakerCount"] = field(default_factory=list, repr=False, compare=False)

    @property
    def speaker_counts(self) -> List["SpeakerCount"]:
        return self._speaker_count_ref

    def __repr__(self) -> str:
        return f"Language(part3={self.part3!r}, label={self.label!r})"

    def __hash__(self) -> int:
        return hash(self.part3)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Language):
            return self.part3 == other.part3
        return NotImplemented
