"""
low — Languages of the World
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
An in-memory object graph for language, country, continent, and regional data.

    import low
    db = low.LanguagesOfTheWorld()
    lang = db.languages.get("kin")
    print(lang.countries[0].region.label)
"""
from .graph import LanguagesOfTheWorld
from .models import (
    Continent,
    Country,
    Language,
    LanguageFamily,
    LanguageName,
    Region,
    Script,
    SpeakerCount,
)

__all__ = [
    "LanguagesOfTheWorld",
    "Language",
    "LanguageName",
    "Script",
    "Country",
    "Continent",
    "Region",
    "LanguageFamily",
    "SpeakerCount",
]
__version__ = "0.1.0"
