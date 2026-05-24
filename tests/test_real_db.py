"""
Smoke tests against the baked production database (low_db.json).
These are intentionally broad — they guard against silent data corruption
rather than precise counts that change with each bootstrap run.
"""
from __future__ import annotations

import pytest

from low import LanguagesOfTheWorld


@pytest.fixture(scope="module")
def real_db():
    return LanguagesOfTheWorld()


class TestRealDB:
    def test_language_count_plausible(self, real_db):
        assert len(real_db.languages) > 7000

    def test_country_count_plausible(self, real_db):
        assert len(real_db.countries) > 190

    def test_continent_count_plausible(self, real_db):
        assert 4 <= len(real_db.continents) <= 8

    def test_family_tree_populated(self, real_db):
        # Glottolog has ~2500 family-level nodes
        assert len(real_db.families) > 2000

    def test_root_families_exist(self, real_db):
        roots = real_db.families.roots()
        root_labels = {f.label for f in roots}
        assert "Indo-European" in root_labels

    def test_kinyarwanda_present(self, real_db):
        lang = real_db.languages.get("kin")
        assert lang is not None
        assert lang.label == "Kinyarwanda"
        assert lang.speaker_count > 0

    def test_kinyarwanda_glottocode(self, real_db):
        lang = real_db.languages.get("kin")
        assert lang.glottocode is not None

    def test_french_part1(self, real_db):
        lang = real_db.languages.get("fr")
        assert lang is not None
        assert lang.part3 == "fra"

    def test_french_family_tree(self, real_db):
        lang = real_db.languages.get("fra")
        assert lang.family is not None
        # Walk up to root — should reach Indo-European
        root = lang.family.root
        assert root.label == "Indo-European"

    def test_german_tree_depth(self, real_db):
        deu = real_db.languages.get("deu")
        assert deu.family is not None
        # Standard German sits deep in the Glottolog tree (>= 3 levels)
        assert deu.family.depth >= 2
        assert deu.family.root.label == "Indo-European"

    def test_rwanda_reachable(self, real_db):
        rw = real_db.countries.get("RW")
        assert rw is not None
        assert rw.continent.label == "Africa"

    def test_navigation_chain(self, real_db):
        lang = real_db.languages.get("kin")
        for country in lang.countries:
            assert country.region is not None
            assert country.continent is not None

    def test_family_get_by_glottocode(self, real_db):
        ie = real_db.families.get("indo1319")
        assert ie is not None
        assert ie.label == "Indo-European"
        assert ie.parent is None
