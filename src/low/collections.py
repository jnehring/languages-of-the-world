from __future__ import annotations

from typing import Generic, Iterator, List, Optional, TypeVar, overload

from .models import Continent, Country, Language, LanguageFamily, Region, SpeakerCount

T = TypeVar("T")


class _BaseCollection(Generic[T]):
    def __init__(self, items: List[T]) -> None:
        self._items = items

    def __iter__(self) -> Iterator[T]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    @overload
    def __getitem__(self, index: int) -> T: ...
    @overload
    def __getitem__(self, index: slice) -> List[T]: ...

    def __getitem__(self, index):
        return self._items[index]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({len(self._items)} items)"


class LanguageCollection(_BaseCollection[Language]):
    def __init__(self, languages: List[Language]) -> None:
        super().__init__(languages)
        self._idx_p1 = {l.part1: l for l in languages if l.part1}
        self._idx_p3 = {l.part3: l for l in languages}
        self._idx_lbl = {l.label.lower(): l for l in languages}

    def get(self, query: str) -> Optional[Language]:
        """
        Polymorphic lookup by ISO 639-1 (2-char), ISO 639-3 (3-char), or label.

        low.languages.get("fr")      -> ISO 639-1
        low.languages.get("fra")     -> ISO 639-3
        low.languages.get("French")  -> case-insensitive label
        """
        if not isinstance(query, str) or not query:
            return None
        token = query.strip()
        if len(token) == 2:
            return self._idx_p1.get(token.lower())
        if len(token) == 3:
            return self._idx_p3.get(token.lower())
        return self._idx_lbl.get(token.lower())

    def filter(
        self,
        label_contains: Optional[str] = None,
        min_speakers: Optional[int] = None,
    ) -> List[Language]:
        """Return languages matching all supplied criteria."""
        res = self._items
        if label_contains is not None:
            needle = label_contains.lower()
            res = [l for l in res if needle in l.label.lower()]
        if min_speakers is not None:
            res = [l for l in res if l.speaker_count >= min_speakers]
        return res


class CountryCollection(_BaseCollection[Country]):
    def __init__(self, countries: List[Country]) -> None:
        super().__init__(countries)
        self._idx_code = {c.code.upper(): c for c in countries}
        self._idx_lbl = {c.label.lower(): c for c in countries}

    def get(self, query: str) -> Optional[Country]:
        """
        Lookup by ISO 3166-1 alpha-2 code or label.

        db.countries.get("RW")      -> by code
        db.countries.get("Rwanda")  -> by label
        """
        if not isinstance(query, str) or not query:
            return None
        token = query.strip()
        if len(token) == 2:
            return self._idx_code.get(token.upper())
        return self._idx_lbl.get(token.lower())


class ContinentCollection(_BaseCollection[Continent]):
    def __init__(self, continents: List[Continent]) -> None:
        super().__init__(continents)
        self._idx_id = {c.id: c for c in continents}
        self._idx_lbl = {c.label.lower(): c for c in continents}

    def get(self, query: str) -> Optional[Continent]:
        """Lookup by UN M49 numeric ID or label."""
        if not isinstance(query, str) or not query:
            return None
        token = query.strip()
        result = self._idx_id.get(token)
        if result is not None:
            return result
        return self._idx_lbl.get(token.lower())


class RegionCollection(_BaseCollection[Region]):
    def __init__(self, regions: List[Region]) -> None:
        super().__init__(regions)
        self._idx_id = {r.id: r for r in regions}
        self._idx_lbl = {r.label.lower(): r for r in regions}

    def get(self, query: str) -> Optional[Region]:
        """Lookup by UN M49 numeric ID or label."""
        if not isinstance(query, str) or not query:
            return None
        token = query.strip()
        result = self._idx_id.get(token)
        if result is not None:
            return result
        return self._idx_lbl.get(token.lower())


class FamilyCollection(_BaseCollection[LanguageFamily]):
    def __init__(self, families: List[LanguageFamily]) -> None:
        super().__init__(families)
        self._idx_glottocode = {f.glottocode: f for f in families}
        self._idx_lbl = {f.label.lower(): f for f in families}

    def get(self, query: str) -> Optional[LanguageFamily]:
        """
        Lookup by Glottolog code or label.

        db.families.get("indo1319")       -> by glottocode
        db.families.get("Indo-European")  -> by label (case-insensitive)
        """
        if not isinstance(query, str) or not query:
            return None
        token = query.strip()
        result = self._idx_glottocode.get(token)
        if result is not None:
            return result
        return self._idx_lbl.get(token.lower())

    def roots(self) -> List[LanguageFamily]:
        """All top-level families (no parent)."""
        return [f for f in self._items if f.parent is None]


class SpeakerCountCollection(_BaseCollection[SpeakerCount]):
    def __init__(self, items: List[SpeakerCount]) -> None:
        super().__init__(items)
        self._by_country: dict = {}
        self._by_language: dict = {}
        for sc in items:
            self._by_country.setdefault(sc.country.code, []).append(sc)
            self._by_language.setdefault(sc.language.part3, []).append(sc)

    def for_country(self, code: str) -> List[SpeakerCount]:
        """All SpeakerCount entries for an ISO 3166-1 alpha-2 country code."""
        return self._by_country.get(code.upper(), [])

    def for_language(self, part3: str) -> List[SpeakerCount]:
        """All SpeakerCount entries for an ISO 639-3 language code."""
        return self._by_language.get(part3.lower(), [])

    def by_source(self, source: str) -> List[SpeakerCount]:
        """All SpeakerCount entries from a given source (e.g. 'cldr', 'cia')."""
        return [sc for sc in self._items if sc.source == source]
