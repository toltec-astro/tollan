# tollan

A shared utility package for TolTEC project and astronomy pipeline in general.

[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-BSD--3--Clause-green.svg)](https://github.com/toltec-astro/tollan/blob/master/LICENSE)

## Overview

Tollan is a Python utility library designed for astronomy projects, providing:

- **Accessor System**: Schema-based data access abstraction for xarray, pandas, and netCDF4
- **Configuration System**: Multi-source configuration with validation
- **Plotting Utilities**: Plotly helpers for multi-panel figures
- **Pipeline Utilities**: Context handler mixins for pipeline
- **General Utilities**: CLI, logging, formatting, etc.

## Requirements

- **Python**: 3.13+
- **Core**: pydantic, pyyaml, typer, loguru
- **Astronomy**: astropy, astroquery
- **Plotting**: matplotlib, plotly, dash

## Installation

### From Source (Development)

```bash
# Clone repository
git clone https://github.com/toltec-astro/tollan.git
cd tollan

# Install with uv (recommended)
uv pip install -e .

# Or with pip
pip install -e .
```

## Quick Start

```python
from tollan.config import RuntimeContext
from pathlib import Path

# Multi-source configuration with precedence
rc = RuntimeContext(
    config_sources=[
        {"format": "dict", "source": {"host": "localhost"}, "order": 0},
        {"format": "yaml", "source": Path("config.yaml"), "order": 10},
        {"format": "envfile", "source": Path(".env"), "order": 20},
    ]
)

# Access merged configuration
config = rc.config_dict
print(config["host"])
```

## Development

```bash
# Install with all dependencies and pre-commit hooks
just install

# Run quality checks (formatting, linting, tests)
just qa

# Run tests with coverage
just coverage

# Build package
just build

# Build and serve documentation locally
just doc

# Clean build artifacts
just clean
```

## License

BSD 3-Clause License - see [LICENSE](https://github.com/toltec-astro/tollan/blob/master/LICENSE)

## Links

- **GitHub**: https://github.com/toltec-astro/tollan
- **Issues**: https://github.com/toltec-astro/tollan/issues
