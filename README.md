# ShipCheck

> Pre-deployment health checks for modern software projects.

ShipCheck is a developer-first CLI that scans a project before deployment and highlights configuration problems, missing files, exposed secrets, dependency issues, and other deployment risks.

## Status

🚧 Early development — v0.1.0 is the first release candidate.

## What it checks

- Git repository and working-tree status
- Framework detection
- `.gitignore` and environment configuration
- Secret detection
- Dependency manifests
- Deployment configuration
- Provider-specific deployment configuration
- Tests and CI/CD signals
- Project documentation

## Installation

### From source

```bash
git clone https://github.com/farukislamyt/ShipCheck.git
cd ShipCheck
python -m pip install -e ".[dev]"
```

### From PyPI

Once the first PyPI release is published:

```bash
python -m pip install shipcheck
```

## Usage

Run a readiness report:

```bash
shipcheck .
```

Machine-readable JSON output:

```bash
shipcheck . --json
```

Use the deployment gate in CI/CD. It exits with status `1` when a check fails or the readiness score is below the configured threshold:

```bash
shipcheck . --gate
```

Override the default readiness threshold of 80:

```bash
shipcheck . --gate --threshold 90
```

## Configuration

Create `.shipcheck.toml` in the project root to persist the readiness threshold:

```toml
[shipcheck]
threshold = 80
```

The CLI `--threshold` option takes precedence over the configuration file.

## Release process

Releases are tag-driven. The GitHub Actions release workflow validates that the tag version matches `pyproject.toml`, builds the package, runs `twine check`, creates a GitHub Release, and publishes the distributions to PyPI using trusted publishing.

For example, after updating the package version and changelog:

```bash
git tag v0.1.0
git push origin v0.1.0
```

See [CHANGELOG.md](CHANGELOG.md) for release history.

## Development

Install development dependencies and run the checks locally:

```bash
python -m pip install -e ".[dev]"
ruff check .
pytest -q
python -m build
```

## License

MIT License.
