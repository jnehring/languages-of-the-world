
# **Software Requirement Specification: Languages of the World (`low`)**

## **1\. System Overview & Context**

`low` is a lightweight, read-only Python utility package that aggregates and normalizes global language, country, continent, and regional data into an interconnected **in-memory object graph**.

Instead of wrapping data logic inside traditional database repositories, `low` exposes data through intuitive Pythonic sequences, smart multi-key lookups, and direct object-to-object property navigation.

## **2\. Architectural Pivot Notes (Design Evolution)**

### **Comment & Feedback Registry**

**Architectural Critique:** The initial repository pattern spec (`LanguageRepository.findByPart1("fra")`) introduced unnecessary boilerplate for an in-memory, read-only dataset. Additionally, a pure bidirectional JSON layout would create infinite evaluation loops or severe data redundancy during serialization.

* **User Decision — Object Graph Transition:** Approved pivoting away from repositories to a unified Object Graph. The API should let developers query entities via singular smart endpoints and traverse relationships natively using dot notation (`language.countries[0].region.label`).  
* **User Decision — Global Querying:** Approved using native Python sequence magic methods (`__iter__`, `__len__`, `__getitem__`). This allows the collection wrapper to act completely like a standard, sliced, and iterable Python list (`low.languages[:5]`), removing the need for clunky `.findAll()` or `.all()` verbs.

## **3\. Data Sourcing & Bootstrapping Pipeline**

The package includes a bootstrapping module (`python -m low.bootstrap`) used **at build-time** (before packaging wheels for PyPI) to pull, sanitize, and bake the source data into a single flat file.

* **ISO 639 Codes & Core Attributes:** Parsed from the official SIL International ISO 639-3 UTF-8 TSV code tables.  
* **Geopolitics (Countries, Continents, Regions):** Sourced from the United Nations M49 Standard CSV.  
* **Demographics & Lineage (Speaker Counts & Families):** Normalized using a static data snapshot curated from a verified public domain source (such as Wikidata or CIA World Factbook), since official ISO standards do not track speaker demographics.

## **4\. Storage Scheme (The Serialization Solution)**

To avoid circular references and infinite loops in the raw data files, the serialized file (`src/low/data/low_db.json`) uses a relational **Foreign Key pattern** rather than nesting or embedding objects inside one another.

JSON  
{  
  "continents": \[{"id": "002", "label": "Africa"}\],  
  "regions": \[{"id": "014", "continent\_id": "002", "label": "Eastern Africa"}\],  
  "countries": \[{"code": "RW", "label": "Rwanda", "continent\_id": "002", "region\_id": "014"}\],  
  "languages": \[  
    {  
      "part1": "rw",  
      "part3": "kin",  
      "label": "Kinyarwanda",  
      "country\_codes": \["RW", "CD", "UG"\],  
      "speaker\_count": 12000000,  
      "scope": "I",  
      "family\_code": "bantu123"  
    }  
  \],  
  "families": \[{"code": "bantu123", "label": "Bantu"}\]  
}

## **5\. In-Memory Object Graph API**

Upon initialization via the primary package client constructor (`low = LanguagesOfTheWorld()`), the database loads the flat JSON and assembles the bidirectional object memory pointers.

### **Entity Relationships (Property Navigation)**

\[Continent\] \<───1:N─── \[Region\] \<───1:N─── \[Country\] \<───M:N─── \[Language\]  
     │                                         │                     │  
     └──────────────────1:N────────────────────┘                     └───N:1─── \[Family\]

### **Data Models**

Python  
from dataclasses import dataclass  
from typing import List, Optional

@dataclass  
class Continent:  
    id: str  
    label: str  
    countries: List\['Country'\]

@dataclass  
class Region:  
    id: str  
    label: str  
    continent: Continent  
    countries: List\['Country'\]

@dataclass  
class Country:  
    code: str  \# ISO 3166-1 alpha-2  
    label: str  
    continent: Continent  
    region: Region  
      
    @property  
    def languages(self) \-\> List\['Language'\]:  
        """Resolved dynamically or wired on startup from the Language graph."""  
        pass

