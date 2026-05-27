# EV Battery Chemistry Trade-Flow Analysis

A public research web application for exploring electric-vehicle battery critical-mineral supply-chain trade flows, conversion-factor optimization results, and vulnerability-index views across selected battery chemistry and mineral cases.

## Live Website

The deployed website is available here:

[https://ev-battery-chemistry-trade-flow-analysis.onrender.com/](https://ev-battery-chemistry-trade-flow-analysis.onrender.com/)

## Overview

This repository hosts the public web application and supporting code for visualizing and analyzing EV battery critical-mineral supply-chain flows. The application is designed to help users explore how battery minerals move through multi-stage supply chains, from upstream production and trade flows to downstream cathode-related production views.

The website currently supports interactive Sankey diagrams, selected conversion-factor optimization outputs, coefficient-level inspection, and vulnerability-index dashboards. It is intended as a research visualization and analysis interface, not as a real-time market-monitoring, investment, or policy dashboard.

## Research Background

This project is associated with the Carnegie Mellon University Vehicle Electrification Group:

[https://www.cmu.edu/cit/veg/](https://www.cmu.edu/cit/veg/)

It builds on the research context of the Nature Communications article:

**“Electric vehicle battery chemistry affects supply chain disruption vulnerabilities”**  
[https://www.nature.com/articles/s41467-024-46418-1](https://www.nature.com/articles/s41467-024-46418-1)

It also follows from the earlier public repository associated with that article:

[acheng98/ev-battery-chemistry-supply-chain-vulnerabilities](https://github.com/acheng98/ev-battery-chemistry-supply-chain-vulnerabilities)

The current repository extends this line of work as a public-facing web and analysis interface for exploring EV battery chemistry trade-flow cases, optimization outputs, and vulnerability-index views.

## Main Features

### Sankey Diagram Exploration

The application provides interactive Sankey diagrams for EV battery critical-mineral supply-chain flows. Users can explore supply-chain stages, countries, trade links, and selected mineral-year-result combinations. The diagrams are designed to show how material flows propagate through the modeled supply chain.

### Conversion Factor Optimization Analysis

The website includes analysis views for selected conversion-factor optimization results. These views compare original and optimized flow snapshots and summarize changes in flow balance, unknown or special-node behavior, and stage-level outputs.

### Coefficient Explorer

The Coefficient Explorer allows users to inspect selected conversion coefficients used in the optimization workflow. Where available, it shows recommended values, bounds, exposure, and related flow changes.

### Vulnerability Index Dashboard

The Vulnerability Index dashboard presents country-level vulnerability-index results and method-case comparisons. These views are intended to support exploratory analysis of how country involvement in production or trade may affect downstream battery-material supply-chain exposure.

### Country VI and Sensitivity-Style Analysis

The application includes country-level VI views and a sensitivity-style analysis interface. These views are useful for comparing country exposure, baseline deltas, and selected scenario-style changes. Some advanced analysis functions may depend on runtime data availability and access mode.

## Repository Structure

The repository is organized around a Python web/runtime architecture:

```text
.
├── apps/
│   └── web/                         # Public ASGI web entrypoint
├── src/
│   └── trade_flow/
│       ├── web/                     # Web application, routes, templates, static assets
│       ├── domain/                  # Runtime contracts, manifest models, validation helpers
│       ├── runtime/                 # Runtime bundle loading and dataset access
│       ├── baseline/                # Baseline analysis logic
│       ├── conversion_factor_optimization/
│       │   └── ...                  # First-generation conversion-factor optimization engine
│       ├── optimization/            # Shared optimization-facing interfaces and helpers
│       ├── metals/                  # Metal-specific adapters and extension points
│       ├── pipelines/               # Higher-level pipeline facades
│       ├── publishing/              # Runtime bundle publishing and validation helpers
│       └── legacy_site/             # Compatibility namespace for earlier site logic
├── configs/                         # Configuration files and runtime contracts
├── schemas/                         # Data/schema contracts
├── docs/                            # Architecture notes and runbooks
├── scripts/                         # Validation, smoke-test, and maintenance scripts
├── tests/                           # Unit and integration-style tests
├── fixtures/                        # Minimal public examples or test fixtures
├── pyproject.toml                   # Python package metadata and dependencies
├── requirements.txt                 # Runtime dependency list
├── render.yaml                      # Render deployment configuration
└── README.md
```

The exact contents may evolve as the public web application, runtime bundle format, and optimization workflow are updated.

## Data and Runtime Note

Some generated runtime data used by the deployed website may be managed separately from the public source-code repository. This separation is intentional: the public repository contains the web application, analysis code, configuration contracts, documentation, and selected public fixtures, while deployed runtime data may be built, versioned, or mounted separately.

Do not assume that all private, generated, intermediate, or deployment-specific datasets are included in this repository. Running the full website locally may require access to a compatible runtime data bundle and the correct environment-variable configuration.

Important runtime-related environment variables may include:

```text
APP_ENV
RUNTIME_ROOT
BATTERY_SITE_APP_DATA_DIR
BATTERY_SITE_OUTPUT_VERSIONS_DIR
BATTERY_SITE_DATA_ROOT
BATTERY_SITE_REFERENCE_FILE
BATTERY_SITE_ORIGINAL_DATA_ROOT
BATTERY_SITE_FIRST_OPTIMIZATION_DATA_ROOT
BATTERY_SITE_INSTANCE_DIR
BATTERY_SITE_DATASET_CONFIG
BATTERY_SITE_ANALYST_PASSWORD
BATTERY_SITE_STRICT_STARTUP
```

## Local Development

A typical local setup, if the required runtime data is available, is:

```bash
git clone https://github.com/ZZZZZZZJL/EV-Battery-Chemistry-Trade-Flow-Analysis.git
cd EV-Battery-Chemistry-Trade-Flow-Analysis

python -m venv .venv
source .venv/bin/activate
pip install -e .
```

On Windows PowerShell, the virtual environment activation command is typically:

```powershell
.venv\Scripts\Activate.ps1
```

Before running the application, configure the runtime data paths. For example:

```bash
export APP_ENV=dev
export RUNTIME_ROOT=/path/to/runtime
export BATTERY_SITE_APP_DATA_DIR=/path/to/runtime/current/app_data
export BATTERY_SITE_OUTPUT_VERSIONS_DIR=/path/to/runtime/current/output_versions
export BATTERY_SITE_DATA_ROOT=/path/to/shared/reference/data
export BATTERY_SITE_INSTANCE_DIR=instance
```

On Windows PowerShell:

```powershell
$env:APP_ENV = "dev"
$env:RUNTIME_ROOT = "C:\path\to\runtime"
$env:BATTERY_SITE_APP_DATA_DIR = "C:\path\to\runtime\current\app_data"
$env:BATTERY_SITE_OUTPUT_VERSIONS_DIR = "C:\path\to\runtime\current\output_versions"
$env:BATTERY_SITE_DATA_ROOT = "C:\path\to\shared\reference\data"
$env:BATTERY_SITE_INSTANCE_DIR = "instance"
```

Then start the FastAPI application with Uvicorn:

```bash
uvicorn --app-dir . apps.web.app:app --host 127.0.0.1 --port 8147
```

Open the local site at:

[http://127.0.0.1:8147/](http://127.0.0.1:8147/)

A deployment-style command is also defined in `render.yaml`:

```bash
uvicorn --app-dir . apps.web.app:app --host 0.0.0.0 --port $PORT
```

If runtime data is unavailable or incomplete, some pages, tables, or analysis views may not load. The `/healthz` endpoint can be used to inspect runtime readiness.

## Verification

Typical local checks may include:

```bash
python -B scripts/validate_repo.py
python -B -m unittest discover -s tests
```

If the runtime data bundle is available, a smoke test may also be run:

```bash
python -B scripts/smoke_test_app.py
```

## Citation and Acknowledgments

This repository is part of a research software workflow associated with the CMU Vehicle Electrification Group.

Please cite or acknowledge the following research context when using this project in academic or public-facing work:

Cheng, A. L., Fuchs, E. R. H., Karplus, V. J., & Michalek, J. J. (2024). **Electric vehicle battery chemistry affects supply chain disruption vulnerabilities.** *Nature Communications*, 15, 2143.  
[https://www.nature.com/articles/s41467-024-46418-1](https://www.nature.com/articles/s41467-024-46418-1)

Earlier public code and data repository:

[acheng98/ev-battery-chemistry-supply-chain-vulnerabilities](https://github.com/acheng98/ev-battery-chemistry-supply-chain-vulnerabilities)

Research group:

[CMU Vehicle Electrification Group](https://www.cmu.edu/cit/veg/)

## License and Reuse

The license for this repository should be confirmed by the maintainers. If a formal license file is added, users should follow the terms stated in that file.

Until then, please contact the repository maintainer before reusing, redistributing, or extending the code or generated outputs beyond standard academic reference and review.

