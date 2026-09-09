from __future__ import annotations

import json
import re
import subprocess
import tomllib
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(help="Pre-deployment health checks for software projects.")
console = Console()
PATH_ARGUMENT = typer.Argument(None, exists=True, file_okay=False, dir_okay=True)

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
CHECK_WEIGHTS = {"Project directory": 5, "Git repository": 10, "Git working tree": 10, "Framework detection": 5, "README": 5, ".gitignore": 10, "Environment configuration": 10, "Dependency manifest": 10, "Deployment config": 10, "Provider validation": 5, "Tests": 10, "Secrets scan": 10}
DEFAULT_THRESHOLD = 80
EXIT_READY = 0
EXIT_GATE_FAILED = 1
EXIT_INVALID_CONFIG = 2
EXIT_USAGE = 3


def _git_clean(path: Path) -> str:
    try:
        result = subprocess.run(["git", "-C", str(path), "status", "--porcelain"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return "WARN"
    return "PASS" if result.returncode == 0 and not result.stdout.strip() else "WARN"


def _has_dependency_manifest(path: Path) -> str:
    manifests = ("pyproject.toml", "requirements.txt", "poetry.lock", "uv.lock", "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "go.mod", "go.sum", "Cargo.toml", "Cargo.lock")
    return "PASS" if any((path / name).exists() for name in manifests) else "WARN"


def _has_tests(path: Path) -> str:
    if any((path / name).is_dir() for name in ("tests", "test", "spec")):
        return "PASS"
    return "PASS" if any(p.name.startswith(("test_", "spec_")) for p in path.rglob("*") if p.is_file()) else "WARN"


def _framework(path: Path) -> str:
    if (path / "manage.py").exists(): return "Django"
    manifests = [p for p in (path / "pyproject.toml", path / "requirements.txt") if p.exists()]
    if manifests:
        text = "\n".join(_read_text(p) or "" for p in manifests).lower()
        for name, label in (("fastapi", "FastAPI"), ("flask", "Flask"), ("django", "Django")):
            if name in text: return label
        return "Python"
    package = path / "package.json"
    if package.exists():
        try:
            data = json.loads(_read_text(package) or "{}")
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            for name, label in (("next", "Next.js"), ("react", "React"), ("vue", "Vue"), ("express", "Express")):
                if name in deps: return label
        except json.JSONDecodeError: return "Node.js"
        return "Node.js"
    return "Unknown"


def _env_keys(file: Path) -> set[str]:
    return {line.split("=", 1)[0].strip() for line in (_read_text(file) or "").splitlines() if "=" in line and line.strip() and not line.lstrip().startswith("#")}


def _env_status(path: Path) -> str:
    env = path / ".env"
    template = next((path / name for name in (".env.example", ".env.template") if (path / name).exists()), None)
    if template is None: return "PASS" if env.exists() else "WARN"
    return "PASS" if env.exists() and _env_keys(template) <= _env_keys(env) else "WARN"


def _deployment_provider(path: Path) -> str:
    if (path / "vercel.json").exists() or (path / ".vercel").is_dir(): return "Vercel"
    if any((path / n).exists() for n in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")): return "Docker"
    if (path / "render.yaml").exists() or (path / "render.yml").exists(): return "Render"
    if (path / "railway.json").exists() or (path / "railway.toml").exists(): return "Railway"
    if (path / "fly.toml").exists(): return "Fly.io"
    if (path / "netlify.toml").exists(): return "Netlify"
    if (path / "Procfile").exists(): return "Procfile-compatible"
    if any((path / n).exists() for n in ("template.yaml", "template.yml", "sam-template.yaml", "sam-template.yml")): return "AWS"
    workflows = path / ".github" / "workflows"
    if workflows.is_dir() and any(p.suffix in {".yml", ".yaml"} for p in workflows.iterdir() if p.is_file()): return "GitHub Actions"
    return "Unknown"


def _deployment_files(path: Path) -> str:
    return "PASS" if _deployment_provider(path) != "Unknown" else "WARN"


def _read_text(path: Path) -> str | None:
    try: return path.read_text(encoding="utf-8", errors="ignore")
    except OSError: return None


def _load_yaml_mapping(path: Path) -> dict | None:
    try: data = yaml.safe_load(_read_text(path) or "")
    except yaml.YAMLError: return None
    return data if isinstance(data, dict) else None


def _validate_vercel(path: Path) -> str:
    try: return "PASS" if isinstance(json.loads(_read_text(path / "vercel.json") or ""), dict) else "FAIL"
    except (OSError, json.JSONDecodeError): return "FAIL"


def _validate_docker(path: Path) -> str:
    dockerfile = path / "Dockerfile"
    if dockerfile.exists(): return "PASS" if re.search(r"(?m)^\s*FROM\s+\S+", _read_text(dockerfile) or "") else "FAIL"
    compose = next((path / n for n in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml") if (path / n).exists()), None)
    data = _load_yaml_mapping(compose) if compose else None
    return "PASS" if data and isinstance(data.get("services"), dict) and data["services"] else "FAIL"


def _validate_github_actions(path: Path) -> str:
    workflows = path / ".github" / "workflows"
    files = [p for p in workflows.iterdir() if p.is_file() and p.suffix in {".yml", ".yaml"}] if workflows.is_dir() else []
    if not files: return "WARN"
    for workflow in files:
        data = _load_yaml_mapping(workflow)
        if data is None or not isinstance(data.get("name"), str) or not data.get("name", "").strip() or ("on" not in data and True not in data) or not isinstance(data.get("jobs"), dict) or not data["jobs"]: return "FAIL"
    return "PASS"


def _validate_toml(path: Path, filenames: tuple[str, ...], required_sections: tuple[str, ...] = ()) -> str:
    file = next((path / n for n in filenames if (path / n).exists()), None)
    if file is None: return "WARN"
    try: data = tomllib.loads(_read_text(file) or "")
    except tomllib.TOMLDecodeError: return "FAIL"
    return "PASS" if all(section in data for section in required_sections) else "FAIL"


def _validate_simple_yaml(path: Path, filenames: tuple[str, ...]) -> str:
    file = next((path / n for n in filenames if (path / n).exists()), None)
    if file is None: return "WARN"
    return "PASS" if _load_yaml_mapping(file) is not None else "FAIL"


def _provider_validation(path: Path, provider: str) -> str:
    if provider == "Vercel": return _validate_vercel(path)
    if provider == "Docker": return _validate_docker(path)
    if provider == "GitHub Actions": return _validate_github_actions(path)
    if provider == "Render": return _validate_simple_yaml(path, ("render.yaml", "render.yml"))
    if provider == "Railway":
        if (path / "railway.json").exists():
            try: return "PASS" if isinstance(json.loads(_read_text(path / "railway.json") or ""), dict) else "FAIL"
            except json.JSONDecodeError: return "FAIL"
        return _validate_toml(path, ("railway.toml",))
    if provider == "Fly.io": return _validate_toml(path, ("fly.toml",), ("app",))
    if provider == "Netlify": return _validate_toml(path, ("netlify.toml",))
    if provider == "AWS": return _validate_simple_yaml(path, ("template.yaml", "template.yml", "sam-template.yaml", "sam-template.yml"))
    if provider == "Procfile-compatible":
        text = _read_text(path / "Procfile") or ""
        return "PASS" if any(re.match(r"^\s*[A-Za-z][A-Za-z0-9_-]*\s*:", line) for line in text.splitlines()) else "FAIL"
    return "WARN"


def _secret_findings(path: Path) -> list[str]:
    findings, seen = [], set()
    for file in path.rglob("*"):
        if not file.is_file() or any(part in IGNORED_DIRS for part in file.parts) or file.suffix.lower() not in SCANNABLE_SUFFIXES: continue
        text = _read_text(file) or ""
        for label, pattern in SECRET_PATTERNS.items():
            match = pattern.search(text)
            if match and not (label == "Generic API key" and match.group(2).strip().lower() in PLACEHOLDER_VALUES):
                item = (str(file.relative_to(path)), label)
                if item not in seen: findings.append(f"{item[0]}: {item[1]}"); seen.add(item)
    return findings


def _config(path: Path) -> tuple[int, set[str], set[str]]:
    config = path / ".shipcheck.toml"
    if not config.exists(): return DEFAULT_THRESHOLD, set(), set()
    try:
        data = tomllib.loads(_read_text(config) or "")
        section = data.get("shipcheck", data)
        threshold = int(section.get("threshold", DEFAULT_THRESHOLD))
        if not 0 <= threshold <= 100: raise ValueError("threshold must be 0..100")
        ignore = section.get("ignore", {})
        return threshold, set(ignore.get("checks", [])), set(ignore.get("paths", []))
    except (tomllib.TOMLDecodeError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid .shipcheck.toml: {exc}") from exc


def check_project(path: Path, ignored_checks: set[str] | None = None) -> list[tuple[str, str]]:
    ignored_checks = ignored_checks or set()
    provider = _deployment_provider(path)
    checks = [("Project directory", "PASS" if path.is_dir() else "FAIL"), ("Git repository", "PASS" if (path / ".git").exists() else "WARN"), ("Git working tree", _git_clean(path) if (path / ".git").exists() else "WARN"), ("Framework detection", "PASS" if _framework(path) != "Unknown" else "WARN"), ("README", "PASS" if any((path / n).exists() for n in ("README.md", "README.rst", "README")) else "WARN"), (".gitignore", "PASS" if (path / ".gitignore").exists() else "WARN"), ("Environment configuration", _env_status(path)), ("Dependency manifest", _has_dependency_manifest(path)), ("Deployment config", _deployment_files(path)), ("Provider validation", _provider_validation(path, provider)), ("Tests", _has_tests(path)), ("Secrets scan", "FAIL" if _secret_findings(path) else "PASS")]
    return [(name, status) for name, status in checks if name not in ignored_checks]


def calculate_score(checks: list[tuple[str, str]]) -> int:
    total = sum(CHECK_WEIGHTS.get(n, 0) for n, _ in checks)
    earned = sum(CHECK_WEIGHTS.get(n, 0) for n, s in checks if s == "PASS")
    return round(earned / total * 100) if total else 0


def is_deployable(checks: list[tuple[str, str]], score: int | None = None, threshold: int = DEFAULT_THRESHOLD) -> bool:
    return not any(s == "FAIL" for _, s in checks) and (calculate_score(checks) if score is None else score) >= threshold


def _diagnostics(checks: list[tuple[str, str]], secrets: list[str]) -> dict[str, list[str]]:
    fixes = {"FAIL": [], "WARN": []}
    advice = {"Git repository": "Initialize Git and commit the project.", "Git working tree": "Commit or stash pending changes before deployment.", "README": "Add README.md with setup and deployment instructions.", ".gitignore": "Add a .gitignore covering secrets, environments, caches, and build artifacts.", "Environment configuration": "Add .env.example and ensure every required key is configured in deployment secrets.", "Dependency manifest": "Add a dependency manifest and lock file where supported.", "Deployment config": "Add the deployment configuration for your target platform.", "Provider validation": "Fix the detected provider configuration syntax and required fields.", "Tests": "Add automated tests before deploying.", "Framework detection": "Add a supported framework/dependency manifest or verify the project type."}
    for name, status in checks:
        if status in fixes and name in advice: fixes[status].append(f"{name}: {advice[name]}")
    if secrets: fixes["FAIL"].append("Secrets scan: remove exposed credentials and rotate them if they were real.")
    return fixes


def _sarif(payload: dict) -> dict:
    results = []
    for check in payload["checks"]:
        if check["status"] == "PASS": continue
        level = "error" if check["status"] == "FAIL" else "warning"
        message = next(iter(payload["diagnostics"][check["status"]]), check["name"])
        results.append({"ruleId": check["name"], "level": level, "message": {"text": message}})
    return {"version": "2.1.0", "$schema": "https://json.schemastore.org/sarif-2.1.0.json", "runs": [{"tool": {"driver": {"name": "ShipCheck", "version": "0.2.0"}}, "results": results}]}


def _safe_fix(path: Path) -> list[str]:
    changed = []
    if not (path / ".gitignore").exists():
        (path / ".gitignore").write_text(".env\n.venv/\n__pycache__/\n*.pyc\nnode_modules/\ndist/\nbuild/\n", encoding="utf-8")
        changed.append("Created .gitignore")
    if not (path / ".env.example").exists() and (path / ".env.template").exists():
        (path / ".env.example").write_text(_read_text(path / ".env.template") or "", encoding="utf-8")
        changed.append("Created .env.example from .env.template")
    return changed


@app.command()
def scan(path: Path | None = PATH_ARGUMENT, json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."), gate: bool = typer.Option(False, "--gate", help="Exit 1 when the deployment gate fails."), threshold: int | None = typer.Option(None, min=0, max=100, help="Minimum readiness score."), format: str = typer.Option("text", "--format", help="Output format: text, json, or sarif."), fix: bool = typer.Option(False, "--fix", help="Apply only safe, local template fixes before scanning.")) -> None:
    """Scan PATH and report deployment readiness."""
    path = (path or Path(".")).resolve()
    if format not in {"text", "json", "sarif"}: raise typer.BadParameter("must be text, json, or sarif", param_hint="--format")
    try: configured_threshold, ignored_checks, _ = _config(path)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=EXIT_INVALID_CONFIG) from exc
    if fix:
        for item in _safe_fix(path): console.print(f"[green]✓[/green] {item}")
    checks = check_project(path, ignored_checks)
    secrets = _secret_findings(path)
    score = calculate_score(checks)
    effective_threshold = configured_threshold if threshold is None else threshold
    provider = _deployment_provider(path)
    deployable = is_deployable(checks, score, effective_threshold)
    diagnostics = _diagnostics(checks, secrets)
    payload = {"project": path.name, "framework": _framework(path), "deployment_provider": provider, "score": score, "threshold": effective_threshold, "deployable": deployable, "checks": [{"name": n, "status": s} for n, s in checks], "secret_findings": secrets, "diagnostics": diagnostics, "exit_codes": {"ready": EXIT_READY, "gate_failed": EXIT_GATE_FAILED, "invalid_config": EXIT_INVALID_CONFIG, "usage": EXIT_USAGE}}
    if format == "sarif": typer.echo(json.dumps(_sarif(payload), indent=2))
    elif json_output or format == "json": typer.echo(json.dumps(payload, indent=2))
    else:
        console.print(Panel.fit("[bold]ShipCheck[/bold]\nPre-deployment health check"))
        console.print(f"\n[bold]Project:[/bold] {path.name}\n[bold]Framework:[/bold] {_framework(path)}\n[bold]Deployment target:[/bold] {provider}\n")
        for name, status in checks:
            icon = {"PASS": "[green]✓[/green]", "WARN": "[yellow]⚠[/yellow]", "FAIL": "[red]✗[/red]"}[status]
            console.print(f"  {icon} {name}")
        if secrets:
            console.print("\n[bold red]Potential secrets:[/bold red]")
            for finding in secrets[:10]: console.print(f"  [red]•[/red] {finding}")
        for level in ("FAIL", "WARN"):
            if diagnostics[level]:
                console.print(f"\n[bold]{'Required fixes' if level == 'FAIL' else 'Recommendations'}:[/bold]")
                for item in diagnostics[level][:10]: console.print(f"  • {item}")
        console.print(f"\n[bold]Deployment Readiness:[/bold] {score}% / {effective_threshold}% — {'READY TO DEPLOY' if deployable else 'BLOCKED'}")
    if gate and not deployable: raise typer.Exit(code=EXIT_GATE_FAILED)


if __name__ == "__main__": app()
