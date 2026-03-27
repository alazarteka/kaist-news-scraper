# Release

This repository is shaped to produce installable wheels and source distributions.

## Pre-Release Checklist

1. Update the version in `pyproject.toml` and `src/herald/__init__.py`.
2. Run the test suite.
3. Build the package.
4. Smoke-test the wheel in a clean virtual environment.
5. Tag the release in git.

## Commands

Run tests:

```bash
uv run python -m unittest discover -s tests -v
```

Build source and wheel artifacts:

```bash
uv build
```

Install the wheel into a clean environment:

```bash
python3 -m venv .release-venv
.release-venv/bin/pip install dist/herald-*.whl
.release-venv/bin/herald --version
```

## GitHub Flow

After building and testing:

1. commit the version bump
2. create an annotated tag such as `v0.3.0`
3. push the branch and tag
4. attach `dist/` artifacts to the GitHub release if you want installable binaries directly from the release page

Users can then install from either:

```bash
pip install git+https://github.com/alazarteka/kaist-news-scraper.git@v0.3.0
```

or from the wheel artifact:

```bash
pip install herald-0.3.0-py3-none-any.whl
```
