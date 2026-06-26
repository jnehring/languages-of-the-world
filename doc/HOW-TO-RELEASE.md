# How to Release

This project ships to PyPI as [`languages-of-the-world`](https://pypi.org/project/languages-of-the-world/). Releases are automated via [`.github/workflows/release.yml`](../.github/workflows/release.yml): the workflow regenerates the database from upstream sources, builds wheel + sdist, and publishes to PyPI using OIDC trusted publishing (no API tokens).

The import name stays `low` — only the distribution name is `languages-of-the-world`.

For a step-by-step breakdown of what the release workflow does, see [GitHub Workflows](GITHUB_WORKFLOWS.md).

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

The **git tag is the source of truth** for the published version. Tag names must start with `v` (e.g. `v0.2.0`); the workflow strips the prefix and writes `0.2.0` into [`pyproject.toml`](../pyproject.toml) and [`src/low/__init__.py`](../src/low/__init__.py) before building. You do not need to bump those files before tagging — though updating them on `main` after a release keeps local installs and CI in sync with what is on PyPI.

1. Bump the version number in pyproject.toml, commit and push it to GitHub.
2. Wait for the CI to finish building the tests. Make sure `main` is green on CI.
3. Tag and push:
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
4. When the `publish-pypi` job finishes, verify on [pypi.org/project/languages-of-the-world](https://pypi.org/project/languages-of-the-world/)
