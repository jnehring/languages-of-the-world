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
    source: str  # "cldr", "cia", "linguameta", or "scraped"
    source_url: Optional[str] = None  # unused; kept for backward-compatible JSON loads

    def __repr__(self) -> str:
        url_part = f", source_url={self.source_url!r}" if self.source_url else ""
        return (
            f"SpeakerCount(country={self.country.code!r}, "
            f"language={self.language.part3!r}, "
            f"speaker_count={self.speaker_count}, "
            f"speaker_fraction={self.speaker_fraction:.4f}, source={self.source!r}{url_part})"
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
class Script:
    """A writing system identified by ISO 15924."""

    code: str   # ISO 15924 four-letter code (lowercase)
    label: str  # English display name
    _languages_ref: List["Language"] = field(default_factory=list, repr=False, compare=False)

    @property
    def languages(self) -> List["Language"]:
        return self._languages_ref

    def __repr__(self) -> str:
        return f"Script(code={self.code!r}, label={self.label!r})"

    def __hash__(self) -> int:
        return hash(self.code)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Script):
            return self.code == other.code
        return NotImplemented


@dataclass
class LanguageName:
    """
    A canonical name for a language, expressed in some (possibly different) language.

    Sourced from LinguaMeta's `name_data` (`is_canonical=True` only).
    """

    language: "Language"             # the language being named
    name: str                        # the name itself (e.g. "Deutsch", "German")
    in_language_bcp47: str           # BCP 47 code of the language the name is in
    in_language: Optional["Language"]  # resolved Language, if a known ISO 639-3 maps
    script: Optional[str] = None     # ISO 15924 code, when supplied
    source: Optional[str] = None     # upstream source (e.g. "CLDR")

    @property
    def is_endonym(self) -> bool:
        """True when this name is expressed in the language itself."""
        return self.in_language is not None and self.in_language.part3 == self.language.part3

    def __repr__(self) -> str:
        return (
            f"LanguageName(language={self.language.part3!r}, "
            f"name={self.name!r}, in_language={self.in_language_bcp47!r})"
        )


@dataclass
class Language:
    part3: str           # ISO 639-3 — primary key
    label: str
    scope: str           # "I" Individual, "M" Macrolanguage
    countries: List[Country]
    family: Optional[LanguageFamily]   # immediate parent node in Glottolog tree
    part1: Optional[str] = None        # ISO 639-1 (optional)
    speaker_count: Optional[int] = None
    """Total speakers across all sources. None if no source reported a count."""
    glottocode: Optional[str] = None   # Glottolog identifier
    endangerment: Optional[str] = None
    """Glottolog Agglomerated Endangered Status (AES). One of:
    'not_endangered', 'threatened', 'shifting', 'moribund', 'nearly_extinct',
    'extinct'. None if Glottolog has no AES assessment for this language."""
    _speaker_count_ref: List["SpeakerCount"] = field(default_factory=list, repr=False, compare=False)
    _names_ref: List["LanguageName"] = field(default_factory=list, repr=False, compare=False)
    _scripts_ref: List["Script"] = field(default_factory=list, repr=False, compare=False)

    @property
    def speaker_counts(self) -> List["SpeakerCount"]:
        return self._speaker_count_ref

    @property
    def names(self) -> List["LanguageName"]:
        """All canonical names for this language, across other languages."""
        return self._names_ref

    @property
    def scripts(self) -> List["Script"]:
        """Writing systems used for this language (canonical scripts first)."""
        return self._scripts_ref

    @property
    def primary_script(self) -> Optional["Script"]:
        """The primary script for this language, if known."""
        return self._scripts_ref[0] if self._scripts_ref else None

    @property
    def endonym(self) -> Optional["LanguageName"]:
        """The canonical name expressed in this language itself, if known."""
        for n in self._names_ref:
            if n.is_endonym:
                return n
        return None

    def __repr__(self) -> str:
        return f"Language(part3={self.part3!r}, label={self.label!r})"

    def __hash__(self) -> int:
        return hash(self.part3)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Language):
            return self.part3 == other.part3
        return NotImplemented