@dataclass  
class LanguageFamily:  
    code: str  
    label: str  
    languages: List\['Language'\]

@dataclass  
class Language:  
    part3: str  \# ISO 639-3 Primary Key  
    label: str  
    scope: str  \# "I" (Individual), "M" (Macrolanguage)  
    countries: List\[Country\]  
    family: Optional\[LanguageFamily\]  
    part1: Optional\[str\] \= None  \# ISO 639-1 (Optional)  
    speaker\_count: int \= 0

## **6\. Collection Interfaces & Query Interface**

Every major entity collection is wrapped inside a sequence-conforming container class.

### **Multi-Key Lookups & List Interfaces**

The collection wrapper exposes a singular `.get()` endpoint that matches data polymorphism dynamically based on string patterns, alongside complete iterable sequences.

Python  
class LanguageCollection:  
    def \_\_init\_\_(self, languages: List\[Language\]):  
        self.\_items \= languages  
        \# Memory-efficient maps for O(1) matching  
        self.\_idx\_p1 \= {l.part1: l for l in languages if l.part1}  
        self.\_idx\_p3 \= {l.part3: l for l in languages}  
        self.\_idx\_lbl \= {l.label.lower(): l for l in languages}

    \# Sequence compliance  
    def \_\_iter\_\_(self): return iter(self.\_items)  
    def \_\_len\_\_(self) \-\> int: return len(self.\_items)  
    def \_\_getitem\_\_(self, index): return self.\_items\[index\]

    def get(self, query: str) \-\> Optional\[Language\]:  
        """  
        Smart Polymorphic Lookup Boundary.  
        low.languages.get("fr")     \-\> Matches ISO 639-1  
        low.languages.get("fra")    \-\> Matches ISO 639-3  
        low.languages.get("French") \-\> Matches Case-Insensitive Label  
        """  
        if not query: return None  
        token \= query.strip().lower()  
        if len(token) \== 2: return self.\_idx\_p1.get(token)  
        if len(token) \== 3: return self.\_idx\_p3.get(token)  
        return self.\_idx\_lbl.get(token)

    def filter(self, label\_contains: str \= None, min\_speakers: int \= None) \-\> List\[Language\]:  
        """Functional lookup scanner for partial attributes."""  
        res \= self.\_items  
        if label\_contains:  
            res \= \[l for l in res if label\_contains.lower() in l.label.lower()\]  
        if min\_speakers is not None:  
            res \= \[l for l in res if l.speaker\_count \>= min\_speakers\]  
        return res

## **7\. Operational Usage Blueprint**

Developers interacting with the library write clean, idiomatic Python:

Python  
import low

\# 1\. Initialize Graph Client  
db \= low.LanguagesOfTheWorld()

\# 2\. Iterate or Slice Global Array Extensions  
total\_tracked \= len(db.languages)  
first\_ten\_langs \= db.languages\[:10\]

\# 3\. Polymorphic Quick-Querying  
target\_lang \= db.languages.get("kin")

\# 4\. Native Object Graph Navigation  
for country in target\_lang.countries:  
    print(f"Spoken in: {country.label}")  
    print(f"Regional Continent Split: {country.region.label} ({country.continent.label})")

## **8\. Package Distribution & Automation Pipeline**

* **Build Target System:** Configured entirely via a modern `pyproject.toml` using `hatchling` or `setuptools`. The data generation pipeline builds the final optimized JSON right into the production source path (`src/low/data/low_db.json`) before shipping.  
* **Documentation:** Fully fleshed `README.md` defining developer usage patterns, structural design rules, and data compilation tasks.  
* **Test Harness:** Robust `pytest` coverage mocking out remote servers during validation checks. Unit tests verify the index lookup routing rules, graph safety, and fallback handling when missing standard values.  
* **GitHub Actions Workflow:** Automated multi-version checks triggered on code adjustments running across target platforms (Python 3.9 through 3.12). Re-runs tests, verifies code quality markers, and safely builds distribution assets.

