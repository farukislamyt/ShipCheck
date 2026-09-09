# ShipCheck

> Pre-deployment health checks for modern software projects.

ShipCheck is a developer-first CLI that scans a project before deployment and highlights configuration problems, missing files, exposed secrets, dependency issues, and other deployment risks.

## Status

🚧 Early development — v0.1 is being built.

## Planned checks

- Git repository and working-tree status
- `.gitignore` and environment configuration
- Secret detection
- Dependency and lockfile checks
- Test and CI/CD detection
- Docker configuration
- Project documentation

## Planned usage

```bash
shipcheck .
```

Machine-readable output will also be supported:

```bash
shipcheck . --json
```

## Development

Clone the repository and install the project in editable mode once the package is available.

```bash
git clone https://github.com/farukislamyt/ShipCheck.git
cd ShipCheck
```

## Roadmap

- [ ] Project scanner
- [ ] Check framework
- [ ] Git checks
- [ ] Environment checks
- [ ] Secret detection
- [ ] Dependency checks
- [ ] Test/CI detection
- [ ] Rich terminal report
- [ ] JSON output
- [ ] Automated test suite
- [ ] First PyPI release

## License

MIT License.
