# ShipCheck

> Know if your project is ready to deploy.

ShipCheck is a developer-first CLI that scans a project before deployment and highlights configuration problems, missing files, exposed secrets, dependency issues, and deployment risks.

## Status

🚀 **v0.2.0** — CI/CD integration, SARIF, diagnostics, provider expansion, and safe fixes.

## What it checks

- Git repository and working-tree status
- Framework detection
- `.gitignore` and environment configuration
- Secret detection
- Dependency manifests
- Deployment configuration
- Provider-specific configuration for Vercel, Docker, GitHub Actions, Render, Railway, Fly.io, Netlify, AWS, and Procfile-compatible targets
- Tests and CI/CD signals
- Project documentation

## Installation

### From PyPI

```bash
python -m pip install shipcheck-cli
```

### From source

```bash
git clone https://github.com/farukislamyt/ShipCheck.git
cd ShipCheck
python -m pip install -e ".[dev]"
```

## CLI usage

```bash
shipcheck .
shipcheck . --gate
shipcheck . --gate --threshold 90
```

Machine-readable output:

```bash
shipcheck . --format json
shipcheck . --format sarif > shipcheck-results.sarif
```

`--json` remains supported as a compatibility alias for JSON output.

### Diagnostics

Non-passing checks include actionable recommendations in terminal and JSON output. Secret findings identify only the file and credential type; secret values are never printed.

### Safe fixes

Use `--fix` for narrowly scoped local fixes that do not overwrite application code:

```bash
shipcheck . --fix
```

Currently this can create a conservative `.gitignore` and copy `.env.template` to `.env.example` when the latter is missing. Always review generated files before committing them.

## Configuration

Create `.shipcheck.toml`:

```toml
[shipcheck]
threshold = 80

[shipcheck.ignore]
checks = ["Tests"]
paths = ["examples/", "fixtures/"]
```

The CLI `--threshold` option takes precedence over the configuration file. Invalid configuration returns exit code `2`.

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | Scan completed and the deployment gate passed or was not requested |
| 1 | `--gate` blocked deployment |
| 2 | Invalid `.shipcheck.toml` configuration |
| 3 | Reserved for usage-level failures |

## GitHub Action

ShipCheck can run as a native composite action:

```yaml
name: ShipCheck

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read
  security-events: write

jobs:
  shipcheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: farukislamyt/ShipCheck@v0.2.0
        with:
          threshold: "80"
          gate: "true"
          format: sarif
```

The action installs the released `shipcheck-cli` package and uploads SARIF results to GitHub Code Scanning.

## Release process

Releases are tag-driven. The GitHub Actions release workflow validates the tag against `pyproject.toml`, builds the package, validates distributions, creates the GitHub Release, and publishes to PyPI using trusted publishing.

```bash
git tag v0.2.0
git push origin v0.2.0
```

See [CHANGELOG.md](CHANGELOG.md) for release history.

## Development

```bash
python -m pip install -e ".[dev]"
ruff check .
pytest -q
python -m build
```

## License

MIT License.
