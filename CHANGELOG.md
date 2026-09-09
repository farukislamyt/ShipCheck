# Changelog

All notable changes to ShipCheck are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow Semantic Versioning.

## [0.2.0] - 2026-09-09

### Added

- Native composite GitHub Action interface.
- SARIF 2.1.0 output for GitHub Code Scanning.
- Actionable diagnostics for failed and warning checks.
- Stable documented exit codes.
- `.shipcheck.toml` ignore configuration for checks and paths.
- Safe `--fix` automation for conservative project templates.
- Provider detection and validation for Render, Railway, Fly.io, Netlify, and AWS.

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

[0.2.0]: https://github.com/farukislamyt/ShipCheck/releases/tag/v0.2.0
[0.1.0]: https://github.com/farukislamyt/ShipCheck/releases/tag/v0.1.0
