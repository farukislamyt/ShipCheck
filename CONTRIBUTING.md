# Contributing to ShipCheck

Thanks for contributing.

## Development setup

ShipCheck requires Python 3.11 or newer.

```bash
git clone https://github.com/farukislamyt/ShipCheck.git
cd ShipCheck
python -m pip install -e ".[dev]"
```

## Before opening a pull request

Run the same core checks used by CI:

```bash
ruff check .
pytest -q
python -m build
```

Keep changes focused and add or update tests for behavior changes.

## Pull requests

Please include:

- A concise description of the problem and solution.
- Tests covering new or changed behavior.
- Documentation updates when the CLI, configuration, or user-facing behavior changes.
- Any compatibility or migration considerations.

Do not commit credentials, API keys, private keys, `.env` files containing secrets, build artifacts, or local virtual environments.

## Commit and code style

Use clear, imperative commit messages such as `feat: add provider validation` or `fix: handle malformed workflow YAML`.

Follow the existing Python style and Ruff configuration in `pyproject.toml`.

## Security issues

Do not disclose security vulnerabilities in public issues. Follow the process in [SECURITY.md](SECURITY.md).
