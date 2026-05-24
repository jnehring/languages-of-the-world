"""Tests for LanguageCollection and sibling collection classes."""
from __future__ import annotations

import pytest

from low.collections import LanguageCollection
from low.models import Language


# ---------------------------------------------------------------------------
# LanguageCollection — get() routing
# ---------------------------------------------------------------------------

class TestLanguageCollectionGet:
    def test_lookup_by_part1(self, db):
        lang = db.languages.get("rw")
        assert lang is not None
        assert lang.part3 == "kin"

    def test_lookup_by_part1_case_insensitive(self, db):
        assert db.languages.get("RW") == db.languages.get("rw")

    def test_lookup_by_part3(self, db):
        lang = db.languages.get("kin")
        assert lang is not None
        assert lang.label == "Kinyarwanda"

    def test_lookup_by_part3_case_insensitive(self, db):
        assert db.languages.get("KIN") == db.languages.get("kin")

    def test_lookup_by_label(self, db):
        lang = db.languages.get("French")
        assert lang is not None
        assert lang.part3 == "fra"

    def test_lookup_by_label_case_insensitive(self, db):
        assert db.languages.get("french") == db.languages.get("French")

    def test_lookup_missing_returns_none(self, db):
        assert db.languages.get("zzz") is None

    def test_lookup_empty_string_returns_none(self, db):
        assert db.languages.get("") is None

    def test_lookup_no_part1_language_by_part3(self, db):
        """A language without a part1 code is still reachable by part3."""
        lang = db.languages.get("arc")
        assert lang is not None
        assert lang.part1 is None

    def test_lookup_no_part1_via_two_char_returns_none(self, db):
        """Two-char query routes to part1 index; missing entry → None."""
        assert db.languages.get("ac") is None


# ---------------------------------------------------------------------------
# LanguageCollection — filter()
# ---------------------------------------------------------------------------

class TestLanguageCollectionFilter:
    def test_filter_by_label_contains(self, db):
        results = db.languages.filter(label_contains="indi")
        assert any(l.part3 == "hin" for l in results)

    def test_filter_by_min_speakers(self, db):
        results = db.languages.filter(min_speakers=100_000_000)
        assert all(l.speaker_count >= 100_000_000 for l in results)
        codes = {l.part3 for l in results}
        assert "por" in codes
        assert "kin" not in codes

    def test_filter_combined(self, db):
        results = db.languages.filter(label_contains="o", min_speakers=50_000_000)
        assert all("o" in l.label.lower() for l in results)
        assert all(l.speaker_count >= 50_000_000 for l in results)

    def test_filter_no_criteria_returns_all(self, db):
        assert len(db.languages.filter()) == len(db.languages)

    def test_filter_zero_min_speakers_returns_all(self, db):
        assert len(db.languages.filter(min_speakers=0)) == len(db.languages)


# ---------------------------------------------------------------------------
# Sequence protocol
# ---------------------------------------------------------------------------

class TestSequenceProtocol:
    def test_len(self, db):
        assert len(db.languages) == 6

    def test_iter(self, db):
        items = list(db.languages)
        assert len(items) == 6
        assert all(isinstance(l, Language) for l in items)

    def test_getitem_int(self, db):
        first = db.languages[0]
        assert isinstance(first, Language)

    def test_getitem_slice(self, db):
        subset = db.languages[:2]
        assert isinstance(subset, list)
        assert len(subset) == 2

    def test_getitem_negative(self, db):
        last = db.languages[-1]
        assert isinstance(last, Language)
