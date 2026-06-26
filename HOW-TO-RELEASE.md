# How to Release

This project ships to PyPI as [`languages-of-the-world`](https://pypi.org/project/languages-of-the-world/). Releases are automated via [`.github/workflows/release.yml`](.github/workflows/release.yml): the workflow regenerates the database from upstream sources, builds wheel + sdist, and publishes to PyPI using OIDC trusted publishing (no API tokens).

The import name stays `low` — only the distribution name is `languages-of-the-world`.

---

## One-Time Setup

You only need to do this once per project.

### 1. Reserve the name on PyPI

- Register on [PyPI](https://pypi.org/account/register/) and [TestPyPI](https://test.pypi.org/account/register/) (separate accounts).
- Enable 2FA on both.

### 2. Configure trusted publishers

On **PyPI** → *Your projects* → *Publishing* → *Add a new pending publisher*:

| Field | Value |
|---|---|
| PyPI project name | `languages-of-the-world` |
| Owner | your GitHub org/user |
| Repository name | `languages-of-the-world` (or whatever the GH repo is named) |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

Repeat on **TestPyPI** with environment name `testpypi`.

No API tokens are needed — GitHub Actions authenticates to PyPI via OIDC.

### 3. Create GitHub environments

In the repo → *Settings* → *Environments* → create two environments:

- `pypi`
- `testpypi`

For `pypi`, optionally add a required reviewer so production publishes require manual approval.

---

## Cutting a Release

### Standard release (production PyPI)

The **git tag is the source of truth** for the published version. Tag names must start with `v` (e.g. `v0.2.0`); the workflow strips the prefix and writes `0.2.0` into [`pyproject.toml`](pyproject.toml) and [`src/low/__init__.py`](src/low/__init__.py) before building. You do not need to bump those files before tagging — though updating them on `main` after a release keeps local installs and CI in sync with what is on PyPI.

1. Make sure `main` is green on CI.
2. Tag and push:
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
3. *(Optional)* Create a GitHub release for the tag (e.g. tag `v0.2.0`, title `0.2.0`). This is cosmetic; the workflow is triggered by the tag push, not the release.
4. The `Release` workflow fires automatically on the `v*` tag. Watch it in the Actions tab.
5. When the `publish-pypi` job finishes, verify on [pypi.org/project/languages-of-the-world](https://pypi.org/project/languages-of-the-world/) and install:
   ```bash
   pip install --upgrade languages-of-the-world
   python -c "import low; db = low.LanguagesOfTheWorld(); print(len(db.languages), 'languages')"
   ```

### Dry-run via TestPyPI

Use this for the first release or any time you want to validate the pipeline without polluting PyPI.

Manual runs do **not** read a tag — they use whatever `version` is already in `pyproject.toml` on the selected branch.

1. In GitHub → *Actions* → *Release* → *Run workflow*.
2. Pick branch (`main`), set **Publish target** to `testpypi`, click *Run*.
3. After it succeeds, install from TestPyPI to verify:
   ```bash
   pip install --index-url https://test.pypi.org/simple/ \
               --extra-index-url https://pypi.org/simple/ \
               languages-of-the-world
   ```

The `extra-index-url` is needed because TestPyPI doesn't mirror runtime dependencies.

### Manual production publish

If you need to re-publish without cutting a new tag (rare — versions are immutable on PyPI, so this only works for a never-published version):

1. *Actions* → *Release* → *Run workflow* → target `pypi`.

---

## What the Workflow Does

1. **build job**
   - Checks out the tag (or branch, for manual runs).
   - **Tag releases only:** derives the version from the tag name (`v0.2.0` → `0.2.0`) and writes it to `pyproject.toml` and `src/low/__init__.py`.
   - Installs `.[bootstrap]` (gets the bootstrap dependencies) and `build`.
   - Verifies `src/low/data/sources/low_scraper_speakers.json` exists (committed scraped data — **not** fetched from the web).
   - Runs `python -m low.bootstrap` to regenerate `src/low/data/low_db.json` and the raw source files in `src/low/data/sources/` from upstream (SIL, UN M49, LinguaMeta, Glottolog, CLDR, CIA Factbook, Wikidata), **plus** the committed scraped speaker file.
   - Verifies the DB JSON is non-empty and contains scraped speaker records (`source: "scraped"`).
   - Runs `python -m build` to produce wheel + sdist in `dist/`.
   - Uploads `dist/` as an artifact.

2. **publish-pypi** *(or **publish-testpypi**)*
   - Downloads the `dist/` artifact.
   - Calls `pypa/gh-action-pypi-publish@release/v1` which authenticates via OIDC and uploads.

Database regeneration happens inside the workflow so every release ships fresh upstream data. The committed `low_db.json` is overwritten in-build; you don't need to regenerate locally before tagging.

**Exception — scraped speaker counts:** unlike CLDR/CIA/LinguaMeta/Wikidata, bootstrap does **not** download scraped data. It reads the versioned file `src/low/data/sources/low_scraper_speakers.json` from the repo checkout. The scraper is never run in this workflow.

---

## Refreshing Scraped Speaker Data

Run locally (or via the optional *Update scraped speakers* workflow in Actions) when you want new web-scraped counts:

```bash
pip install "languages-of-the-world[scraper]"
# SERPER_API_KEY and GEMINI_API_KEY in .env

low-scraper run --rounds 3
low-scraper import    # → src/low/data/sources/low_scraper_speakers.json

git add src/low/data/sources/low_scraper_speakers.json
git commit -m "Update scraped speaker counts"
git push
```

Then cut a release as usual. Scraper updates are decoupled from release cadence — only commit the JSON when you re-scrape.

Working files under `scraper-data/` are gitignored and are **not** used by bootstrap or the release workflow.

---

## Versioning

| Trigger | Version source |
|---|---|
| Tag push (`v*`) | Tag name without the `v` prefix (e.g. `v0.2.0` → `0.2.0`) |
| Manual workflow dispatch | `project.version` in `pyproject.toml` on the selected branch |

After a production release, consider bumping `pyproject.toml` and `src/low/__init__.py` on `main` so the repo reflects the latest shipped version. The CI-only update during a tag build is not committed back to git.

This project follows [SemVer](https://semver.org/):

- **Patch** (`0.1.0` → `0.1.1`) — bug fixes, data refresh only.
- **Minor** (`0.1.0` → `0.2.0`) — new fields / collections / sources, backwards-compatible.
- **Major** (`0.1.0` → `1.0.0`) — breaking changes to the public API (entity properties, collection methods).

PyPI does not allow re-uploading the same version. If a release is broken, yank it on PyPI and ship `X.Y.Z+1`.

---

## Troubleshooting

### "User 'github-actions' is not allowed to upload"

Trusted publisher isn't configured or the environment name in the workflow doesn't match the one registered on PyPI. Re-check step 2 of one-time setup.

### Release fails: missing scraped speaker records

The build job checks that `src/low/data/sources/low_scraper_speakers.json` exists and that `low_db.json` contains records with `source: "scraped"` after bootstrap. If this fails:

1. Run `low-scraper import` locally (after a scrape) or restore the file from git history.
2. Commit and push `src/low/data/sources/low_scraper_speakers.json`.
3. Re-run the release workflow.

### Bootstrap fails on Wikidata (HTTP 429)

The Wikidata fetcher is wrapped in try/except — the release proceeds with `wikidata_speakers.json` empty and LinguaMeta-only `Language.speaker_count`. If you want fresh Wikidata data, re-run the workflow when WDQS is healthy.

### Bootstrap fails on another source

The job will exit non-zero and the publish step won't run. Check the failing source's URL — upstreams occasionally rename or restructure files. Fix the parser locally, push, then re-tag.

### Version already exists on PyPI

You can't overwrite. Bump the version, re-tag, re-push.

### Workflow didn't trigger on tag push

Make sure you pushed the tag (`git push --tags` or `git push origin vX.Y.Z`). A `git push` without `--tags` does not include them.
