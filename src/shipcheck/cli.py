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


def _framework(path: Path) -> str:
    if (path / "manage.py").exists():
        return "Django"
    if (path / "pyproject.toml").exists() or (path / "requirements.txt").exists():
        try:
            files = [p for p in (path / "pyproject.toml", path / "requirements.txt") if p.exists()]
            text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in files).lower()
            for name, label in (("fastapi", "FastAPI"), ("flask", "Flask"), ("django", "Django")):
                if name in text:
                    return label
        except OSError:
            pass
        return "Python"
    package = path / "package.json"
    if package.exists():
        try:
            data = json.loads(package.read_text(encoding="utf-8", errors="ignore"))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            for name, label in (("next", "Next.js"), ("react", "React"), ("vue", "Vue"), ("express", "Express")):
                if name in deps:
                    return label
        except (OSError, json.JSONDecodeError):
            pass
        return "Node.js"
    return "Unknown"


def _env_status(path: Path) -> str:
    env = path / ".env"
    template = next((path / name for name in (".env.example", ".env.template") if (path / name).exists()), None)
    if not env.exists() and template is None:
        return "WARN"
    if not env.exists():
        return "WARN"
    if template is None:
        return "PASS"
    try:
        env_keys = {line.split("=", 1)[0].strip() for line in env.read_text(errors="ignore").splitlines() if "=" in line and line.strip() and not line.lstrip().startswith("#")}
        template_keys = {line.split("=", 1)[0].strip() for line in template.read_text(errors="ignore").splitlines() if "=" in line and line.strip() and not line.lstrip().startswith("#")}
        return "PASS" if template_keys <= env_keys else "WARN"
    except OSError:
        return "WARN"


def _deployment_files(path: Path) -> str:
    names = ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml", "vercel.json", "Procfile")
    return "PASS" if any((path / name).exists() for name in names) else "WARN"


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
        ("Framework detection", "PASS" if _framework(path) != "Unknown" else "WARN"),
        ("README", "PASS" if any((path / name).exists() for name in ("README.md", "README.rst", "README")) else "WARN"),
        (".gitignore", "PASS" if (path / ".gitignore").exists() else "WARN"),
        ("Environment configuration", _env_status(path)),
        ("Dependency manifest", _has_dependency_manifest(path)),
        ("Deployment config", _deployment_files(path)),
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
    payload = {"project": path.name, "framework": _framework(path), "score": score, "checks": [{"name": n, "status": s} for n, s in checks], "secret_findings": secrets}

    if json_output:
        typer.echo(json.dumps(payload, indent=2))
        raise typer.Exit()

    console.print(Panel.fit("[bold]ShipCheck[/bold]\nPre-deployment health check"))
    console.print(f"\n[bold]Project:[/bold] {path.name}")
    console.print(f"[bold]Framework:[/bold] {_framework(path)}\n")
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
