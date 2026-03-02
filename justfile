# Justfile for tollan

# Show available commands
list:
    @just --list

install:
    uv sync --all-groups --all-packages --all-extras
    git config core.hooksPath .githooks
    uv run pre-commit install-hooks

rebuild-lockfiles:
    uv lock --upgrade

# Run all the formatting, linting, and testing commands
qa:
    uv run pre-commit run --all-files
    uv run coverage run -m pytest .

# Run coverage, and build to HTML
coverage:
    uv run coverage run -m pytest .
    uv run coverage report -m
    uv run coverage html

# Build the project, useful for checking that packaging is correct
build:
    rm -rf build
    rm -rf dist
    uv build

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
    uv run sphinx-build -M html docs docs/_build -T

# Serve docs locally
doc: doc-build
    uv run mkdocs serve -a localhost:8888

# Deploy docs
doc-deploy: doc-build
    uv run mkdocs gh-deploy --force
