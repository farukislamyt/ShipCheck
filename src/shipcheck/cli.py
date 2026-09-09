from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(help="Pre-deployment health checks for software projects.")
console = Console()

SECRET_PATTERNS = {
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "Generic API key": re.compile(r"(?i)(api[_-]?key|secret[_-]?key)\s*[:=]\s*[\"'][^\"']{12,}[\"']"),
}

IGNORED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "dist", "build"}
SCANNABLE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yaml", ".yml", ".toml", ".ini", ".env", ".txt"}


def _git_clean(path: Path) -> str:
    try:
        result = subprocess.run(["git", "-C", str(path), "status", "--porcelain"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return "WARN"
    if result.returncode != 0:
        return "WARN"
    return "PASS" if not result.stdout.strip() else "WARN"


def _has_dependency_manifest(path: Path) -> str:
    manifests = ("pyproject.toml", "requirements.txt", "poetry.lock", "uv.lock", "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "go.mod", "go.sum", "Cargo.toml", "Cargo.lock")
    return "PASS" if any((path / name).exists() for name in manifests) else "WARN"


def _has_tests(path: Path) -> str:
    if any((path / name).is_dir() for name in ("tests", "test", "spec")):
        return "PASS"
    return "PASS" if any(p.name.startswith(("test_", "spec_")) for p in path.rglob("*") if p.is_file()) else "WARN"


def _secret_findings(path: Path) -> list[str]:
    findings: list[str] = []
    for file in path.rglob("*"):
        if not file.is_file() or any(part in IGNORED_DIRS for part in file.parts) or file.suffix.lower() not in SCANNABLE_SUFFIXES:
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{file.relative_to(path)}: {label}")
    return findings


def check_project(path: Path) -> list[tuple[str, str]]:
    return [
        ("Project directory", "PASS" if path.is_dir() else "FAIL"),
        ("Git repository", "PASS" if (path / ".git").exists() else "WARN"),
        ("Git working tree", _git_clean(path) if (path / ".git").exists() else "WARN"),
        ("README", "PASS" if any((path / name).exists() for name in ("README.md", "README.rst", "README")) else "WARN"),
        (".gitignore", "PASS" if (path / ".gitignore").exists() else "WARN"),
        ("Environment template", "PASS" if any((path / name).exists() for name in (".env.example", ".env.template")) else "WARN"),
        ("Dependency manifest", _has_dependency_manifest(path)),
        ("Tests", _has_tests(path)),
        ("Secrets scan", "FAIL" if _secret_findings(path) else "PASS"),
    ]


@app.command()
def scan(
    path: Path = typer.Argument(Path("."), exists=True, file_okay=False, dir_okay=True),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Scan PATH and report deployment readiness checks."""
    path = path.resolve()
    checks = check_project(path)
    secrets = _secret_findings(path)
    passed = sum(status == "PASS" for _, status in checks)
    score = round((passed / len(checks)) * 100)
    payload = {"project": path.name, "score": score, "checks": [{"name": n, "status": s} for n, s in checks], "secret_findings": secrets}

    if json_output:
        typer.echo(json.dumps(payload, indent=2))
        raise typer.Exit()

    console.print(Panel.fit("[bold]ShipCheck[/bold]\nPre-deployment health check"))
    console.print(f"\n[bold]Project:[/bold] {path.name}\n")
    for name, status in checks:
        icon = {"PASS": "[green]✓[/green]", "WARN": "[yellow]⚠[/yellow]", "FAIL": "[red]✗[/red]"}[status]
        console.print(f"  {icon} {name}")
    if secrets:
        console.print("\n[bold red]Potential secrets:[/bold red]")
        for finding in secrets[:10]:
            console.print(f"  [red]•[/red] {finding}")
    console.print(f"\n[bold]Deployment Readiness:[/bold] {score}%")


if __name__ == "__main__":
    app()
