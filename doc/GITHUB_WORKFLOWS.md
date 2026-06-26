# GitHub Workflows

This repository uses two GitHub Actions workflows under [`.github/workflows/`](../.github/workflows/):

| Workflow | File | Trigger |
|---|---|---|
| **CI** | [`ci.yml`](../.github/workflows/ci.yml) | Push or pull request to `main` / `master` |
| **Release** | [`release.yml`](../.github/workflows/release.yml) | Push of a `v*` tag, or manual dispatch |

---

## CI (`ci.yml`)

CI validates every change before it lands on the default branch.

### `test` job

Runs a matrix across **Python 3.9–3.12** on **Ubuntu** and **macOS** (eight combinations). For each cell it:

1. Checks out the repository
2. Installs the package in editable mode with dev dependencies: `pip install -e ".[dev]"`
3. Runs `pytest` with coverage on `src/low`

`fail-fast: false` keeps other matrix cells running if one fails.

### `build` job

Runs on Ubuntu with Python 3.12 after all `test` jobs pass. It:

1. Installs the `build` package
2. Produces wheel and sdist via `python -m build`
3. Uploads the `dist/` directory as a GitHub Actions artifact named `dist`

This confirms the package builds successfully but does **not** publish anywhere.

---

## Release (`release.yml`)

The release workflow regenerates the database from upstream sources, builds the distribution, and publishes to PyPI (or TestPyPI).

### Triggers

- **Tag push** (`v*`) — production release to PyPI
- **Manual dispatch** — choose `testpypi` or `pypi` as the publish target

### Jobs

1. **`build`** — regenerate `low_db.json`, build wheel + sdist, upload `dist/` artifact
2. **`publish-pypi`** — runs on tag push or manual dispatch with target `pypi`; publishes to PyPI via OIDC
3. **`publish-testpypi`** — runs on manual dispatch with target `testpypi`; publishes to TestPyPI via OIDC

No API tokens are required — authentication uses PyPI trusted publishing (OIDC).

For setup and the release checklist, see [How to Release](HOW-TO-RELEASE.md).

---

## What the Workflow Does

The following describes the **release** workflow in detail.

1. **`build` job**
   - Checks out the tag (or branch, for manual runs).
   - **Tag releases only:** derives the version from the tag name (`v0.2.0` → `0.2.0`) and writes it to `pyproject.toml` and `src/low/__init__.py`.
   - Installs `.[bootstrap]` (gets the bootstrap dependencies) and `build`.
   - Verifies `src/low/data/sources/low_scraper_speakers.json` exists (committed scraped data — **not** fetched from the web).
   - Runs `python -m low.bootstrap` to regenerate `src/low/data/low_db.json` and the raw source files in `src/low/data/sources/` from upstream (SIL, UN M49, LinguaMeta, Glottolog, CLDR, CIA Factbook, Wikidata), **plus** the committed scraped speaker file.
   - Verifies the DB JSON is non-empty and contains scraped speaker records (`source: "scraped"`).
   - Runs `python -m build` to produce wheel + sdist in `dist/`.
   - Uploads `dist/` as an artifact.

2. **`publish-pypi`** *(or **`publish-testpypi`**)*
   - Downloads the `dist/` artifact.
   - Calls `pypa/gh-action-pypi-publish@release/v1` which authenticates via OIDC and uploads.

Database regeneration happens inside the workflow so every release ships fresh upstream data. The committed `low_db.json` is overwritten in-build; you don't need to regenerate locally before tagging.

**Exception — scraped speaker counts:** unlike CLDR/CIA/LinguaMeta/Wikidata, bootstrap does **not** download scraped data. It reads the versioned file `src/low/data/sources/low_scraper_speakers.json` from the repo checkout. The scraper is never run in this workflow.

For how to refresh scraped data locally, see [Speaker-count scraper](WEB_SCRAPER.md).
