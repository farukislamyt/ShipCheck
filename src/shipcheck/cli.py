from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(help="Pre-deployment health checks for software projects.")
console = Console()

SECRET_PATTERNS = {
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"),
    "Stripe live key": re.compile(r"\bsk_live_[0-9A-Za-z]{16,}\b"),
    "Generic API key": re.compile(r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*[\"']([^\"']{16,})[\"']"),
}

IGNORED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "dist", "build", ".mypy_cache", ".ruff_cache"}
SCANNABLE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yaml", ".yml", ".toml", ".ini", ".env", ".txt", ".cfg", ".conf"}
PLACEHOLDER_VALUES = {"example-placeholder", "changeme", "change-me", "your-api-key", "your-secret-key", "replace-me"}

CHECK_WEIGHTS = {
    "Project directory": 5,
    "Git repository": 10,
    "Git working tree": 10,
    "Framework detection": 5,
    "README": 5,
    ".gitignore": 10,
    "Environment configuration": 10,
    "Dependency manifest": 10,
    "Deployment config": 10,
    "Provider validation": 5,
    "Tests": 10,
    "Secrets scan": 10,
}
DEFAULT_THRESHOLD = 80


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
    return "PASS" if _deployment_provider(path) != "Unknown" else "WARN"


def _deployment_provider(path: Path) -> str:
    if (path / "vercel.json").exists() or (path / ".vercel").is_dir():
        return "Vercel"
    if any((path / name).exists() for name in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")):
        return "Docker"
    if (path / "Procfile").exists():
        return "Procfile-compatible"
    workflows = path / ".github" / "workflows"
    if workflows.is_dir() and any(p.suffix in {".yml", ".yaml"} for p in workflows.iterdir() if p.is_file()):
        return "GitHub Actions"
    return "Unknown"


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def _load_yaml_mapping(path: Path) -> dict | None:
    text = _read_text(path)
    if text is None:
        return None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def _validate_vercel(path: Path) -> str:
    config = path / "vercel.json"
    if not config.exists():
        return "WARN"
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "FAIL"
    return "PASS" if isinstance(data, dict) else "FAIL"


def _validate_docker(path: Path) -> str:
    dockerfile = path / "Dockerfile"
    if dockerfile.exists():
        text = _read_text(dockerfile)
        if text is None:
            return "WARN"
        return "PASS" if re.search(r"(?m)^\s*FROM\s+\S+", text) else "FAIL"
    compose = next((path / name for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml") if (path / name).exists()), None)
    if compose is None:
        return "WARN"
    data = _load_yaml_mapping(compose)
    return "PASS" if data is not None and isinstance(data.get("services"), dict) and data["services"] else "FAIL"


def _validate_github_actions(path: Path) -> str:
    workflows = path / ".github" / "workflows"
    files = [p for p in workflows.iterdir() if p.is_file() and p.suffix in {".yml", ".yaml"}] if workflows.is_dir() else []
    if not files:
        return "WARN"
    for workflow in files:
        data = _load_yaml_mapping(workflow)
        if data is None:
            return "FAIL"
        if not isinstance(data.get("name"), str) or not data.get("name", "").strip():
            return "FAIL"
        if "on" not in data and True not in data:
            return "FAIL"
        jobs = data.get("jobs")
        if not isinstance(jobs, dict) or not jobs:
            return "FAIL"
    return "PASS"


def _provider_validation(path: Path, provider: str) -> str:
    if provider == "Vercel":
        return _validate_vercel(path)
    if provider == "Docker":
        return _validate_docker(path)
    if provider == "GitHub Actions":
        return _validate_github_actions(path)
    if provider == "Procfile-compatible":
        procfile = path / "Procfile"
        text = _read_text(procfile)
        return "PASS" if text and any(re.match(r"^\s*[A-Za-z][A-Za-z0-9_-]*\s*:", line) for line in text.splitlines()) else "FAIL"
    return "WARN"


def _secret_findings(path: Path) -> list[str]:
    findings: list[str] = []
    seen: set[tuple[str, str]] = set()
    for file in path.rglob("*"):
        if not file.is_file() or any(part in IGNORED_DIRS for part in file.parts) or file.suffix.lower() not in SCANNABLE_SUFFIXES:
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            match = pattern.search(text)
            if match and not (label == "Generic API key" and match.group(2).strip().lower() in PLACEHOLDER_VALUES):
                finding = (str(file.relative_to(path)), label)
                if finding not in seen:
                    findings.append(f"{finding[0]}: {finding[1]}")
                    seen.add(finding)
    return findings


def check_project(path: Path) -> list[tuple[str, str]]:
    provider = _deployment_provider(path)
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
        ("Provider validation", _provider_validation(path, provider)),
        ("Tests", _has_tests(path)),
        ("Secrets scan", "FAIL" if _secret_findings(path) else "PASS"),
    ]


def calculate_score(checks: list[tuple[str, str]]) -> int:
    total = sum(CHECK_WEIGHTS.get(name, 0) for name, _ in checks)
    earned = sum(CHECK_WEIGHTS.get(name, 0) for name, status in checks if status == "PASS")
    return round((earned / total) * 100) if total else 0


def is_deployable(checks: list[tuple[str, str]], score: int | None = None, threshold: int = DEFAULT_THRESHOLD) -> bool:
    if any(status == "FAIL" for _, status in checks):
        return False
    return (calculate_score(checks) if score is None else score) >= threshold


def _configured_threshold(path: Path) -> int:
    config = path / ".shipcheck.toml"
    if not config.exists():
        return DEFAULT_THRESHOLD
    try:
        for line in config.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith("threshold") and "=" in line:
                value = int(line.split("=", 1)[1].strip())
                if 0 <= value <= 100:
                    return value
    except (OSError, ValueError):
        pass
    return DEFAULT_THRESHOLD


@app.command()
def scan(
    path: Path = typer.Argument(None, exists=True, file_okay=False, dir_okay=True),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
    gate: bool = typer.Option(False, "--gate", help="Exit with code 1 when the deployment gate fails."),
    threshold: int | None = typer.Option(None, min=0, max=100, help="Minimum readiness score required by --gate."),
) -> None:
    """Scan PATH and report deployment readiness checks."""
    path = (path or Path(".")).resolve()
    checks = check_project(path)
    secrets = _secret_findings(path)
    score = calculate_score(checks)
    configured_threshold = _configured_threshold(path)
    effective_threshold = configured_threshold if threshold is None else threshold
    provider = _deployment_provider(path)
    deployable = is_deployable(checks, score, effective_threshold)
    payload = {"project": path.name, "framework": _framework(path), "deployment_provider": provider, "score": score, "threshold": effective_threshold, "deployable": deployable, "checks": [{"name": n, "status": s} for n, s in checks], "secret_findings": secrets}

    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        console.print(Panel.fit("[bold]ShipCheck[/bold]\nPre-deployment health check"))
        console.print(f"\n[bold]Project:[/bold] {path.name}")
        console.print(f"[bold]Framework:[/bold] {_framework(path)}")
        console.print(f"[bold]Deployment target:[/bold] {provider}\n")
        for name, status in checks:
            icon = {"PASS": "[green]✓[/green]", "WARN": "[yellow]⚠[/yellow]", "FAIL": "[red]✗[/red]"}[status]
            console.print(f"  {icon} {name}")
        if secrets:
            console.print("\n[bold red]Potential secrets:[/bold red]")
            for finding in secrets[:10]:
                console.print(f"  [red]•[/red] {finding}")
        verdict = "READY TO DEPLOY" if deployable else "BLOCKED"
        console.print(f"\n[bold]Deployment Readiness:[/bold] {score}% / {effective_threshold}% — {verdict}")

    if gate and not deployable:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
