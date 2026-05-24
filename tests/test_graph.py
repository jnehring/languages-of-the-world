"""Tests for the in-memory object graph — relationship wiring and navigation."""
from __future__ import annotations

import pytest


class TestLanguageGraph:
    def test_language_countries_populated(self, db):
        lang = db.languages.get("kin")
        assert len(lang.countries) == 3
        codes = {c.code for c in lang.countries}
        assert codes == {"RW", "CD", "UG"}

    def test_language_no_countries(self, db):
        lang = db.languages.get("arc")
        assert lang.countries == []

    def test_language_family_wired(self, db):
        lang = db.languages.get("kin")
        assert lang.family is not None
        assert lang.family.label == "Atlantic-Congo"

    def test_language_family_none_when_missing(self, db):
        lang = db.languages.get("arc")
        assert lang.family is None

    def test_language_speaker_count(self, db):
        lang = db.languages.get("hin")
        assert lang.speaker_count == 344_000_000

    def test_language_glottocode(self, db):
        lang = db.languages.get("kin")
        assert lang.glottocode == "kiny1244"

    def test_language_no_glottocode(self, db):
        lang = db.languages.get("arc")
        assert lang.glottocode is None


class TestFamilyTree:
    def test_root_family_no_parent(self, db):
        ie = db.families.get("indo1319")
        assert ie is not None
        assert ie.parent is None

    def test_subfamily_has_parent(self, db):
        germ = db.families.get("germ1287")
        assert germ is not None
        assert germ.parent is not None
        assert germ.parent.glottocode == "indo1319"

    def test_parent_children_back_reference(self, db):
        ie = db.families.get("indo1319")
        child_codes = {c.glottocode for c in ie.children}
        assert "germ1287" in child_codes

    def test_depth_root(self, db):
        ie = db.families.get("indo1319")
        assert ie.depth == 0

    def test_depth_subfamily(self, db):
        germ = db.families.get("germ1287")
        assert germ.depth == 1

    def test_depth_sub_subfamily(self, db):
        west = db.families.get("west2793")
        assert west.depth == 2

    def test_root_property(self, db):
        west = db.families.get("west2793")
        assert west.root.glottocode == "indo1319"

    def test_ancestors(self, db):
        west = db.families.get("west2793")
        ancestor_codes = [a.glottocode for a in west.ancestors]
        assert ancestor_codes == ["germ1287", "indo1319"]

    def test_language_to_root_via_family(self, db):
        deu = db.languages.get("deu")
        assert deu.family is not None
        assert deu.family.glottocode == "west2793"
        assert deu.family.root.glottocode == "indo1319"

    def test_roots_method(self, db):
        roots = db.families.roots()
        root_codes = {f.glottocode for f in roots}
        assert "indo1319" in root_codes
        assert "atla1278" in root_codes
        assert "germ1287" not in root_codes

    def test_family_languages_back_reference(self, db):
        ie = db.families.get("indo1319")
        lang_codes = {l.part3 for l in ie.languages}
        assert "fra" in lang_codes
        assert "por" in lang_codes
        assert "hin" in lang_codes

    def test_subfamily_own_languages(self, db):
        west = db.families.get("west2793")
        lang_codes = {l.part3 for l in west.languages}
        assert "deu" in lang_codes

    def test_family_get_by_glottocode(self, db):
        fam = db.families.get("indo1319")
        assert fam is not None
        assert fam.label == "Indo-European"

    def test_family_get_by_label(self, db):
        fam = db.families.get("Indo-European")
        assert fam is not None
        assert fam.glottocode == "indo1319"


class TestCountryGraph:
    def test_country_region(self, db):
        rw = db.countries.get("RW")
        assert rw.region.label == "Eastern Africa"

    def test_country_continent(self, db):
        rw = db.countries.get("RW")
        assert rw.continent.label == "Africa"

    def test_country_languages_back_reference(self, db):
        rw = db.countries.get("RW")
        lang_codes = {l.part3 for l in rw.languages}
        assert "kin" in lang_codes
        assert "fra" in lang_codes

    def test_country_get_by_label(self, db):
        brazil = db.countries.get("Brazil")
        assert brazil is not None
        assert brazil.code == "BR"

    def test_country_get_missing(self, db):
        assert db.countries.get("ZZ") is None


class TestRegionGraph:
    def test_region_continent(self, db):
        region = db.regions.get("Eastern Africa")
        assert region is not None
        assert region.continent.label == "Africa"

    def test_region_countries_populated(self, db):
        region = db.regions.get("Eastern Africa")
        codes = {c.code for c in region.countries}
        assert {"RW", "CD", "UG"}.issubset(codes)

    def test_region_get_by_id(self, db):
        region = db.regions.get("014")
        assert region is not None
        assert region.label == "Eastern Africa"


class TestContinentGraph:
    def test_continent_countries_populated(self, db):
        africa = db.continents.get("Africa")
        assert africa is not None
        codes = {c.code for c in africa.countries}
        assert {"RW", "CD", "UG"}.issubset(codes)

    def test_continent_get_by_id(self, db):
        cont = db.continents.get("002")
        assert cont is not None
        assert cont.label == "Africa"


class TestDotNavigation:
    def test_full_country_chain(self, db):
        lang = db.languages.get("kin")
        for country in lang.countries:
            assert country.region.label
            assert country.continent.label
            assert country.region.continent.label == country.continent.label

    def test_full_family_chain(self, db):
        deu = db.languages.get("deu")
        path = []
        node = deu.family
        while node:
            path.append(node.glottocode)
            node = node.parent
        assert path == ["west2793", "germ1287", "indo1319"]


class TestGraphInit:
    def test_missing_db_raises(self, tmp_path):
        from low import LanguagesOfTheWorld
        with pytest.raises(FileNotFoundError):
            LanguagesOfTheWorld(db_path=tmp_path / "nonexistent.json")

    def test_repr(self, db):
        r = repr(db)
        assert "LanguagesOfTheWorld" in r
        assert "languages=6" in r
