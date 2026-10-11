# Justfile for tollan

# Show available commands
list:
    @just --list

install:
    uv sync --locked --all-groups --all-packages --all-extras
    git config core.hooksPath .githooks
    uv run pre-commit install-hooks

rebuild-lockfiles:
    uv lock --upgrade

# Run all the formatting, linting, and testing commands
qa:
    uv run --locked pre-commit run --all-files
    uv run --locked coverage run -m pytest
    just doc-test

# Save a local baseline before changing a hot path.
# Keep Python, dependencies, and machine comparable; saved results are ignored.
benchmark-save name="baseline":
    uv run --locked pytest tests/accessor/pandas/test_model_table_performance.py --benchmark-enable --benchmark-save={{name}}

# Compare with a saved local run; fail only for a slowdown greater than 3x.
benchmark-check baseline:
    uv run --locked pytest tests/accessor/pandas/test_model_table_performance.py --benchmark-enable --benchmark-compare={{baseline}} --benchmark-compare-fail=median:200%

# Run tests with coverage
coverage:
    uv run --locked coverage run -m pytest
    uv run --locked coverage combine
    uv run --locked coverage report -m
    uv run --locked coverage html

# Build the project, useful for checking that packaging is correct
build:
    rm -rf build
    rm -rf dist
    uv build

# Publish to PyPI (manual alternative to GitHub Actions)
publish: build
    uv publish

clean:
    rm -fr build/
    rm -fr dist/
    rm -fr docs/_build/
    rm -fr docs/api/
    rm -fr .eggs/
    find . -name '*.egg-info' -exec rm -fr {} +
    find . -name '*.egg' -exec rm -fr {} +
    find . -name '*.pyc' -exec rm -f {} +
    find . -name '*.pyo' -exec rm -f {} +
    find . -name '*~' -exec rm -f {} +
    find . -name '__pycache__' -exec rm -fr {} +
    rm -f .coverage
    rm -fr htmlcov/
    rm -fr .pytest_cache
    rm -fr .ruff_cache

# Build the docs
doc-build:
    rm -rf docs/api docs/_build
    uv run --locked --group docs sphinx-build -M html docs docs/_build -E -a -n -W --keep-going -T

# Render first, then execute examples in a fresh process using the same doctrees.
# This also avoids autodoc's annotation mutations affecting Pydantic examples.
doc-test: doc-build
    uv run --locked --group docs sphinx-build -M doctest docs docs/_build -n -W --keep-going -T

# Serve docs locally with live reload
doc:
    rm -rf docs/api
    uv run --locked --group docs sphinx-autobuild docs docs/_build/html --port 8888 --open-browser

# Deploy docs to GitHub Pages
doc-deploy: doc-build
    uv run --group docs ghp-import docs/_build/html -r origin -b gh-pages --push --no-jekyll

# Check if project is up to date with the template
# NOTE: --checkout must be passed explicitly; cruft does not read it from .cruft.json (upstream issue)
cruft-check:
    uvx cruft check --checkout v2026

# Update project from the template
cruft-update:
    uvx cruft update --checkout v2026
