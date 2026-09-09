# Changelog

All notable changes to ShipCheck are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow Semantic Versioning.

## [0.1.0] - 2026-09-09

### Added

- Project, Git, framework, README, `.gitignore`, and environment checks.
- Dependency manifest and deployment configuration detection.
- Provider-aware validation for Vercel, Docker, and GitHub Actions.
- Secret scanning for common credential formats.
- Weighted deployment-readiness scoring.
- Configurable readiness thresholds through `.shipcheck.toml` and `--threshold`.
- Deployment gate mode with a non-zero exit code when readiness fails.
- Rich terminal reports and JSON output.
- Automated test coverage and GitHub Actions CI across Python 3.11–3.13.
- Python package build and CLI smoke-test validation in CI.

[0.1.0]: https://github.com/farukislamyt/ShipCheck/releases/tag/v0.1.0
